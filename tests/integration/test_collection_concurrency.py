from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.collectors.base import CollectionBatch, SourceItem
from app.models.enums import RunStatus, Source
from app.models.tables import CollectionRun, RawFetch, RawPayload, SourceObservation
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


def test_concurrent_retries_resume_one_failed_run_idempotently() -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL)
    run_key = "concurrency:failed-retry"
    with Session(engine) as session:
        session.add(
            CollectionRun(
                run_key=run_key,
                source=Source.GOOGLE_TRENDS,
                started_at=datetime(2026, 9, 20, 14, 0, tzinfo=UTC),
                completed_at=datetime(2026, 9, 20, 14, 0, 1, tzinfo=UTC),
                status=RunStatus.FAILED,
                error_code="TIMEOUT",
            )
        )
        session.commit()
    barrier = Barrier(2)

    def retry() -> None:
        with Session(engine) as session:
            barrier.wait()
            CollectionService(session).persist(make_batch(), run_key=run_key)
            session.commit()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(retry) for _ in range(2)]
        for future in futures:
            future.result(timeout=15)

    with Session(engine) as session:
        run = session.scalar(select(CollectionRun).where(CollectionRun.run_key == run_key))
        assert run is not None
        assert run.status is RunStatus.SUCCEEDED
        assert run.error_code is None
        assert (
            session.scalar(
                select(func.count()).select_from(RawFetch).where(RawFetch.run_id == run.id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(SourceObservation)
                .where(SourceObservation.run_id == run.id)
            )
            == 1
        )
    engine.dispose()


def test_stale_failure_transaction_cannot_overwrite_committed_success() -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL)
    run_key = "concurrency:success-is-terminal"
    with Session(engine) as setup:
        setup.add(
            CollectionRun(
                run_key=run_key,
                source=Source.GOOGLE_TRENDS,
                started_at=datetime(2026, 9, 20, 14, 0, tzinfo=UTC),
                completed_at=datetime(2026, 9, 20, 14, 0, 1, tzinfo=UTC),
                status=RunStatus.FAILED,
                error_code="NETWORK_ERROR",
            )
        )
        setup.commit()

    with Session(engine) as stale_failure:
        stale_run = stale_failure.scalar(
            select(CollectionRun).where(CollectionRun.run_key == run_key)
        )
        assert stale_run is not None
        assert stale_run.status is RunStatus.FAILED

        with Session(engine) as success:
            successful_run = success.scalar(
                select(CollectionRun).where(CollectionRun.run_key == run_key)
            )
            assert successful_run is not None
            successful_run.status = RunStatus.SUCCEEDED
            successful_run.error_code = None
            success.commit()

        service = CollectionService(stale_failure)
        service._repo.find_run = lambda _run_key: stale_run
        service._record_failure(
            Source.GOOGLE_TRENDS,
            run_key,
            started_at=datetime(2026, 9, 20, 14, 0, tzinfo=UTC),
            completed_at=datetime(2026, 9, 20, 14, 0, 2, tzinfo=UTC),
            error_code="TIMEOUT",
        )
        stale_failure.commit()

    with Session(engine) as verification:
        run = verification.scalar(select(CollectionRun).where(CollectionRun.run_key == run_key))
        assert run is not None
        assert run.status is RunStatus.SUCCEEDED
        assert run.error_code is None
    engine.dispose()
