from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from app.evaluation.metrics import cost, coverage, cross_source, freshness, quality
from app.evaluation.models import CardFact, CostFact, FreshnessFact
from app.models.enums import Category, HumanEvaluationLabel, Source


def test_quality_rates_use_all_human_evaluations_as_denominator() -> None:
    result = quality(
        [
            HumanEvaluationLabel.DUPLICATE,
            HumanEvaluationLabel.VALID_TREND,
            HumanEvaluationLabel.NEWS_ONLY,
            HumanEvaluationLabel.WRONG_CATEGORY,
            HumanEvaluationLabel.BAD_ENTITY_MERGE,
        ],
        checked_claims=4,
        blocked_claims=1,
    )

    assert result.reviewed == 5
    assert result.precision == Decimal("0.2000")
    assert result.duplicate_rate == Decimal("0.2000")
    assert result.noise_rate == Decimal("0.2000")
    assert result.news_only_rate == Decimal("0.2000")
    assert result.classification_error_rate == Decimal("0.2000")
    assert result.merge_error_rate == Decimal("0.2000")
    assert result.unsupported_summary_rate == Decimal("0.2500")


def test_zero_denominators_remain_unknown() -> None:
    result = quality([], checked_claims=0, blocked_claims=0)

    assert result.precision is None
    assert result.duplicate_rate is None
    assert result.noise_rate is None
    assert result.unsupported_summary_rate is None


def test_category_coverage_includes_empty_categories() -> None:
    result = coverage(
        [
            CardFact(Category.SPORTS, valid=True),
            CardFact(Category.SPORTS, valid=False),
        ]
    )

    assert set(result) == set(Category)
    assert result[Category.SPORTS].candidates == 2
    assert result[Category.SPORTS].valid_cards == 1
    assert result[Category.FOOD].candidates == 0
    assert result[Category.FOOD].valid_cards == 0


def test_cost_per_approved_card_aggregates_api_llm_and_human_cost() -> None:
    result = cost(
        [
            CostFact("API", Decimal("0.10")),
            CostFact("LLM", Decimal("0.20")),
            CostFact("HUMAN", Decimal("0"), human_minutes=6, hourly_rate=Decimal("20")),
        ],
        approved=2,
    )

    assert result.total_cost == Decimal("2.300000")
    assert result.human_minutes == 6
    assert result.cost_per_approved_card == Decimal("1.150000")
    assert result.by_type == {
        "API": Decimal("0.100000"),
        "HUMAN": Decimal("2.000000"),
        "LLM": Decimal("0.200000"),
    }


def test_cross_source_and_freshness_use_explicit_denominators() -> None:
    confirmation = cross_source(
        [
            frozenset({Source.GOOGLE_TRENDS, Source.WIKIMEDIA}),
            frozenset({Source.GOOGLE_TRENDS}),
            frozenset(),
        ]
    )
    timing = freshness(
        [
            FreshnessFact(timedelta(minutes=10), timedelta(minutes=5)),
            FreshnessFact(timedelta(minutes=20), None),
            FreshnessFact(timedelta(minutes=30), timedelta(minutes=15)),
        ]
    )

    assert confirmation.eligible_entities == 2
    assert confirmation.confirmed_entities == 1
    assert confirmation.rate == Decimal("0.5000")
    assert timing.detection_samples == 3
    assert timing.detection_p50_minutes == Decimal("20.00")
    assert timing.detection_p95_minutes == Decimal("30.00")
    assert timing.approval_samples == 2
    assert timing.approval_p50_minutes == Decimal("5.00")
    assert timing.approval_p95_minutes == Decimal("15.00")


def test_geeknews_is_a_discovery_source_without_self_confirmation() -> None:
    result = cross_source(
        [
            frozenset({Source.GEEKNEWS}),
            frozenset({Source.GEEKNEWS, Source.GOOGLE_TRENDS}),
        ]
    )

    assert result.eligible_entities == 2
    assert result.confirmed_entities == 1
    assert result.rate == Decimal("0.5000")


def test_negative_freshness_delay_is_rejected() -> None:
    with pytest.raises(ValueError, match="negative"):
        freshness([FreshnessFact(timedelta(seconds=-1), None)])


def test_freshness_can_record_approval_on_a_later_day_without_new_detection() -> None:
    result = freshness([FreshnessFact(None, timedelta(minutes=45))])

    assert result.detection_samples == 0
    assert result.approval_samples == 1
    assert result.approval_p50_minutes == Decimal("45.00")
