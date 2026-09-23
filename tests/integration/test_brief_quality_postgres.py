from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.tables import (
    Base,
    BriefItem,
    BriefReviewActivityPulse,
    BriefReviewReopen,
    BriefReviewSession,
)
from app.services.brief_quality_review import BriefQualityReviewService, ReviewConflict
from tests.services.test_brief_quality_review import NOW, seed_brief, valid_item_review

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="TEST_DATABASE_URL is required for PostgreSQL review concurrency verification",
)


@pytest.fixture(autouse=True)
def reset_postgres_schema():
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def _seed_open_review(engine) -> tuple[int, int]:
    with Session(engine) as session:
        brief = seed_brief(session)
        item = session.scalar(select(BriefItem).where(BriefItem.brief_id == brief.id))
        assert item is not None
        review = BriefQualityReviewService(session).start_session(brief.id, "owner", now=NOW)
        session.commit()
        return review.id, item.id


def test_simultaneous_pulse_replay_is_idempotent(reset_postgres_schema) -> None:
    engine = reset_postgres_schema
    review_id, _ = _seed_open_review(engine)

    def record() -> bool:
        with Session(engine) as session:
            created = BriefQualityReviewService(session).record_activity_pulse(
                review_id, "same-event", 10, now=NOW
            )
            session.commit()
            return created

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = sorted((executor.submit(record), executor.submit(record)), key=id)
        values = [future.result(timeout=10) for future in results]

    assert sorted(values) == [False, True]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(BriefReviewActivityPulse)) == 1


def test_completion_serializes_against_item_edit(reset_postgres_schema) -> None:
    engine = reset_postgres_schema
    review_id, item_id = _seed_open_review(engine)
    with Session(engine) as session:
        service = BriefQualityReviewService(session)
        service.upsert_item_review(review_id, item_id, valid_item_review(), now=NOW)
        service.set_missing_events_confirmed(review_id, True)
        service.record_activity_pulse(review_id, "complete", 10, now=NOW)
        session.commit()

    first_locked = threading.Event()
    release = threading.Event()

    def complete() -> None:
        with Session(engine) as session:
            BriefQualityReviewService(session).complete_session(review_id, now=NOW)
            first_locked.set()
            assert release.wait(10)
            session.commit()

    def edit() -> str:
        assert first_locked.wait(10)
        with Session(engine) as session, pytest.raises(ReviewConflict, match="completed"):
            BriefQualityReviewService(session).upsert_item_review(
                review_id, item_id, valid_item_review(), now=NOW
            )
        return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        completed = executor.submit(complete)
        edited = executor.submit(edit)
        assert first_locked.wait(10)
        release.set()
        completed.result(timeout=10)
        assert edited.result(timeout=10) == "rejected"


def test_reopen_serializes_edit_and_persists_across_engine_restart(
    reset_postgres_schema,
) -> None:
    engine = reset_postgres_schema
    review_id, item_id = _seed_open_review(engine)
    with Session(engine) as session:
        service = BriefQualityReviewService(session)
        service.upsert_item_review(review_id, item_id, valid_item_review(), now=NOW)
        service.set_missing_events_confirmed(review_id, True)
        service.record_activity_pulse(review_id, "complete", 10, now=NOW)
        service.complete_session(review_id, now=NOW)
        session.commit()

    first_locked = threading.Event()
    release = threading.Event()

    def reopen() -> None:
        with Session(engine) as session:
            BriefQualityReviewService(session).reopen_session(
                review_id,
                actor="owner",
                reason="correct evidence judgment",
                now=datetime(2026, 9, 24, tzinfo=UTC),
            )
            first_locked.set()
            assert release.wait(10)
            session.commit()

    def edit_after_reopen() -> None:
        assert first_locked.wait(10)
        with Session(engine) as session:
            BriefQualityReviewService(session).upsert_item_review(
                review_id, item_id, valid_item_review(), now=NOW
            )
            session.commit()

    with ThreadPoolExecutor(max_workers=2) as executor:
        reopened = executor.submit(reopen)
        edited = executor.submit(edit_after_reopen)
        assert first_locked.wait(10)
        release.set()
        reopened.result(timeout=10)
        edited.result(timeout=10)
    engine.dispose()

    restarted = create_engine(TEST_DATABASE_URL)
    with Session(restarted) as session:
        review = session.get(BriefReviewSession, review_id)
        audit = session.scalar(
            select(BriefReviewReopen).where(BriefReviewReopen.session_id == review_id)
        )
        assert review is not None and review.completed_at is None
        assert audit is not None and audit.reason == "correct evidence judgment"
        session.add(
            BriefReviewActivityPulse(
                session_id=review_id,
                client_event_id="invalid-bound",
                active_seconds=31,
                recorded_at=NOW,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
    restarted.dispose()
