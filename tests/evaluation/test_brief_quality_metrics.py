from __future__ import annotations

from datetime import UTC, date, datetime

from app.evaluation.brief_quality_metrics import aggregate_brief_quality
from app.evaluation.brief_quality_models import (
    BriefQualityFacts,
    IncludedDateFact,
    ItemReviewFact,
    MissingEventFact,
)


def item(
    *,
    useful: str,
    duplicate: str = "NO_DUPLICATE_ESCAPE",
    incorrect_merge: str = "NO_INCORRECT_MERGE",
) -> ItemReviewFact:
    return ItemReviewFact(
        brief_item_review_id=1,
        brief_item_id=10,
        event_cluster_id=20,
        usefulness=useful,
        event_selection="KEEP",
        fact_correctness="CORRECT",
        interpretation_quality="STRONG",
        watch_usefulness="ACTIONABLE",
        verbosity="JUST_RIGHT",
        evidence_set_usefulness="ESSENTIAL",
        incorrect_merge_verdict=incorrect_merge,
        duplicate_escape_verdict=duplicate,
        duplicate_of_brief_item_id=11 if duplicate == "DUPLICATE_ESCAPE" else None,
        duplicate_of_event_cluster_id=None,
        incorrect_merge_membership_ids=(31,) if incorrect_merge == "INCORRECT_MERGE" else (),
    )


def included(day: int, seconds: int, items: tuple[ItemReviewFact, ...]) -> IncludedDateFact:
    return IncludedDateFact(
        brief_id=day,
        brief_date=date(2026, 9, day),
        brief_version=1,
        pipeline_version="pipeline-v1",
        generation_version="generation-v1",
        clustering_versions=("cluster-v1",),
        assessment_versions=("assessment-v1",),
        active_review_seconds=seconds,
        item_reviews=items,
        missing_events=(
            MissingEventFact(
                canonical_title="Missing",
                canonical_url="https://example.com/missing",
                discovered_from="REDDIT",
                reason="important",
            ),
        ),
    )


def test_metrics_preserve_denominators_distributions_links_and_percentiles() -> None:
    facts = BriefQualityFacts(
        reviewer="owner",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 5),
        operational_dates=(),
        included_dates=tuple(
            included(day, seconds, (item(useful="USEFUL" if day < 5 else "NOT_USEFUL"),))
            for day, seconds in zip(range(1, 6), (10, 20, 30, 40, 50), strict=True)
        ),
        excluded_dates=(),
    )

    report = aggregate_brief_quality(facts, generated_at=datetime(2026, 9, 24, tzinfo=UTC))

    assert report.sample_status == "VALIDATION_SAMPLE_COMPLETE"
    assert report.metrics.useful_brief_rate.numerator == 4
    assert report.metrics.useful_brief_rate.denominator == 5
    assert report.metrics.useful_brief_rate.rate == 0.8
    assert report.metrics.fact_correctness == {"CORRECT": 5}
    assert report.metrics.missing_event_discovery_sources == {"REDDIT": 5}
    assert report.metrics.active_review_seconds_p50 == 30
    assert report.metrics.active_review_seconds_p95 == 50
    assert report.metrics.missing_events_per_day["2026-09-01"] == 1


def test_zero_denominator_is_none_and_not_quality_pass() -> None:
    facts = BriefQualityFacts(
        reviewer="owner",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 1),
        operational_dates=(),
        included_dates=(),
        excluded_dates=(),
    )
    report = aggregate_brief_quality(facts, generated_at=datetime(2026, 9, 24, tzinfo=UTC))
    assert report.sample_status == "INSUFFICIENT_VALIDATION_DAYS"
    assert report.metrics.useful_brief_rate.rate is None


def test_structured_defects_keep_linked_targets() -> None:
    defect = item(
        useful="NOT_USEFUL",
        duplicate="DUPLICATE_ESCAPE",
        incorrect_merge="INCORRECT_MERGE",
    )
    facts = BriefQualityFacts(
        reviewer="owner",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 1),
        operational_dates=(),
        included_dates=(included(1, 10, (defect,)),),
        excluded_dates=(),
    )
    report = aggregate_brief_quality(facts, generated_at=datetime(2026, 9, 24, tzinfo=UTC))
    assert report.metrics.incorrect_merge.numerator == 1
    assert report.metrics.incorrect_merge_links[0]["eventClusterItemIds"] == [31]
    assert report.metrics.duplicate_escape.numerator == 1
    assert report.metrics.duplicate_escape_links[0]["duplicateOfBriefItemId"] == 11
