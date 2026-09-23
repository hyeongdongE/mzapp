from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.collectors.base import CollectionBatch, SourceItem
from app.intelligence.normalization import normalize_source_item
from app.models.enums import Source
from app.models.tables import RawFetch, RawItem, SourceHealth
from app.services.intelligence_collection import IntelligenceCollectionService

AS_OF = datetime(2026, 9, 23, 3, 0, tzinfo=UTC)


class FixtureCollector:
    source = Source.GEEKNEWS

    async def collect(self, as_of: datetime) -> CollectionBatch:
        return CollectionBatch(
            source=self.source,
            collected_at=as_of,
            request_url="https://news.hada.io/rss/news",
            raw_bytes=b"<feed />",
            items=[
                SourceItem(
                    source_item_id="geeknews:42",
                    source_timestamp=as_of,
                    observed_at=as_of,
                    canonical_text="SoloPilot release",
                    source_url="https://news.hada.io/topic?id=42&utm_source=test",
                    metrics={},
                    title="SoloPilot release",
                    snippet="GeekNews-authored summary that must remain private",
                    metadata={"attribution": "GeekNews"},
                )
            ],
            collector_version="fixture-v1",
            parser_version="fixture-parser-v1",
        )


def test_geeknews_normalization_does_not_publish_source_summary() -> None:
    item = SourceItem(
        source_item_id="geeknews:42",
        source_timestamp=AS_OF,
        observed_at=AS_OF,
        canonical_text="SoloPilot release",
        source_url="https://news.hada.io/topic?id=42",
        metrics={},
        title="SoloPilot release",
        snippet="private summary",
        metadata={"attribution": "GeekNews"},
    )

    normalized = normalize_source_item(Source.GEEKNEWS, item, raw_fetch_id=7)

    assert normalized.snippet is None
    assert normalized.metadata["attribution"] == "GeekNews"


@pytest.mark.asyncio
async def test_collection_links_raw_item_to_fetch_and_updates_health(db_session) -> None:
    result = await IntelligenceCollectionService(db_session, now=lambda: AS_OF).run(
        FixtureCollector(), as_of=AS_OF, run_key="geeknews:20260923T030000Z"
    )

    raw_item = db_session.scalar(select(RawItem))
    health = db_session.get(SourceHealth, Source.GEEKNEWS)
    assert raw_item is not None
    assert db_session.get(RawFetch, result.fetch_id) is not None
    assert raw_item.raw_fetch_id == result.fetch_id
    assert raw_item.canonical_url == "https://news.hada.io/topic?id=42"
    assert raw_item.snippet is None
    assert health is not None
    assert health.last_success_at == AS_OF.replace(tzinfo=None)
    assert health.consecutive_failures == 0
