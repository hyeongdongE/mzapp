from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence.clustering import ConservativeClusterer, EventClusterDraft
from app.intelligence.entities import extract_entities
from app.intelligence.evidence import evidence_from_raw_item
from app.models.enums import ClusterStatus, ReviewStatus
from app.models.tables import (
    EventCluster,
    EventClusterItem,
    EventEntityLink,
    EventEvidence,
    IntelligenceEntity,
    RawItem,
)


@dataclass(frozen=True)
class EventProcessingResult:
    created_clusters: int
    assigned_items: int
    created_entities: int
    created_evidence: int
    cluster_ids: tuple[int, ...]


class EventProcessingService:
    def __init__(
        self,
        session: Session,
        *,
        now: Callable[[], datetime] | None = None,
        clusterer: ConservativeClusterer | None = None,
    ) -> None:
        self._session = session
        self._now = now or (lambda: datetime.now(UTC))
        self._clusterer = clusterer or ConservativeClusterer()

    def process_window(
        self,
        window_start: datetime,
        window_end: datetime,
        *,
        version: str,
    ) -> EventProcessingResult:
        assigned_ids = select(EventClusterItem.raw_item_id)
        items = list(
            self._session.scalars(
                select(RawItem)
                .where(
                    RawItem.published_at >= window_start,
                    RawItem.published_at < window_end,
                    RawItem.id.not_in(assigned_ids),
                )
                .order_by(RawItem.published_at, RawItem.id)
            )
        )
        if not items:
            return EventProcessingResult(0, 0, 0, 0, ())

        existing_clusters = self._existing_clusters(window_start, window_end)
        result = self._clusterer.process(
            items,
            existing_clusters=existing_clusters,
        )
        decisions = {decision.item_id: decision for decision in result.decisions}
        created_entities = 0
        created_evidence = 0
        cluster_ids: list[int] = []
        assigned_at = self._now().astimezone(UTC)
        new_item_ids = {item.id for item in items}
        created_clusters = 0
        for draft in result.clusters:
            if draft.persisted:
                cluster = self._session.get(EventCluster, draft.id)
                if cluster is None:
                    continue
                members = [item for item in draft.members if item.id in new_item_ids]
                if not members:
                    continue
                cluster.last_seen_at = max(
                    cluster.last_seen_at,
                    max(item.collected_at for item in members),
                )
            else:
                members = list(draft.members)
                cluster = EventCluster(
                    public_id=str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"{version}:{','.join(str(item.id) for item in members)}",
                        )
                    ),
                    canonical_title=members[0].title,
                    summary=None,
                    first_seen_at=min(item.collected_at for item in members),
                    last_seen_at=max(item.collected_at for item in members),
                    status=(
                        ClusterStatus.NEEDS_REVIEW
                        if draft.needs_review
                        else ClusterStatus.ACTIVE
                    ),
                    clustering_version=version,
                    review_status=ReviewStatus.PENDING,
                )
                self._session.add(cluster)
                self._session.flush()
                created_clusters += 1
            cluster_ids.append(cluster.id)
            linked_entities = {
                (link.entity_id, link.role)
                for link in self._session.scalars(
                    select(EventEntityLink).where(
                        EventEntityLink.event_cluster_id == cluster.id
                    )
                )
            }
            for item in members:
                decision = decisions[item.id]
                self._session.add(
                    EventClusterItem(
                        event_cluster_id=cluster.id,
                        raw_item_id=item.id,
                        assignment_method=decision.action.value,
                        assignment_score=decision.score,
                        reason_codes=list(decision.reason_codes),
                        human_confirmed=False,
                        assigned_at=assigned_at,
                    )
                )
                for mention in extract_entities(item):
                    entity, created = self._entity(mention)
                    created_entities += int(created)
                    key = (entity.id, mention.role)
                    if key not in linked_entities:
                        linked_entities.add(key)
                        self._session.add(
                            EventEntityLink(
                                event_cluster_id=cluster.id,
                                entity_id=entity.id,
                                role=mention.role,
                            )
                        )
                evidence = evidence_from_raw_item(item)
                self._session.add(
                    EventEvidence(
                        event_cluster_id=cluster.id,
                        raw_item_id=item.id,
                        kind=evidence.kind,
                        fact=evidence.fact,
                        source_url=evidence.source_url,
                        observed_at=evidence.observed_at,
                        publishable=evidence.publishable,
                    )
                )
                created_evidence += 1
        self._session.flush()
        return EventProcessingResult(
            created_clusters=created_clusters,
            assigned_items=len(items),
            created_entities=created_entities,
            created_evidence=created_evidence,
            cluster_ids=tuple(cluster_ids),
        )

    def _existing_clusters(
        self, window_start: datetime, window_end: datetime
    ) -> tuple[EventClusterDraft, ...]:
        cluster_ids = self._session.scalars(
            select(EventCluster.id)
            .join(
                EventClusterItem,
                EventClusterItem.event_cluster_id == EventCluster.id,
            )
            .join(RawItem, RawItem.id == EventClusterItem.raw_item_id)
            .where(
                EventCluster.status == ClusterStatus.ACTIVE,
                RawItem.published_at >= window_start,
                RawItem.published_at < window_end,
            )
            .distinct()
            .order_by(EventCluster.id)
        )
        drafts = []
        for cluster_id in cluster_ids:
            members = list(
                self._session.scalars(
                    select(RawItem)
                    .join(
                        EventClusterItem,
                        EventClusterItem.raw_item_id == RawItem.id,
                    )
                    .where(EventClusterItem.event_cluster_id == cluster_id)
                    .order_by(RawItem.id)
                )
            )
            drafts.append(
                EventClusterDraft(
                    id=cluster_id,
                    members=members,
                    persisted=True,
                )
            )
        return tuple(drafts)

    def _entity(self, mention) -> tuple[IntelligenceEntity, bool]:
        entity = self._session.scalar(
            select(IntelligenceEntity)
            .where(
                IntelligenceEntity.normalized_name == mention.normalized_name,
                IntelligenceEntity.entity_type == mention.entity_type,
            )
            .limit(1)
        )
        if entity is not None:
            return entity, False
        entity = IntelligenceEntity(
            canonical_name=mention.canonical_name,
            normalized_name=mention.normalized_name,
            entity_type=mention.entity_type,
            aliases=list(mention.aliases),
        )
        self._session.add(entity)
        self._session.flush()
        return entity, True
