from __future__ import annotations

from collections import Counter
from datetime import datetime
from math import ceil

from app.evaluation.brief_quality_models import (
    BriefQualityFacts,
    BriefQualityMetrics,
    BriefQualityReport,
    RateMetric,
)

REPORT_SCHEMA_VERSION = "brief-quality-report-v1"


def aggregate_brief_quality(
    facts: BriefQualityFacts, *, generated_at: datetime
) -> BriefQualityReport:
    items = [item for day in facts.included_dates for item in day.item_reviews]
    useful = sum(item.usefulness == "USEFUL" for item in items)
    incorrect = [item for item in items if item.incorrect_merge_verdict == "INCORRECT_MERGE"]
    duplicates = [item for item in items if item.duplicate_escape_verdict == "DUPLICATE_ESCAPE"]
    seconds = [day.active_review_seconds for day in facts.included_dates]
    missing = [event for day in facts.included_dates for event in day.missing_events]
    metrics = BriefQualityMetrics(
        useful_brief_rate=_rate(useful, len(items)),
        event_selection=_distribution(item.event_selection for item in items),
        fact_correctness=_distribution(item.fact_correctness for item in items),
        interpretation_quality=_distribution(item.interpretation_quality for item in items),
        watch_usefulness=_distribution(item.watch_usefulness for item in items),
        verbosity=_distribution(item.verbosity for item in items),
        evidence_set_usefulness=_distribution(item.evidence_set_usefulness for item in items),
        incorrect_merge=_rate(len(incorrect), len(items)),
        incorrect_merge_links=tuple(
            {
                "briefItemReviewId": item.brief_item_review_id,
                "eventClusterId": item.event_cluster_id,
                "eventClusterItemIds": list(item.incorrect_merge_membership_ids),
            }
            for item in incorrect
        ),
        duplicate_escape=_rate(len(duplicates), len(items)),
        duplicate_escape_links=tuple(
            {
                "briefItemReviewId": item.brief_item_review_id,
                "briefItemId": item.brief_item_id,
                "duplicateOfBriefItemId": item.duplicate_of_brief_item_id,
                "duplicateOfEventClusterId": item.duplicate_of_event_cluster_id,
            }
            for item in duplicates
        ),
        missing_events_per_day={
            day.brief_date.isoformat(): len(day.missing_events) for day in facts.included_dates
        },
        missing_event_discovery_sources=_distribution(event.discovered_from for event in missing),
        active_review_seconds_by_day={
            day.brief_date.isoformat(): day.active_review_seconds for day in facts.included_dates
        },
        active_review_seconds_p50=_percentile(seconds, 0.50),
        active_review_seconds_p95=_percentile(seconds, 0.95),
        reviewed_brief_count=len(facts.included_dates),
        reviewed_date_count=len({day.brief_date for day in facts.included_dates}),
        reviewed_item_count=len(items),
    )
    return BriefQualityReport(
        report_schema_version=REPORT_SCHEMA_VERSION,
        generated_at=generated_at,
        reviewer=facts.reviewer,
        start_date=facts.start_date,
        end_date=facts.end_date,
        sample_status=(
            "VALIDATION_SAMPLE_COMPLETE"
            if metrics.reviewed_date_count >= 5
            else "INSUFFICIENT_VALIDATION_DAYS"
        ),
        pipeline_versions=_versions(day.pipeline_version for day in facts.included_dates),
        generation_versions=_versions(day.generation_version for day in facts.included_dates),
        clustering_versions=_versions(
            value for day in facts.included_dates for value in day.clustering_versions
        ),
        assessment_versions=_versions(
            value for day in facts.included_dates for value in day.assessment_versions
        ),
        operational_dates=facts.operational_dates,
        included_dates=facts.included_dates,
        excluded_dates=facts.excluded_dates,
        metrics=metrics,
    )


def _rate(numerator: int, denominator: int) -> RateMetric:
    return RateMetric(
        numerator=numerator,
        denominator=denominator,
        rate=None if denominator == 0 else numerator / denominator,
    )


def _distribution(values) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(1, ceil(percentile * len(ordered))) - 1]


def _versions(values) -> tuple[str, ...]:
    return tuple(sorted(set(values)))
