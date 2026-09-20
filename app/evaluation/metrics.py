from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from decimal import ROUND_HALF_UP, Decimal
from math import ceil

from app.evaluation.models import (
    CardFact,
    CategoryCoverage,
    CostFact,
    CostMetrics,
    CrossSourceMetrics,
    FreshnessFact,
    FreshnessMetrics,
    QualityMetrics,
)
from app.models.enums import Category, HumanEvaluationLabel, Source

RATE_QUANTUM = Decimal("0.0001")
MONEY_QUANTUM = Decimal("0.000001")
MINUTE_QUANTUM = Decimal("0.01")


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return (Decimal(numerator) / Decimal(denominator)).quantize(
        RATE_QUANTUM, rounding=ROUND_HALF_UP
    )


def quality(
    labels: Iterable[HumanEvaluationLabel],
    *,
    checked_claims: int,
    blocked_claims: int,
) -> QualityMetrics:
    if checked_claims < 0 or blocked_claims < 0 or blocked_claims > checked_claims:
        raise ValueError("claim counts must satisfy 0 <= blocked <= checked")
    counts = Counter(labels)
    reviewed = sum(counts.values())
    valid = counts[HumanEvaluationLabel.VALID_TREND]
    duplicates = counts[HumanEvaluationLabel.DUPLICATE]
    news_only = counts[HumanEvaluationLabel.NEWS_ONLY]
    noise = (
        counts[HumanEvaluationLabel.TOO_OBVIOUS]
        + news_only
        + counts[HumanEvaluationLabel.NOT_USEFUL]
    )
    classification_errors = counts[HumanEvaluationLabel.WRONG_CATEGORY]
    merge_errors = counts[HumanEvaluationLabel.BAD_ENTITY_MERGE]
    return QualityMetrics(
        reviewed=reviewed,
        valid_trends=valid,
        duplicates=duplicates,
        noise_items=noise,
        news_only_items=news_only,
        classification_errors=classification_errors,
        merge_errors=merge_errors,
        precision=_rate(valid, reviewed),
        duplicate_rate=_rate(duplicates, reviewed),
        noise_rate=_rate(noise, reviewed),
        news_only_rate=_rate(news_only, reviewed),
        classification_error_rate=_rate(classification_errors, reviewed),
        merge_error_rate=_rate(merge_errors, reviewed),
        checked_claims=checked_claims,
        blocked_claims=blocked_claims,
        unsupported_summary_rate=_rate(blocked_claims, checked_claims),
    )


def coverage(cards: Iterable[CardFact]) -> dict[Category, CategoryCoverage]:
    candidates: Counter[Category] = Counter()
    valid: Counter[Category] = Counter()
    for card in cards:
        candidates[card.category] += 1
        if card.valid:
            valid[card.category] += 1
    return {
        category: CategoryCoverage(candidates[category], valid[category])
        for category in Category
    }


def cost(records: Iterable[CostFact], *, approved: int) -> CostMetrics:
    if approved < 0:
        raise ValueError("approved must be non-negative")
    totals: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    human_minutes = 0
    for record in records:
        if record.amount < 0 or record.human_minutes < 0 or record.hourly_rate < 0:
            raise ValueError("cost inputs must be non-negative")
        labor = Decimal(record.human_minutes) * record.hourly_rate / Decimal(60)
        totals[record.cost_type] += record.amount + labor
        human_minutes += record.human_minutes
    by_type = {
        cost_type: amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        for cost_type, amount in sorted(totals.items())
    }
    total = sum(by_type.values(), Decimal("0")).quantize(MONEY_QUANTUM)
    per_card = None
    if approved:
        per_card = (total / Decimal(approved)).quantize(
            MONEY_QUANTUM, rounding=ROUND_HALF_UP
        )
    return CostMetrics(total, human_minutes, per_card, by_type)


def cross_source(source_sets: Iterable[frozenset[Source]]) -> CrossSourceMetrics:
    discovery_sources = {Source.GOOGLE_TRENDS, Source.WIKIMEDIA}
    eligible = 0
    confirmed = 0
    for sources in source_sets:
        observed = sources & discovery_sources
        if not observed:
            continue
        eligible += 1
        if len(observed) >= 2:
            confirmed += 1
    return CrossSourceMetrics(eligible, confirmed, _rate(confirmed, eligible))


def _percentile(values: Sequence[Decimal], percentile: Decimal) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, ceil(float(percentile * len(ordered))))
    return ordered[rank - 1].quantize(MINUTE_QUANTUM, rounding=ROUND_HALF_UP)


def freshness(facts: Iterable[FreshnessFact]) -> FreshnessMetrics:
    detection: list[Decimal] = []
    approval: list[Decimal] = []
    for fact in facts:
        if fact.detection_delay is not None:
            if fact.detection_delay.total_seconds() < 0:
                raise ValueError("negative detection delay")
            detection.append(
                Decimal(str(fact.detection_delay.total_seconds())) / Decimal(60)
            )
        if fact.approval_delay is not None:
            if fact.approval_delay.total_seconds() < 0:
                raise ValueError("negative approval delay")
            approval.append(Decimal(str(fact.approval_delay.total_seconds())) / Decimal(60))
    detection_tuple = tuple(value.quantize(MINUTE_QUANTUM) for value in detection)
    approval_tuple = tuple(value.quantize(MINUTE_QUANTUM) for value in approval)
    return FreshnessMetrics(
        detection_samples=len(detection_tuple),
        detection_p50_minutes=_percentile(detection_tuple, Decimal("0.50")),
        detection_p95_minutes=_percentile(detection_tuple, Decimal("0.95")),
        approval_samples=len(approval_tuple),
        approval_p50_minutes=_percentile(approval_tuple, Decimal("0.50")),
        approval_p95_minutes=_percentile(approval_tuple, Decimal("0.95")),
        detection_minutes=detection_tuple,
        approval_minutes=approval_tuple,
    )
