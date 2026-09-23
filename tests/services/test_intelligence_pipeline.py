from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.collectors.base import CollectionBatch, MalformedPayload, SourceItem
from app.models.enums import Source
from app.models.tables import RawItem, SourceHealth
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
            coverage_complete=True,
        )


class BadCollector:
    source = Source.HACKER_NEWS

    async def collect(self, as_of: datetime) -> CollectionBatch:
        del as_of
        raise MalformedPayload("broken fixture")


class GitHubCollector(GoodCollector):
    source = Source.GITHUB_RELEASES

    def __init__(self, key: str, *, fail: bool = False) -> None:
        self.collection_key = key
        self._fail = fail

    async def collect(self, as_of: datetime) -> CollectionBatch:
        if self._fail:
            raise MalformedPayload("broken repository")
        batch = await super().collect(as_of)
        return CollectionBatch(**{**batch.__dict__, "source": self.source})


class KeyedGitHubCollector(GitHubCollector):
    async def collect(self, as_of: datetime) -> CollectionBatch:
        batch = await super().collect(as_of)
        item = batch.items[0]
        return CollectionBatch(
            **{
                **batch.__dict__,
                "request_url": f"https://api.github.com/repos/{self.collection_key}/releases",
                "raw_bytes": f"payload:{self.collection_key}".encode(),
                "items": [
                    SourceItem(
                        **{
                            **item.__dict__,
                            "source_item_id": f"github:{self.collection_key}:1",
                        }
                    )
                ],
            }
        )


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


@pytest.mark.asyncio
async def test_repository_health_is_isolated_per_collection_key(db_session) -> None:
    pipeline = IntelligencePipeline(db_session, now=lambda: AS_OF)

    result = await pipeline.collect(
        [GitHubCollector("acme/failing", fail=True), GitHubCollector("acme/healthy")],
        as_of=AS_OF,
    )

    assert [item.succeeded for item in result] == [False, True]
    failed = db_session.get(SourceHealth, (Source.GITHUB_RELEASES, "acme/failing"))
    healthy = db_session.get(SourceHealth, (Source.GITHUB_RELEASES, "acme/healthy"))
    assert failed is not None and failed.freshness_state == "FAILED"
    assert healthy is not None and healthy.freshness_state == "FRESH"


@pytest.mark.asyncio
async def test_repository_run_keys_are_stable_when_configuration_order_changes(
    db_session,
) -> None:
    pipeline = IntelligencePipeline(db_session, now=lambda: AS_OF)
    left = KeyedGitHubCollector("acme/left")
    right = KeyedGitHubCollector("acme/right")

    first = await pipeline.collect([left, right], as_of=AS_OF)
    second = await pipeline.collect([right, left], as_of=AS_OF)

    assert all(result.succeeded for result in [*first, *second])
    assert db_session.scalar(select(func.count()).select_from(RawItem)) == 2
