from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.intelligence.evidence import evidence_from_raw_item
from app.models.enums import ClusterStatus, ReviewStatus, RunStatus, Source
from app.models.tables import (
    CollectionRun,
    EventCluster,
    EventClusterItem,
    EventEvidence,
    RawFetch,
    RawItem,
    RawPayload,
)

NOW = datetime(2026, 9, 23, 3, 0, tzinfo=UTC)


@dataclass(frozen=True)
class EvidenceSpec:
    source: Source
    title: str
    canonical_url: str | None = None
    metadata: dict = field(default_factory=dict)


def seed_event(
    session: Session,
    specs: list[EvidenceSpec],
    *,
    status: ClusterStatus = ClusterStatus.ACTIVE,
    suffix: str = "event",
) -> EventCluster:
    cluster = EventCluster(
        public_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"golden-test:{suffix}")),
        canonical_title=specs[0].title,
        summary=None,
        first_seen_at=NOW,
        last_seen_at=NOW,
        status=status,
        clustering_version="test-cluster-v1",
        review_status=ReviewStatus.PENDING,
    )
    session.add(cluster)
    session.flush()
    for index, spec in enumerate(specs, start=1):
        observed_at = NOW + timedelta(seconds=index)
        run = CollectionRun(
            run_key=f"{suffix}:{index}",
            source=spec.source,
            started_at=observed_at,
            completed_at=observed_at,
            status=RunStatus.SUCCEEDED,
            error_code=None,
        )
        payload = RawPayload(
            source=spec.source,
            payload_hash=f"{suffix}-{index}".ljust(64, "0"),
            raw_payload={"fixture": True},
            collected_at=observed_at,
            source_timestamp=NOW,
            collector_version="fixture-v1",
            parser_version="fixture-v1",
        )
        session.add_all([run, payload])
        session.flush()
        fetch = RawFetch(
            run_id=run.id,
            raw_payload_id=payload.id,
            request_url=f"https://source.example/{suffix}/{index}",
            collected_at=observed_at,
            source_timestamp=NOW,
            collector_version="fixture-v1",
            parser_version="fixture-v1",
        )
        session.add(fetch)
        session.flush()
        canonical_url = spec.canonical_url or f"https://vendor.example/{suffix}/{index}"
        raw_item = RawItem(
            raw_fetch_id=fetch.id,
            source=spec.source,
            external_id=f"{suffix}:{index}",
            title=spec.title,
            url=f"https://source.example/{suffix}/{index}",
            original_url=canonical_url,
            author=None,
            published_at=NOW,
            collected_at=observed_at,
            canonical_url=canonical_url,
            content_hash=f"content-{suffix}-{index}".ljust(64, "0")[:64],
            normalized_title=spec.title.casefold(),
            snippet=None,
            item_metadata={"attribution": spec.source.value, **spec.metadata},
            normalizer_version="fixture-v1",
        )
        session.add(raw_item)
        session.flush()
        session.add(
            EventClusterItem(
                event_cluster_id=cluster.id,
                raw_item_id=raw_item.id,
                assignment_method="FIXTURE",
                assignment_score=1.0,
                reason_codes=["FIXTURE"],
                human_confirmed=False,
                assigned_at=observed_at,
            )
        )
        draft = evidence_from_raw_item(raw_item)
        session.add(
            EventEvidence(
                event_cluster_id=cluster.id,
                raw_item_id=raw_item.id,
                kind=draft.kind,
                fact=draft.fact,
                source_url=draft.source_url,
                observed_at=draft.observed_at,
                publishable=draft.publishable,
            )
        )
    session.flush()
    return cluster
