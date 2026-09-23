from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence.clustering import ConservativeClusterer
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
            return EventProcessingResult(0, 0, 0, 0)

        result = self._clusterer.process(items)
        decisions = {decision.item_id: decision for decision in result.decisions}
        created_entities = 0
        created_evidence = 0
        assigned_at = self._now().astimezone(UTC)
        for draft in result.clusters:
            cluster = EventCluster(
                public_id=str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"{version}:{','.join(str(item.id) for item in draft.members)}",
                    )
                ),
                canonical_title=draft.members[0].title,
                summary=None,
                first_seen_at=min(item.collected_at for item in draft.members),
                last_seen_at=max(item.collected_at for item in draft.members),
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
            linked_entities: set[tuple[int, str]] = set()
            for item in draft.members:
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
            created_clusters=len(result.clusters),
            assigned_items=len(items),
            created_entities=created_entities,
            created_evidence=created_evidence,
        )

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
