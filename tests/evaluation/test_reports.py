from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.evaluation.models import (
    CategoryCoverage,
    CostMetrics,
    CrossSourceMetrics,
    DailyEvaluation,
    FreshnessMetrics,
    QualityMetrics,
    SupplyMetrics,
)
from app.evaluation.reports import (
    aggregate_week,
    render_daily_markdown,
    render_weekly_markdown,
    write_report_atomic,
)
from app.models.enums import Category


def daily_fixture(
    day: date, *, reviewed: int = 0, complete_day: bool = True
) -> DailyEvaluation:
    rate = Decimal("1.0000") if reviewed else None
    return DailyEvaluation(
        day=day,
        complete_day=complete_day,
        supply=SupplyMetrics(10, 8, 6, 2),
        coverage={
            category: CategoryCoverage(
                candidates=1 if category is Category.SPORTS else 0,
                valid_cards=1 if category is Category.SPORTS else 0,
            )
            for category in Category
        },
        quality=QualityMetrics(
            reviewed=reviewed,
            valid_trends=reviewed,
            duplicates=0,
            noise_items=0,
            news_only_items=0,
            classification_errors=0,
            merge_errors=0,
            precision=rate,
            duplicate_rate=None,
            noise_rate=None,
            news_only_rate=None,
            classification_error_rate=None,
            merge_error_rate=None,
            checked_claims=0,
            blocked_claims=0,
            unsupported_summary_rate=None,
        ),
        cross_source=CrossSourceMetrics(2, 1, Decimal("0.5000")),
        freshness=FreshnessMetrics(
            detection_samples=0,
            detection_p50_minutes=None,
            detection_p95_minutes=None,
            approval_samples=0,
            approval_p50_minutes=None,
            approval_p95_minutes=None,
            detection_minutes=(),
            approval_minutes=(),
        ),
        cost=CostMetrics(
            total_cost=Decimal("1.000000"),
            human_minutes=3,
            cost_per_approved_card=Decimal("0.500000"),
            by_type={"API": Decimal("1.000000")},
        ),
        top_noise_sources=(("NEWS_ONLY", 2),),
        versions={"score": ("score-v1",), "prompt": ("prompt-v1",)},
        decision="CONTINUE_DATA_COLLECTION",
        missing_denominators=("quality", "freshness"),
    )


def test_daily_report_is_deterministic_complete_and_renders_na() -> None:
    report = render_daily_markdown(daily_fixture(date(2026, 9, 20)))

    assert "# Trend Radar Daily Evaluation — 2026-09-20" in report
    assert "Decision: `CONTINUE_DATA_COLLECTION`" in report
    assert "| FOOD | 0 | 0 |" in report
    assert "| Precision | N/A |" in report
    assert "| Unsupported summary rate | N/A |" in report
    assert "Trend scores are internal relative scores, not probabilities." in report


def test_weekly_report_aggregates_daily_facts_and_cannot_be_ready_before_14_days() -> None:
    week = aggregate_week(
        [
            daily_fixture(date(2026, 9, 20), reviewed=1),
            daily_fixture(date(2026, 9, 21), reviewed=1, complete_day=False),
        ],
        week_number=1,
    )
    report = render_weekly_markdown(week)

    assert week.supply.raw_candidates == 20
    assert week.coverage[Category.SPORTS].valid_cards == 2
    assert week.cost.human_minutes == 6
    assert week.decision == "CONTINUE_DATA_COLLECTION"
    assert "Period: `2026-09-20` through `2026-09-21`" in report
    assert "Complete days: 1" in report


def test_report_write_atomically_replaces_target(tmp_path) -> None:
    target = tmp_path / "2026-09-20.md"
    target.write_text("old", encoding="utf-8")

    write_report_atomic(target, "new\n")

    assert target.read_text(encoding="utf-8") == "new\n"
    assert list(tmp_path.iterdir()) == [target]
