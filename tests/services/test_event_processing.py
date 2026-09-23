from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.collectors.base import CollectionBatch, SourceItem
from app.models.enums import EvidenceConfidence, Source
from app.models.tables import (
    EventAssessment,
    EventCluster,
    EventClusterItem,
    EventEntityLink,
    EventEvidence,
    IntelligenceEntity,
)
from app.services.event_processing import EventProcessingService
from app.services.intelligence_collection import IntelligenceCollectionService
from app.services.intelligence_scheduler import IntelligencePipeline

AS_OF = datetime(2026, 9, 23, 3, 0, tzinfo=UTC)


class EventCollector:
    def __init__(self, source: Source, item: SourceItem) -> None:
        self.source = source
        self._item = item

    async def collect(self, as_of: datetime) -> CollectionBatch:
        return CollectionBatch(
            source=self.source,
            collected_at=as_of,
            request_url=self._item.source_url,
            raw_bytes=f"payload:{self._item.source_item_id}".encode(),
            items=[self._item],
            collector_version="fixture-v1",
            parser_version="fixture-parser-v1",
            coverage_complete=True,
        )


def source_item(source: Source, index: int, title: str, url: str) -> SourceItem:
    return SourceItem(
        source_item_id=f"{source.value.lower()}:{index}",
        source_timestamp=AS_OF - timedelta(minutes=5 - index),
        observed_at=AS_OF,
        canonical_text=title,
        source_url=url,
        metrics={},
        title=title,
        original_url=url,
        metadata={"attribution": source.value},
    )


@pytest.mark.asyncio
async def test_event_processing_persists_cluster_entities_and_evidence(db_session) -> None:
    fixtures = [
        (Source.GEEKNEWS, "Acme Agent SDK 2.0 released", "https://news.hada.io/topic?id=1"),
        (Source.HACKER_NEWS, "Acme Agent SDK 2.0 is out", "https://news.ycombinator.com/item?id=2"),
        (Source.GITHUB_RELEASES, "Agent SDK v2.0.0", "https://github.com/acme/agent-sdk/releases/tag/v2.0.0"),
        (Source.OFFICIAL_CLOUDFLARE, "Support for Acme Agent SDK 2.0", "https://blog.cloudflare.com/acme-agent-sdk-2"),
    ]
    for index, (source, title, url) in enumerate(fixtures, start=1):
        collector = EventCollector(source, source_item(source, index, title, url))
        await IntelligenceCollectionService(db_session, now=lambda: AS_OF).run(
            collector,
            as_of=AS_OF,
            run_key=f"{source.value}:{index}",
        )

    result = EventProcessingService(db_session, now=lambda: AS_OF).process_window(
        AS_OF - timedelta(days=1),
        AS_OF + timedelta(minutes=1),
        version="cluster-v1",
    )

    assert result.created_clusters == 1
    assert result.assigned_items == 4
    assert result.created_evidence == 4
    assert db_session.scalar(select(func.count()).select_from(EventCluster)) == 1
    assert db_session.scalar(select(func.count()).select_from(EventClusterItem)) == 4
    assert db_session.scalar(select(func.count()).select_from(EventEvidence)) == 4
    assert db_session.scalar(select(func.count()).select_from(IntelligenceEntity)) >= 1
    assert db_session.scalar(select(func.count()).select_from(EventEntityLink)) >= 1
    cluster = db_session.scalar(select(EventCluster))
    assert cluster is not None
    assert cluster.clustering_version == "cluster-v1"


@pytest.mark.asyncio
async def test_event_processing_is_replay_safe_for_already_assigned_items(db_session) -> None:
    item = source_item(
        Source.GEEKNEWS,
        1,
        "Acme Agent SDK 2.0 released",
        "https://news.hada.io/topic?id=1",
    )
    await IntelligenceCollectionService(db_session, now=lambda: AS_OF).run(
        EventCollector(Source.GEEKNEWS, item),
        as_of=AS_OF,
        run_key="geeknews:replay-safe",
    )
    service = EventProcessingService(db_session, now=lambda: AS_OF)

    first = service.process_window(
        AS_OF - timedelta(days=1), AS_OF + timedelta(minutes=1), version="cluster-v1"
    )
    second = service.process_window(
        AS_OF - timedelta(days=1), AS_OF + timedelta(minutes=1), version="cluster-v1"
    )

    assert first.assigned_items == 1
    assert second.assigned_items == 0


@pytest.mark.asyncio
async def test_late_matching_item_enriches_existing_cluster(db_session) -> None:
    pipeline = IntelligencePipeline(db_session, now=lambda: AS_OF)
    await IntelligenceCollectionService(db_session, now=lambda: AS_OF).run(
        EventCollector(
            Source.GITHUB_RELEASES,
            source_item(
                Source.GITHUB_RELEASES,
                1,
                "Acme Agent SDK 2.0 released",
                "https://github.com/acme/agent-sdk/releases/tag/v2.0.0",
            ),
        ),
        as_of=AS_OF,
        run_key="github:initial",
    )
    first = pipeline.process(
        AS_OF - timedelta(days=1),
        AS_OF + timedelta(minutes=1),
        version="cluster-v1",
        assessment_version="assessment-v1",
    )

    await IntelligenceCollectionService(db_session, now=lambda: AS_OF).run(
        EventCollector(
            Source.HACKER_NEWS,
            source_item(
                Source.HACKER_NEWS,
                2,
                "Acme Agent SDK v2.0 is out",
                "https://news.ycombinator.com/item?id=2",
            ),
        ),
        as_of=AS_OF,
        run_key="hn:late",
    )
    second = pipeline.process(
        AS_OF - timedelta(days=1),
        AS_OF + timedelta(minutes=1),
        version="cluster-v1",
        assessment_version="assessment-v1",
    )

    assert first.created_clusters == 1
    assert second.created_clusters == 0
    assert second.cluster_ids == first.cluster_ids
    assert db_session.scalar(select(func.count()).select_from(EventCluster)) == 1
    assert db_session.scalar(select(func.count()).select_from(EventClusterItem)) == 2
    assert db_session.scalar(select(func.count()).select_from(EventEvidence)) == 2
    assessment = db_session.scalar(select(EventAssessment))
    assert assessment is not None
    assert assessment.confidence is EvidenceConfidence.STRONG
    assert assessment.confidence_breakdown["independent_evidence_count"] == 2.0
