from __future__ import annotations

from collections import Counter
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import BriefItemUsefulness, BriefReviewSessionStatus, BriefStatus
from app.models.tables import (
    BriefItem,
    BriefItemReview,
    BriefReviewActivityPulse,
    BriefReviewSession,
    DailyBrief,
)

REPORT_SCHEMA_VERSION = "brief-quality-report-v1"


def build_brief_quality_report(
    session: Session, *, reviewer: str, start_date: date, end_date: date
) -> dict:
    if start_date > end_date:
        raise ValueError("start_date must not be after end_date")
    briefs = list(
        session.scalars(
            select(DailyBrief)
            .where(DailyBrief.brief_date.between(start_date, end_date))
            .order_by(DailyBrief.brief_date, DailyBrief.version)
        )
    )
    operational = [
        {"briefId": brief.id, "date": brief.brief_date.isoformat(), "status": brief.status.value}
        for brief in briefs
    ]
    latest_published: dict[date, DailyBrief] = {}
    for brief in briefs:
        if brief.status is BriefStatus.PUBLISHED:
            latest_published[brief.brief_date] = brief
    included: list[dict] = []
    excluded: list[dict] = []
    reviews: list[BriefItemReview] = []
    active_by_date: dict[str, int] = {}
    for day, brief in sorted(latest_published.items()):
        review = session.scalar(
            select(BriefReviewSession).where(
                BriefReviewSession.brief_id == brief.id,
                BriefReviewSession.reviewer == reviewer,
                BriefReviewSession.status == BriefReviewSessionStatus.COMPLETED,
            )
        )
        if review is None:
            excluded.append(_excluded(brief, "LATEST_PUBLISHED_VERSION_UNREVIEWED"))
            continue
        item_count = int(
            session.scalar(
                select(func.count()).select_from(BriefItem).where(BriefItem.brief_id == brief.id)
            )
            or 0
        )
        item_reviews = list(
            session.scalars(select(BriefItemReview).where(BriefItemReview.session_id == review.id))
        )
        active = int(
            session.scalar(
                select(func.coalesce(func.sum(BriefReviewActivityPulse.active_seconds), 0)).where(
                    BriefReviewActivityPulse.session_id == review.id
                )
            )
            or 0
        )
        if (
            item_count == 0
            or len(item_reviews) != item_count
            or not review.missing_events_confirmed
            or active <= 0
        ):
            excluded.append(_excluded(brief, "INCOMPLETE_REVIEW"))
            continue
        included.append({"briefId": brief.id, "date": day.isoformat(), "version": brief.version})
        reviews.extend(item_reviews)
        active_by_date[day.isoformat()] = active
    usefulness = Counter(item.usefulness.value for item in reviews)
    denominator = len(reviews)
    numerator = usefulness[BriefItemUsefulness.USEFUL.value]
    return {
        "reportSchemaVersion": REPORT_SCHEMA_VERSION,
        "reviewer": reviewer,
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "sampleStatus": (
            "VALIDATION_SAMPLE_COMPLETE" if len(included) >= 5 else "INSUFFICIENT_VALIDATION_DAYS"
        ),
        "operationalDates": operational,
        "includedDates": included,
        "excludedDates": excluded,
        "metrics": {
            "usefulBriefRate": {
                "numerator": numerator,
                "denominator": denominator,
                "rate": None if denominator == 0 else numerator / denominator,
            },
            "usefulnessDistribution": dict(sorted(usefulness.items())),
            "activeReviewSecondsByDate": active_by_date,
        },
    }


def _excluded(brief: DailyBrief, reason: str) -> dict:
    return {
        "briefId": brief.id,
        "date": brief.brief_date.isoformat(),
        "status": brief.status.value,
        "reason": reason,
    }
