from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.collectors.base import CollectionBatch, HttpRequestFailed, SourceItem
from app.models.enums import RunStatus, Source
from app.models.tables import CollectionRun, RawPayload, SourceObservation
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
