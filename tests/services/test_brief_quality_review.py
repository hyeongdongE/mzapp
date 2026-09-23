from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import (
    BriefItemUsefulness,
    BriefReviewSessionStatus,
    BriefStatus,
    ClusterStatus,
    DuplicateEscapeVerdict,
    EventSelectionVerdict,
    EvidenceSetUsefulness,
    FactCorrectness,
    IncorrectMergeVerdict,
    InterpretationQuality,
    MissingEventDiscoverySource,
    Source,
    VerbosityVerdict,
    WatchUsefulness,
)
from app.models.tables import (
    BriefItem,
    BriefItemReviewMergeMembership,
    BriefReviewActivityPulse,
    BriefReviewReopen,
    DailyBrief,
    EventCluster,
    EventClusterItem,
    MissingEventReview,
)
from app.services.brief_quality_review import (
    BriefQualityReviewService,
    ItemReviewInput,
    MissingEventInput,
    ReviewConflict,
)
from tests.intelligence.helpers import EvidenceSpec, seed_event

NOW = datetime(2026, 9, 23, 12, tzinfo=UTC)


def valid_item_review() -> ItemReviewInput:
    return ItemReviewInput(
        usefulness=BriefItemUsefulness.USEFUL,
        event_selection=EventSelectionVerdict.KEEP,
        fact_correctness=FactCorrectness.CORRECT,
        interpretation_quality=InterpretationQuality.STRONG,
        watch_usefulness=WatchUsefulness.USEFUL,
        verbosity=VerbosityVerdict.JUST_RIGHT,
        evidence_set_usefulness=EvidenceSetUsefulness.HELPFUL,
        incorrect_merge_verdict=IncorrectMergeVerdict.NO_INCORRECT_MERGE,
        duplicate_escape_verdict=DuplicateEscapeVerdict.NO_DUPLICATE_ESCAPE,
    )


def seed_brief(session: Session, *, status: BriefStatus = BriefStatus.PUBLISHED) -> DailyBrief:
    sequence = int(session.scalar(select(func.count()).select_from(EventCluster)) or 0) + 1
    cluster = EventCluster(
        public_id=f"quality-cluster-{sequence}",
        canonical_title="Quality event",
        first_seen_at=NOW,
        last_seen_at=NOW,
        status=ClusterStatus.ACTIVE,
        clustering_version="cluster-v1",
    )
    session.add(cluster)
    session.flush()
    brief = DailyBrief(
        brief_date=date(2026, 9, 23),
        version=sequence,
        status=status,
        window_start=NOW,
        window_end=NOW,
        generated_at=NOW,
        published_at=NOW if status is BriefStatus.PUBLISHED else None,
        selected_count=1,
        generation_version="brief-v1",
        pipeline_version="intelligence-pipeline-v1",
    )
    session.add(brief)
    session.flush()
    session.add(
        BriefItem(
            brief_id=brief.id,
            event_cluster_id=cluster.id,
            position=1,
            headline="Headline",
            category="AI_TECH",
            what_happened="What",
            why_it_matters="Why",
            fact_text="Fact",
            interpretation_text="Interpretation",
            watch_text="Watch",
            source_links=[],
            importance=80,
        )
    )
    session.flush()
    return brief


def test_session_start_is_idempotent_and_requires_published_brief(db_session: Session) -> None:
    published = seed_brief(db_session)
    service = BriefQualityReviewService(db_session)

    first = service.start_session(published.id, "owner", now=NOW)
    second = service.start_session(published.id, "owner", now=NOW)

    assert first.id == second.id
    assert first.status is BriefReviewSessionStatus.OPEN
    draft = seed_brief(db_session, status=BriefStatus.DRAFT)
    with pytest.raises(ReviewConflict, match="PUBLISHED"):
        service.start_session(draft.id, "owner", now=NOW)


def test_activity_pulses_are_bounded_idempotent_and_summed(db_session: Session) -> None:
    brief = seed_brief(db_session)
    service = BriefQualityReviewService(db_session)
    review = service.start_session(brief.id, "owner", now=NOW)

    assert service.record_activity_pulse(review.id, "pulse-1", 15, now=NOW)
    assert not service.record_activity_pulse(review.id, "pulse-1", 15, now=NOW)
    assert service.record_activity_pulse(review.id, "pulse-2", 7, now=NOW)
    assert service.active_review_seconds(review.id) == 22
    assert db_session.scalar(select(func.count()).select_from(BriefReviewActivityPulse)) == 2
    for invalid in (0, 31):
        with pytest.raises(ValueError, match="1 through 30"):
            service.record_activity_pulse(review.id, f"bad-{invalid}", invalid, now=NOW)


def test_completed_session_is_immutable_until_explicit_reopen(db_session: Session) -> None:
    brief = seed_brief(db_session)
    item = db_session.scalar(select(BriefItem).where(BriefItem.brief_id == brief.id))
    assert item is not None
    service = BriefQualityReviewService(db_session)
    review = service.start_session(brief.id, "owner", now=NOW)
    service.upsert_item_review(review.id, item.id, valid_item_review(), now=NOW)
    service.set_missing_events_confirmed(review.id, True)
    service.record_activity_pulse(review.id, "pulse", 10, now=NOW)

    completed = service.complete_session(review.id, now=NOW)
    assert completed.status is BriefReviewSessionStatus.COMPLETED
    assert completed.completion_revision == 1
    with pytest.raises(ReviewConflict, match="completed"):
        service.set_missing_events_confirmed(review.id, False)

    reopened = service.reopen_session(
        review.id, actor="owner", reason="correct an assessment", now=NOW
    )
    assert reopened.status is BriefReviewSessionStatus.OPEN
    assert reopened.completed_at is None
    audit = db_session.scalar(select(BriefReviewReopen))
    assert audit is not None
    assert audit.reason == "correct an assessment"
    assert audit.previous_completion_revision == 1


def test_completion_rejects_incomplete_review(db_session: Session) -> None:
    brief = seed_brief(db_session)
    service = BriefQualityReviewService(db_session)
    review = service.start_session(brief.id, "owner", now=NOW)
    with pytest.raises(ReviewConflict, match="item review"):
        service.complete_session(review.id, now=NOW)


def test_structured_merge_and_duplicate_targets_enforce_cluster_ownership(
    db_session: Session,
) -> None:
    cluster = seed_event(
        db_session,
        [
            EvidenceSpec(Source.GEEKNEWS, "One"),
            EvidenceSpec(Source.HACKER_NEWS, "Two"),
        ],
        suffix="quality-merge",
    )
    other = seed_event(
        db_session,
        [EvidenceSpec(Source.GITHUB_RELEASES, "Other")],
        suffix="quality-other",
    )
    brief = DailyBrief(
        brief_date=date(2026, 9, 24),
        version=1,
        status=BriefStatus.PUBLISHED,
        window_start=NOW,
        window_end=NOW,
        generated_at=NOW,
        published_at=NOW,
        selected_count=1,
        generation_version="brief-v1",
        pipeline_version="intelligence-pipeline-v1",
    )
    db_session.add(brief)
    db_session.flush()
    item = BriefItem(
        brief_id=brief.id,
        event_cluster_id=cluster.id,
        position=1,
        headline="Merged event",
        category="AI_TECH",
        what_happened="What",
        why_it_matters="Why",
        fact_text="Fact",
        interpretation_text="Interpretation",
        watch_text="Watch",
        source_links=[],
        importance=80,
    )
    db_session.add(item)
    db_session.flush()
    memberships = list(
        db_session.scalars(
            select(EventClusterItem).where(EventClusterItem.event_cluster_id == cluster.id)
        )
    )
    wrong_membership = db_session.scalar(
        select(EventClusterItem).where(EventClusterItem.event_cluster_id == other.id)
    )
    assert wrong_membership is not None
    service = BriefQualityReviewService(db_session)
    review = service.start_session(brief.id, "owner", now=NOW)

    saved = service.upsert_item_review(
        review.id,
        item.id,
        replace(
            valid_item_review(),
            incorrect_merge_verdict=IncorrectMergeVerdict.INCORRECT_MERGE,
            incorrect_merge_membership_ids=(memberships[0].id,),
        ),
        now=NOW,
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(BriefItemReviewMergeMembership)
            .where(BriefItemReviewMergeMembership.brief_item_review_id == saved.id)
        )
        == 1
    )
    with pytest.raises(ReviewConflict, match="must belong"):
        service.upsert_item_review(
            review.id,
            item.id,
            replace(
                valid_item_review(),
                incorrect_merge_verdict=IncorrectMergeVerdict.INCORRECT_MERGE,
                incorrect_merge_membership_ids=(wrong_membership.id,),
            ),
            now=NOW,
        )
    with pytest.raises(ReviewConflict, match="structured target"):
        service.upsert_item_review(
            review.id,
            item.id,
            replace(
                valid_item_review(),
                duplicate_escape_verdict=DuplicateEscapeVerdict.DUPLICATE_ESCAPE,
            ),
            now=NOW,
        )


def test_missing_event_uses_independent_source_and_canonical_https_url(
    db_session: Session,
) -> None:
    brief = seed_brief(db_session)
    service = BriefQualityReviewService(db_session)
    review = service.start_session(brief.id, "owner", now=NOW)

    missing = service.add_missing_event(
        review.id,
        MissingEventInput(
            canonical_title="Uncovered launch",
            canonical_url="https://EXAMPLE.com/launch#discussion",
            discovered_from=MissingEventDiscoverySource.X,
            reason="Material release",
        ),
        now=NOW,
    )

    assert missing.canonical_url == "https://example.com/launch"
    assert missing.discovered_from is MissingEventDiscoverySource.X
    assert db_session.scalar(select(func.count()).select_from(MissingEventReview)) == 1
