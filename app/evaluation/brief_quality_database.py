from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.evaluation.brief_quality_models import (
    BriefQualityFacts,
    ExcludedDateFact,
    IncludedDateFact,
    ItemReviewFact,
    MissingEventFact,
    OperationalDateFact,
)
from app.models.enums import BriefReviewSessionStatus, BriefStatus
from app.models.tables import (
    BriefItem,
    BriefItemReview,
    BriefItemReviewMergeMembership,
    BriefReviewActivityPulse,
    BriefReviewSession,
    DailyBrief,
    EventAssessment,
    EventCluster,
    MissingEventReview,
)


def load_brief_quality_facts(
    session: Session, *, reviewer: str, start_date: date, end_date: date
) -> BriefQualityFacts:
    if start_date > end_date:
        raise ValueError("start_date must not be after end_date")
    briefs = list(
        session.scalars(
            select(DailyBrief)
            .where(DailyBrief.brief_date.between(start_date, end_date))
            .order_by(DailyBrief.brief_date, DailyBrief.version, DailyBrief.id)
        )
    )
    operational = tuple(
        OperationalDateFact(
            brief_id=brief.id,
            brief_date=brief.brief_date,
            brief_version=brief.version,
            status=brief.status.value,
        )
        for brief in briefs
    )
    by_date: dict[date, list[DailyBrief]] = defaultdict(list)
    for brief in briefs:
        by_date[brief.brief_date].append(brief)
    included: list[IncludedDateFact] = []
    excluded: list[ExcludedDateFact] = []
    for _, day_briefs in sorted(by_date.items()):
        published = [brief for brief in day_briefs if brief.status is BriefStatus.PUBLISHED]
        latest = max(published, key=lambda brief: (brief.version, brief.id)) if published else None
        for brief in day_briefs:
            if brief.status is not BriefStatus.PUBLISHED:
                excluded.append(_excluded(brief, brief.status.value))
            elif brief is not latest:
                excluded.append(_excluded(brief, "SUPERSEDED_PUBLISHED_VERSION"))
        if latest is None:
            continue
        result = _eligible_date(session, latest, reviewer)
        if isinstance(result, ExcludedDateFact):
            excluded.append(result)
        else:
            included.append(result)
    return BriefQualityFacts(
        reviewer=reviewer,
        start_date=start_date,
        end_date=end_date,
        operational_dates=operational,
        included_dates=tuple(included),
        excluded_dates=tuple(excluded),
    )


def _eligible_date(
    session: Session, brief: DailyBrief, reviewer: str
) -> IncludedDateFact | ExcludedDateFact:
    review = session.scalar(
        select(BriefReviewSession).where(
            BriefReviewSession.brief_id == brief.id,
            BriefReviewSession.reviewer == reviewer,
        )
    )
    if review is None or review.status is not BriefReviewSessionStatus.COMPLETED:
        return _excluded(brief, "LATEST_PUBLISHED_VERSION_UNREVIEWED")
    items = list(
        session.scalars(
            select(BriefItem)
            .where(BriefItem.brief_id == brief.id)
            .order_by(BriefItem.position, BriefItem.id)
        )
    )
    if not items:
        return _excluded(brief, "NO_REVIEWABLE_ITEMS")
    item_reviews = list(
        session.scalars(
            select(BriefItemReview)
            .where(BriefItemReview.session_id == review.id)
            .order_by(BriefItemReview.brief_item_id)
        )
    )
    if len(item_reviews) != len(items) or {value.brief_item_id for value in item_reviews} != {
        item.id for item in items
    }:
        return _excluded(brief, "INCOMPLETE_ITEM_REVIEWS")
    if not review.missing_events_confirmed:
        return _excluded(brief, "MISSING_EVENTS_NOT_CONFIRMED")
    active_seconds = int(
        session.scalar(
            select(func.coalesce(func.sum(BriefReviewActivityPulse.active_seconds), 0)).where(
                BriefReviewActivityPulse.session_id == review.id
            )
        )
        or 0
    )
    if active_seconds <= 0:
        return _excluded(brief, "ZERO_ACTIVE_REVIEW_TIME")
    cluster_ids = sorted({item.event_cluster_id for item in items})
    clusters = list(session.scalars(select(EventCluster).where(EventCluster.id.in_(cluster_ids))))
    assessments = list(
        session.scalars(
            select(EventAssessment).where(EventAssessment.event_cluster_id.in_(cluster_ids))
        )
    )
    clustering_versions = tuple(sorted({value.clustering_version for value in clusters}))
    assessment_versions = tuple(sorted({value.assessment_version for value in assessments}))
    if (
        not brief.pipeline_version
        or not brief.generation_version
        or len(clusters) != len(cluster_ids)
        or not clustering_versions
        or not assessment_versions
    ):
        return _excluded(brief, "MISSING_VERSION_PROVENANCE")
    membership_ids: dict[int, list[int]] = defaultdict(list)
    for review_id, membership_id in session.execute(
        select(
            BriefItemReviewMergeMembership.brief_item_review_id,
            BriefItemReviewMergeMembership.event_cluster_item_id,
        ).where(
            BriefItemReviewMergeMembership.brief_item_review_id.in_(
                [value.id for value in item_reviews]
            )
        )
    ):
        membership_ids[review_id].append(membership_id)
    item_by_id = {item.id: item for item in items}
    review_facts = tuple(
        ItemReviewFact(
            brief_item_review_id=value.id,
            brief_item_id=value.brief_item_id,
            event_cluster_id=item_by_id[value.brief_item_id].event_cluster_id,
            usefulness=value.usefulness.value,
            event_selection=value.event_selection.value,
            fact_correctness=value.fact_correctness.value,
            interpretation_quality=value.interpretation_quality.value,
            watch_usefulness=value.watch_usefulness.value,
            verbosity=value.verbosity.value,
            evidence_set_usefulness=value.evidence_set_usefulness.value,
            incorrect_merge_verdict=value.incorrect_merge_verdict.value,
            duplicate_escape_verdict=value.duplicate_escape_verdict.value,
            duplicate_of_brief_item_id=value.duplicate_of_brief_item_id,
            duplicate_of_event_cluster_id=value.duplicate_of_event_cluster_id,
            incorrect_merge_membership_ids=tuple(sorted(membership_ids[value.id])),
        )
        for value in item_reviews
    )
    missing_events = tuple(
        MissingEventFact(
            canonical_title=value.canonical_title,
            canonical_url=value.canonical_url,
            discovered_from=value.discovered_from.value,
            reason=value.reason,
        )
        for value in session.scalars(
            select(MissingEventReview)
            .where(MissingEventReview.session_id == review.id)
            .order_by(MissingEventReview.canonical_url)
        )
    )
    return IncludedDateFact(
        brief_id=brief.id,
        brief_date=brief.brief_date,
        brief_version=brief.version,
        pipeline_version=brief.pipeline_version,
        generation_version=brief.generation_version,
        clustering_versions=clustering_versions,
        assessment_versions=assessment_versions,
        active_review_seconds=active_seconds,
        item_reviews=review_facts,
        missing_events=missing_events,
    )


def _excluded(brief: DailyBrief, reason: str) -> ExcludedDateFact:
    return ExcludedDateFact(
        brief_id=brief.id,
        brief_date=brief.brief_date,
        brief_version=brief.version,
        status=brief.status.value,
        reason=reason,
    )
