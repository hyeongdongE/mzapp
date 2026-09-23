from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evaluation.brief_quality_database import load_brief_quality_facts
from app.models.enums import BriefStatus, EvidenceConfidence
from app.models.tables import BriefItem, BriefReviewSession, EventAssessment
from tests.evaluation.test_brief_quality_report import complete_review
from tests.services.test_brief_quality_review import NOW, seed_brief


def add_assessment(session: Session, brief_id: int) -> None:
    item = session.scalar(select(BriefItem).where(BriefItem.brief_id == brief_id))
    assert item is not None
    session.add(
        EventAssessment(
            event_cluster_id=item.event_cluster_id,
            confidence=EvidenceConfidence.STRONG,
            confidence_breakdown={},
            importance=80,
            importance_breakdown={},
            assessment_version="assessment-v1",
            assessed_at=NOW,
        )
    )
    session.flush()


def test_loader_uses_latest_published_and_never_falls_back(db_session: Session) -> None:
    older = seed_brief(db_session)
    complete_review(db_session, older.id)
    latest = seed_brief(db_session)

    facts = load_brief_quality_facts(
        db_session,
        reviewer="owner",
        start_date=date(2026, 9, 23),
        end_date=date(2026, 9, 23),
    )

    assert facts.included_dates == ()
    assert [(row.brief_id, row.reason) for row in facts.excluded_dates] == [
        (older.id, "SUPERSEDED_PUBLISHED_VERSION"),
        (latest.id, "LATEST_PUBLISHED_VERSION_UNREVIEWED"),
    ]


def test_loader_keeps_low_signal_day_in_operational_record(db_session: Session) -> None:
    low_signal = seed_brief(db_session, status=BriefStatus.LOW_SIGNAL_DAY)

    facts = load_brief_quality_facts(
        db_session,
        reviewer="owner",
        start_date=date(2026, 9, 23),
        end_date=date(2026, 9, 23),
    )

    assert [(row.brief_id, row.status) for row in facts.operational_dates] == [
        (low_signal.id, "LOW_SIGNAL_DAY")
    ]
    assert facts.excluded_dates[0].reason == "LOW_SIGNAL_DAY"


def test_loader_isolates_reviewer_and_rejects_missing_version_provenance(
    db_session: Session,
) -> None:
    brief = seed_brief(db_session)
    complete_review(db_session, brief.id, reviewer="other")
    facts = load_brief_quality_facts(
        db_session,
        reviewer="owner",
        start_date=date(2026, 9, 23),
        end_date=date(2026, 9, 23),
    )
    assert facts.excluded_dates[-1].reason == "LATEST_PUBLISHED_VERSION_UNREVIEWED"

    review = db_session.scalar(
        select(BriefReviewSession).where(BriefReviewSession.brief_id == brief.id)
    )
    assert review is not None
    review.reviewer = "owner"
    brief.pipeline_version = ""
    db_session.flush()
    facts = load_brief_quality_facts(
        db_session,
        reviewer="owner",
        start_date=date(2026, 9, 23),
        end_date=date(2026, 9, 23),
    )
    assert facts.excluded_dates[-1].reason == "MISSING_VERSION_PROVENANCE"


def test_loader_includes_only_complete_versioned_review(db_session: Session) -> None:
    brief = seed_brief(db_session)
    add_assessment(db_session, brief.id)
    complete_review(db_session, brief.id)

    facts = load_brief_quality_facts(
        db_session,
        reviewer="owner",
        start_date=date(2026, 9, 23),
        end_date=date(2026, 9, 23),
    )

    assert len(facts.included_dates) == 1
    included = facts.included_dates[0]
    assert included.pipeline_version == "intelligence-pipeline-v1"
    assert included.clustering_versions == ("cluster-v1",)
    assert included.assessment_versions == ("assessment-v1",)
    assert included.active_review_seconds == 12


def test_loader_uses_published_item_assessment_snapshot_not_later_assessment(
    db_session: Session,
) -> None:
    brief = seed_brief(db_session)
    add_assessment(db_session, brief.id)
    item = db_session.scalar(select(BriefItem).where(BriefItem.brief_id == brief.id))
    assert item is not None
    item.assessment_version = "assessment-v1"
    db_session.add(
        EventAssessment(
            event_cluster_id=item.event_cluster_id,
            confidence=EvidenceConfidence.STRONG,
            confidence_breakdown={},
            importance=90,
            importance_breakdown={},
            assessment_version="assessment-v2",
            assessed_at=NOW.replace(hour=13),
        )
    )
    complete_review(db_session, brief.id)

    facts = load_brief_quality_facts(
        db_session,
        reviewer="owner",
        start_date=date(2026, 9, 23),
        end_date=date(2026, 9, 23),
    )

    assert facts.included_dates[0].assessment_versions == ("assessment-v1",)
