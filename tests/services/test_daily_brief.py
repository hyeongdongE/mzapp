from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import func, select

from app.intelligence.assessment import AssessmentService
from app.intelligence.facts import FactBuilder
from app.intelligence.sources import required_source_keys
from app.models.enums import BriefStatus, Source
from app.models.tables import BriefItem, BriefItemFact, DailyBrief, SourceHealth
from app.services.daily_brief import DailyBriefService
from tests.intelligence.helpers import EvidenceSpec, seed_event

BRIEF_DATE = date(2026, 9, 24)
GENERATION_TIME = datetime(2026, 9, 24, 0, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 9, 23, 22, 30, tzinfo=UTC)


def seed_health(db_session, *, stale_source: Source | None = None) -> None:
    for source in required_source_keys():
        covered_through = (
            datetime(2026, 9, 23, 0, 0, tzinfo=UTC)
            if source is stale_source
            else WINDOW_END
        )
        db_session.add(
            SourceHealth(
                source=source,
                last_attempt_at=GENERATION_TIME,
                last_success_at=GENERATION_TIME,
                last_failure_at=None,
                consecutive_failures=0,
                last_error_code=None,
                freshness_state="FRESH",
                covered_through=covered_through,
            )
        )
    db_session.flush()


def seed_qualifying_events(db_session, count: int) -> list[int]:
    event_ids = []
    for index in range(1, count + 1):
        event = seed_event(
            db_session,
            [
                EvidenceSpec(
                    Source.GITHUB_RELEASES,
                    f"Critical security release {index}.0",
                    metadata={
                        "repository": f"acme/tool-{index}",
                        "release_tag": f"v{index}.0",
                    },
                ),
                EvidenceSpec(
                    Source.OFFICIAL_AWS,
                    f"Critical security release {index}.0 support",
                ),
            ],
            suffix=f"brief-event-{index}",
        )
        FactBuilder(db_session).build(event.id)
        AssessmentService(db_session).assess(event.id, version="assessment-v1")
        event_ids.append(event.id)
    return event_ids


def test_healthy_sources_allow_two_item_low_signal_brief(db_session) -> None:
    seed_health(db_session)
    seed_qualifying_events(db_session, 2)

    result = DailyBriefService(db_session).generate(
        BRIEF_DATE, now=GENERATION_TIME, version="brief-v1"
    )

    assert result.status is BriefStatus.LOW_SIGNAL_DAY
    assert result.item_count == 2
    assert result.published_at == GENERATION_TIME


def test_stale_required_source_blocks_publication(db_session) -> None:
    seed_health(db_session, stale_source=Source.HACKER_NEWS)
    seed_qualifying_events(db_session, 6)

    result = DailyBriefService(db_session).generate(
        BRIEF_DATE, now=GENERATION_TIME, version="brief-v1"
    )

    assert result.status is BriefStatus.DEGRADED_SOURCE_COVERAGE
    assert result.published_at is None
    assert result.item_count == 0


def test_normal_brief_snapshots_exact_fact_and_evidence_pairs(db_session) -> None:
    seed_health(db_session)
    seed_qualifying_events(db_session, 4)

    result = DailyBriefService(db_session).generate(
        BRIEF_DATE, now=GENERATION_TIME, version="brief-v1"
    )

    assert result.status is BriefStatus.PUBLISHED
    assert 3 <= result.item_count <= 7
    assert result.reading_time_seconds <= 300
    assert db_session.scalar(select(func.count()).select_from(BriefItemFact)) > 0
    snapshots = db_session.scalars(select(BriefItemFact)).all()
    assert all(snapshot.event_fact_id and snapshot.event_evidence_id for snapshot in snapshots)


def test_repeat_generation_does_not_mutate_published_version(db_session) -> None:
    seed_health(db_session)
    seed_qualifying_events(db_session, 3)
    service = DailyBriefService(db_session)

    first = service.generate(BRIEF_DATE, now=GENERATION_TIME, version="brief-v1")
    first_count = db_session.scalar(select(func.count()).select_from(BriefItemFact))
    second = service.generate(BRIEF_DATE, now=GENERATION_TIME, version="brief-v1")

    assert second.brief_id == first.brief_id
    assert db_session.scalar(select(func.count()).select_from(DailyBrief)) == 1
    assert db_session.scalar(select(func.count()).select_from(BriefItemFact)) == first_count


def test_explicit_correction_version_can_snapshot_same_event_again(db_session) -> None:
    seed_health(db_session)
    seed_qualifying_events(db_session, 1)
    service = DailyBriefService(db_session)
    first = service.generate(BRIEF_DATE, now=GENERATION_TIME, version="brief-v1")

    corrected = service.generate(BRIEF_DATE, now=GENERATION_TIME, version="brief-v2")

    assert corrected.brief_id != first.brief_id
    assert corrected.version == 2
    assert corrected.item_count == 1
    assert db_session.scalar(select(func.count()).select_from(DailyBrief)) == 2


def test_already_briefed_event_is_suppressed_from_next_window(db_session) -> None:
    seed_health(db_session)
    event_ids = seed_qualifying_events(db_session, 1)
    service = DailyBriefService(db_session)
    first = service.generate(BRIEF_DATE, now=GENERATION_TIME, version="brief-v1")
    assert first.item_count == 1

    next_date = date(2026, 9, 25)
    for health in db_session.scalars(select(SourceHealth)):
        health.covered_through = datetime(2026, 9, 24, 22, 30, tzinfo=UTC)
    second = service.generate(
        next_date,
        now=datetime(2026, 9, 25, 0, 0, tzinfo=UTC),
        version="brief-v1",
    )

    assert second.item_count == 0
    assert db_session.scalar(
        select(func.count()).select_from(BriefItem).where(
            BriefItem.event_cluster_id == event_ids[0]
        )
    ) == 1


def test_old_backfill_is_excluded_even_when_first_seen_is_recent(db_session) -> None:
    seed_health(db_session)
    event = seed_event(
        db_session,
        [EvidenceSpec(Source.OFFICIAL_AWS, "Critical old security release")],
        suffix="old-backfill",
    )
    event.first_seen_at = GENERATION_TIME
    for item in event_ids_raw_items(db_session, event.id):
        item.published_at = datetime(2026, 8, 1, tzinfo=UTC)
    FactBuilder(db_session).build(event.id)
    AssessmentService(db_session).assess(event.id, version="assessment-v1")

    result = DailyBriefService(db_session).generate(
        BRIEF_DATE, now=GENERATION_TIME, version="brief-v1"
    )

    assert result.item_count == 0
    assert result.status is BriefStatus.LOW_SIGNAL_DAY


def event_ids_raw_items(db_session, event_id: int):
    from app.models.tables import EventClusterItem, RawItem

    return db_session.scalars(
        select(RawItem)
        .join(EventClusterItem, EventClusterItem.raw_item_id == RawItem.id)
        .where(EventClusterItem.event_cluster_id == event_id)
    ).all()
