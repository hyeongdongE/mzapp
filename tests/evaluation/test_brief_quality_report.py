from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.evaluation.brief_quality_reports import build_brief_quality_report
from app.models.enums import BriefStatus
from app.models.tables import BriefItem
from app.services.brief_quality_review import BriefQualityReviewService
from tests.services.test_brief_quality_review import NOW, seed_brief, valid_item_review


def complete_review(session: Session, brief_id: int, reviewer: str = "owner") -> None:
    item = session.query(BriefItem).filter_by(brief_id=brief_id).one()
    assert item is not None
    service = BriefQualityReviewService(session)
    review = service.start_session(brief_id, reviewer, now=NOW)
    service.upsert_item_review(review.id, item.id, valid_item_review(), now=NOW)
    service.set_missing_events_confirmed(review.id, True)
    service.record_activity_pulse(review.id, "pulse", 12, now=NOW)
    service.complete_session(review.id, now=NOW)


def test_latest_published_unreviewed_does_not_fall_back(db_session: Session) -> None:
    old = seed_brief(db_session)
    complete_review(db_session, old.id)
    latest = seed_brief(db_session)

    report = build_brief_quality_report(
        db_session, reviewer="owner", start_date=date(2026, 9, 23), end_date=date(2026, 9, 23)
    )

    assert report["includedDates"] == []
    latest_exclusion = next(row for row in report["excludedDates"] if row["briefId"] == latest.id)
    assert latest_exclusion["reason"] == "LATEST_PUBLISHED_VERSION_UNREVIEWED"


def test_low_signal_day_is_operational_but_not_quality_denominator(db_session: Session) -> None:
    seed_brief(db_session, status=BriefStatus.LOW_SIGNAL_DAY)
    report = build_brief_quality_report(
        db_session, reviewer="owner", start_date=date(2026, 9, 23), end_date=date(2026, 9, 23)
    )
    assert report["operationalDates"][0]["status"] == "LOW_SIGNAL_DAY"
    assert report["metrics"]["usefulBriefRate"]["denominator"] == 0
    assert report["sampleStatus"] == "INSUFFICIENT_VALIDATION_DAYS"
