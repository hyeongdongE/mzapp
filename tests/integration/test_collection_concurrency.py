from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.collectors.base import CollectionBatch, SourceItem
from app.models.enums import Source
from app.models.tables import RawFetch, RawPayload, SourceObservation
from app.services.collection import CollectionService

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="TEST_DATABASE_URL is required for PostgreSQL concurrency verification",
)


def make_batch() -> CollectionBatch:
    acquired_at = datetime(2026, 9, 20, 15, 0, tzinfo=UTC)
    return CollectionBatch(
        source=Source.GOOGLE_TRENDS,
        collected_at=acquired_at,
        request_url="https://trends.google.com/trending/rss?geo=KR",
        raw_bytes=b"<rss><channel><title>concurrent</title></channel></rss>",
        items=[
            SourceItem(
                source_item_id="google:concurrent",
                source_timestamp=acquired_at,
                observed_at=acquired_at,
                canonical_text="concurrent",
                source_url="https://trends.google.com/trending/rss?geo=KR",
                metrics={},
            )
        ],
        collector_version="google-rss-v1",
        parser_version="google-rss-parser-v1",
    )


def test_concurrent_runs_share_raw_payload_without_integrity_failure() -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL)
    barrier = Barrier(2)

    def persist(run_key: str) -> None:
        with Session(engine) as session:
            barrier.wait()
            CollectionService(session).persist(make_batch(), run_key=run_key)
            session.commit()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(persist, f"concurrency:{index}") for index in range(2)]
        for future in futures:
            future.result(timeout=15)

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(RawPayload)) == 1
        assert session.scalar(select(func.count()).select_from(RawFetch)) == 2
        assert session.scalar(select(func.count()).select_from(SourceObservation)) == 2
    engine.dispose()
