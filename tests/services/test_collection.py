from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.collectors.base import CollectionBatch, HttpRequestFailed, SourceItem
from app.models.enums import RunStatus, Source
from app.models.tables import Base, CollectionRun, RawFetch, RawPayload, SourceObservation
from app.services.collection import CollectionService

AS_OF = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def batch() -> CollectionBatch:
    return CollectionBatch(
        source=Source.GOOGLE_TRENDS,
        collected_at=AS_OF,
        request_url="https://trends.google.com/trending/rss?geo=KR",
        raw_bytes=b"<rss>same exact bytes</rss>",
        items=[
            SourceItem(
                source_item_id="google:item:1",
                source_timestamp=AS_OF,
                observed_at=AS_OF,
                canonical_text="이현중",
                source_url="https://trends.google.com/trending/rss?geo=KR",
                metrics={"approx_traffic_raw": "2천+"},
            )
        ],
        collector_version="google-rss-v1",
        parser_version="google-rss-parser-v1",
    )


def count(db_session, model) -> int:
    return db_session.scalar(select(func.count()).select_from(model)) or 0


def test_identical_payload_across_runs_reuses_blob_and_keeps_observations(db_session) -> None:
    service = CollectionService(db_session)

    first = service.persist(batch(), run_key="google:20260920T1000")
    second = service.persist(batch(), run_key="google:20260920T1100")

    assert count(db_session, RawPayload) == 1
    assert count(db_session, RawFetch) == 2
    assert count(db_session, SourceObservation) == 2
    assert first.run_id != second.run_id


def test_same_run_retry_does_not_duplicate_observations(db_session) -> None:
    service = CollectionService(db_session)

    first = service.persist(batch(), run_key="google:20260920T1000")
    second = service.persist(batch(), run_key="google:20260920T1000")

    assert count(db_session, CollectionRun) == 1
    assert count(db_session, SourceObservation) == 1
    assert second.run_id == first.run_id
    assert second.inserted_observations == 0


def test_geeknews_item_repeated_in_new_feed_snapshot_is_not_duplicated(db_session) -> None:
    value = batch()
    geeknews = CollectionBatch(
        source=Source.GEEKNEWS,
        collected_at=value.collected_at,
        request_url="https://news.hada.io/rss/news",
        raw_bytes=b"<feed>snapshot one</feed>",
        items=[
            SourceItem(
                source_item_id="geeknews:item:34041",
                source_timestamp=AS_OF,
                observed_at=AS_OF,
                canonical_text="LangChain agent",
                source_url="https://news.hada.io/topic?id=34041",
                metrics={"entry_id": "https://news.hada.io/topic?id=34041"},
            )
        ],
        collector_version="geeknews-atom-v1",
        parser_version="geeknews-atom-parser-v1",
    )

    first = CollectionService(db_session).persist(geeknews, run_key="geeknews:first")
    second = CollectionService(db_session).persist(
        CollectionBatch(
            source=geeknews.source,
            collected_at=geeknews.collected_at,
            request_url=geeknews.request_url,
            raw_bytes=b"<feed>snapshot two</feed>",
            items=geeknews.items,
            collector_version=geeknews.collector_version,
            parser_version=geeknews.parser_version,
        ),
        run_key="geeknews:second",
    )

    assert first.inserted_observations == 1
    assert second.inserted_observations == 0
    assert count(db_session, RawFetch) == 2
    assert count(db_session, SourceObservation) == 1


def test_geeknews_parser_upgrade_can_emit_corrected_observation_once(db_session) -> None:
    original = batch()
    v1 = CollectionBatch(
        source=Source.GEEKNEWS,
        collected_at=original.collected_at,
        request_url="https://news.hada.io/rss/news",
        raw_bytes=b"<feed>same bytes</feed>",
        items=[
            SourceItem(
                source_item_id="geeknews:item:versioned",
                source_timestamp=AS_OF,
                observed_at=AS_OF,
                canonical_text="Claude &quot;Code&quot;",
                source_url="https://news.hada.io/topic?id=versioned",
                metrics={"entry_id": "versioned"},
            )
        ],
        collector_version="geeknews-atom-v1",
        parser_version="geeknews-atom-parser-v1",
    )
    v2 = CollectionBatch(
        source=v1.source,
        collected_at=v1.collected_at,
        request_url=v1.request_url,
        raw_bytes=v1.raw_bytes,
        items=[
            SourceItem(
                source_item_id="geeknews:item:versioned",
                source_timestamp=AS_OF,
                observed_at=AS_OF,
                canonical_text='Claude "Code"',
                source_url="https://news.hada.io/topic?id=versioned",
                metrics={"entry_id": "versioned"},
            )
        ],
        collector_version="geeknews-atom-v1",
        parser_version="geeknews-atom-parser-v2",
    )

    first = CollectionService(db_session).persist(v1, run_key="geeknews:parser-v1")
    upgraded = CollectionService(db_session).persist(v2, run_key="geeknews:parser-v2")
    repeated = CollectionService(db_session).persist(v2, run_key="geeknews:parser-v2-repeat")

    assert first.inserted_observations == 1
    assert upgraded.inserted_observations == 1
    assert repeated.inserted_observations == 0
    assert count(db_session, SourceObservation) == 2


def test_raw_payload_preserves_exact_bytes_for_replay(db_session) -> None:
    CollectionService(db_session).persist(batch(), run_key="google:20260920T1000")

    stored = db_session.scalar(select(RawPayload))

    assert stored is not None
    assert stored.raw_payload == {
        "content_encoding": "base64",
        "content_type": "application/octet-stream",
        "data": "PHJzcz5zYW1lIGV4YWN0IGJ5dGVzPC9yc3M+",
    }
    assert stored.payload_hash == "5c6a31d0be98a45eb99db929d3f81ee74f89d6058c660f98800f75481eeed533"


def test_empty_batch_retains_run_to_payload_fetch_provenance(db_session) -> None:
    value = batch()
    value = CollectionBatch(
        source=value.source,
        collected_at=value.collected_at,
        request_url=value.request_url,
        raw_bytes=b"<rss><channel/></rss>",
        items=[],
        collector_version=value.collector_version,
        parser_version=value.parser_version,
    )

    result = CollectionService(db_session).persist(value, run_key="google:empty")
    fetch = db_session.scalar(select(RawFetch).where(RawFetch.run_id == result.run_id))

    assert fetch is not None
    assert fetch.raw_payload_id == result.payload_id
    assert fetch.request_url == value.request_url
    assert fetch.collected_at == value.collected_at.replace(tzinfo=None)
    assert fetch.source_timestamp is None
    assert fetch.collector_version == "google-rss-v1"
    assert fetch.parser_version == "google-rss-parser-v1"


def test_same_raw_bytes_retain_each_fetch_parser_version(db_session) -> None:
    first = batch()
    second = CollectionBatch(
        source=first.source,
        collected_at=first.collected_at,
        request_url=first.request_url,
        raw_bytes=first.raw_bytes,
        items=first.items,
        collector_version="google-rss-v2",
        parser_version="google-rss-parser-v2",
    )

    CollectionService(db_session).persist(first, run_key="google:v1")
    CollectionService(db_session).persist(second, run_key="google:v2")

    fetches = list(db_session.scalars(select(RawFetch).order_by(RawFetch.id)))
    assert count(db_session, RawPayload) == 1
    assert [fetch.parser_version for fetch in fetches] == [
        "google-rss-parser-v1",
        "google-rss-parser-v2",
    ]


@pytest.mark.asyncio
async def test_failed_collection_records_redacted_error_code(db_session) -> None:
    class FailingCollector:
        source = Source.WIKIMEDIA

        async def collect(self, _as_of: datetime) -> CollectionBatch:
            raise HttpRequestFailed("TIMEOUT")

    with pytest.raises(HttpRequestFailed):
        await CollectionService(db_session).run(
            FailingCollector(), as_of=AS_OF, run_key="wikimedia:20260920"
        )

    run = db_session.scalar(select(CollectionRun))
    assert run is not None
    assert run.status is RunStatus.FAILED
    assert run.error_code == "TIMEOUT"


@pytest.mark.asyncio
async def test_successful_collection_uses_real_run_boundaries_not_logical_as_of(db_session) -> None:
    value = batch()

    class SuccessfulCollector:
        source = Source.GOOGLE_TRENDS

        async def collect(self, _as_of: datetime) -> CollectionBatch:
            return value

    moments = iter(
        [
            datetime(2026, 9, 20, 12, 0, 1, tzinfo=UTC),
            datetime(2026, 9, 20, 12, 0, 9, tzinfo=UTC),
        ]
    )

    await CollectionService(db_session, now=lambda: next(moments)).run(
        SuccessfulCollector(),
        as_of=datetime(2020, 1, 1, tzinfo=UTC),
        run_key="google:trusted-clock",
    )

    run = db_session.scalar(select(CollectionRun))
    assert run is not None
    assert run.started_at == datetime(2026, 9, 20, 12, 0, 1)
    assert run.completed_at == datetime(2026, 9, 20, 12, 0, 9)


@pytest.mark.asyncio
async def test_failed_collection_survives_outer_rollback_in_its_own_transaction() -> None:
    class FailingCollector:
        source = Source.WIKIMEDIA

        async def collect(self, _as_of: datetime) -> CollectionBatch:
            raise HttpRequestFailed("TIMEOUT")

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    moments = iter(
        [
            datetime(2026, 9, 20, 12, 0, 1, tzinfo=UTC),
            datetime(2026, 9, 20, 12, 0, 9, tzinfo=UTC),
        ]
    )
    try:
        with Session(engine) as session:
            with pytest.raises(HttpRequestFailed):
                await CollectionService(session, now=lambda: next(moments)).run(
                    FailingCollector(), as_of=AS_OF, run_key="wikimedia:durable-failure"
                )
            session.rollback()

        with Session(engine) as verification:
            run = verification.scalar(select(CollectionRun))
            assert run is not None
            assert run.status is RunStatus.FAILED
            assert run.started_at == datetime(2026, 9, 20, 12, 0, 1)
            assert run.completed_at == datetime(2026, 9, 20, 12, 0, 9)
            assert run.error_code == "TIMEOUT"
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.mark.asyncio
async def test_failed_retry_does_not_downgrade_a_succeeded_run(db_session) -> None:
    class FailingCollector:
        source = Source.GOOGLE_TRENDS

        async def collect(self, _as_of: datetime) -> CollectionBatch:
            raise HttpRequestFailed("TIMEOUT")

    service = CollectionService(db_session)
    service.persist(batch(), run_key="google:already-succeeded")
    db_session.commit()

    with pytest.raises(HttpRequestFailed):
        await service.run(FailingCollector(), as_of=AS_OF, run_key="google:already-succeeded")

    run = db_session.scalar(
        select(CollectionRun).where(CollectionRun.run_key == "google:already-succeeded")
    )
    assert run is not None
    assert run.status is RunStatus.SUCCEEDED
    assert run.error_code is None
