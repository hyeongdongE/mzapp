from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.collectors.base import CollectionBatch, MalformedPayload, SourceItem
from app.models.enums import Source
from app.models.tables import RawItem
from app.services.intelligence_scheduler import IntelligencePipeline

AS_OF = datetime(2026, 9, 23, 3, 0, tzinfo=UTC)


class GoodCollector:
    source = Source.GEEKNEWS

    async def collect(self, as_of: datetime) -> CollectionBatch:
        return CollectionBatch(
            source=self.source,
            collected_at=as_of,
            request_url="https://news.hada.io/rss/news",
            raw_bytes=b"<feed />",
            items=[
                SourceItem(
                    source_item_id="geeknews:pipeline",
                    source_timestamp=as_of,
                    observed_at=as_of,
                    canonical_text="Pipeline event",
                    source_url="https://news.hada.io/topic?id=pipeline",
                    metrics={},
                    title="Pipeline event",
                    metadata={"attribution": "GeekNews"},
                )
            ],
            collector_version="fixture-v1",
            parser_version="fixture-v1",
        )


class BadCollector:
    source = Source.HACKER_NEWS

    async def collect(self, as_of: datetime) -> CollectionBatch:
        del as_of
        raise MalformedPayload("broken fixture")


@pytest.mark.asyncio
async def test_collection_failures_are_isolated_and_run_keys_are_idempotent(
    db_session,
) -> None:
    pipeline = IntelligencePipeline(db_session, now=lambda: AS_OF)

    first = await pipeline.collect([BadCollector(), GoodCollector()], as_of=AS_OF)
    second = await pipeline.collect([GoodCollector()], as_of=AS_OF)

    assert [(item.source, item.succeeded) for item in first] == [
        (Source.HACKER_NEWS, False),
        (Source.GEEKNEWS, True),
    ]
    assert second[0].succeeded is True
    assert db_session.scalar(select(func.count()).select_from(RawItem)) == 1
