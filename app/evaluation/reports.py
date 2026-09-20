from __future__ import annotations

import os
import tempfile
from collections import Counter
from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from app.evaluation.metrics import cost, coverage, cross_source, freshness, quality
from app.evaluation.models import (
    CardFact,
    CostFact,
    CostMetrics,
    DailyEvaluation,
    FreshnessFact,
    SupplyMetrics,
    WeeklyEvaluation,
)
from app.models.enums import Category, HumanEvaluationLabel, Source


def _format_rate(value: Decimal | None) -> str:
    return "N/A" if value is None else f"{value * 100:.2f}%"


def _format_decimal(value: Decimal | None, places: int = 2) -> str:
    return "N/A" if value is None else f"{value:.{places}f}"


def _quality_rows(result: DailyEvaluation | WeeklyEvaluation) -> list[tuple[str, str]]:
    quality_metrics = result.quality
    return [
        ("Reviewed decisions", str(quality_metrics.reviewed)),
        ("Precision", _format_rate(quality_metrics.precision)),
        ("Duplicate rate", _format_rate(quality_metrics.duplicate_rate)),
        ("Noise rate", _format_rate(quality_metrics.noise_rate)),
        ("News-only rate", _format_rate(quality_metrics.news_only_rate)),
        (
            "Classification error rate",
            _format_rate(quality_metrics.classification_error_rate),
        ),
        ("Merge error rate", _format_rate(quality_metrics.merge_error_rate)),
        (
            "Unsupported summary rate",
            _format_rate(quality_metrics.unsupported_summary_rate),
        ),
    ]


def _render_body(result: DailyEvaluation | WeeklyEvaluation) -> list[str]:
    lines = [
        f"Decision: `{result.decision}`",
        "",
        "> Trend scores are internal relative scores, not probabilities.",
        "",
        "## Supply",
        "",
        "| Metric | Count |",
        "|---|---:|",
        f"| Raw candidates | {result.supply.raw_candidates} |",
        f"| Unique candidates | {result.supply.unique_candidates} |",
        f"| Trend entities | {result.supply.trend_entities} |",
        f"| Approved cards | {result.supply.approved_cards} |",
        "",
        "## Category coverage",
        "",
        "| Category | Candidates | Valid cards |",
        "|---|---:|---:|",
    ]
    for category in Category:
        category_metrics = result.coverage[category]
        lines.append(
            f"| {category.value} | {category_metrics.candidates} | "
            f"{category_metrics.valid_cards} |"
        )
    lines.extend(["", "## Quality", "", "| Metric | Value |", "|---|---:|"])
    lines.extend(f"| {name} | {value} |" for name, value in _quality_rows(result))
    lines.extend(
        [
            "",
            "## Cross-source confirmation",
            "",
            f"Eligible entities: {result.cross_source.eligible_entities}",
            f"Confirmed entities: {result.cross_source.confirmed_entities}",
            f"Rate: {_format_rate(result.cross_source.rate)}",
            "",
            "## Freshness",
            "",
            "| Metric | Samples | P50 minutes | P95 minutes |",
            "|---|---:|---:|---:|",
            "| Detection | "
            f"{result.freshness.detection_samples} | "
            f"{_format_decimal(result.freshness.detection_p50_minutes)} | "
            f"{_format_decimal(result.freshness.detection_p95_minutes)} |",
            "| Approval | "
            f"{result.freshness.approval_samples} | "
            f"{_format_decimal(result.freshness.approval_p50_minutes)} | "
            f"{_format_decimal(result.freshness.approval_p95_minutes)} |",
            "",
            "## Cost",
            "",
            f"Total cost: {result.cost.total_cost:.6f} USD",
            f"Human review minutes: {result.cost.human_minutes}",
            "Cost per approved card: "
            + (
                "N/A"
                if result.cost.cost_per_approved_card is None
                else f"{result.cost.cost_per_approved_card:.6f} USD"
            ),
            "",
            "| Cost type | Amount (USD) |",
            "|---|---:|",
        ]
    )
    if result.cost.by_type:
        lines.extend(
            f"| {cost_type} | {amount:.6f} |"
            for cost_type, amount in sorted(result.cost.by_type.items())
        )
    else:
        lines.append("| None | 0.000000 |")
    lines.extend(["", "## Top noise sources", ""])
    if result.top_noise_sources:
        lines.extend(f"- {label}: {count}" for label, count in result.top_noise_sources)
    else:
        lines.append("- N/A")
    lines.extend(["", "## Versions", ""])
    for name, values in sorted(result.versions.items()):
        lines.append(f"- {name}: {', '.join(values) if values else 'N/A'}")
    lines.extend(["", "## Missing denominators", ""])
    if result.missing_denominators:
        lines.extend(f"- {item}" for item in result.missing_denominators)
    else:
        lines.append("- None")
    return lines


def render_daily_markdown(result: DailyEvaluation) -> str:
    lines = [
        f"# Trend Radar Daily Evaluation — {result.day.isoformat()}",
        "",
        f"Period: `{result.day.isoformat()}` (UTC)",
        f"Official collection complete: {'Yes' if result.complete_day else 'No'}",
        "",
        *_render_body(result),
    ]
    return "\n".join(lines).rstrip() + "\n"


def render_weekly_markdown(result: WeeklyEvaluation) -> str:
    lines = [
        f"# Trend Radar Weekly Evaluation — Week {result.week_number:02d}",
        "",
        f"Period: `{result.start_date.isoformat()}` through `{result.end_date.isoformat()}` (UTC)",
        f"Complete days: {result.complete_days}",
        "",
        *_render_body(result),
    ]
    return "\n".join(lines).rstrip() + "\n"


def write_report_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        temporary_path.replace(path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def aggregate_week(
    days: Sequence[DailyEvaluation], *, week_number: int
) -> WeeklyEvaluation:
    if not days:
        raise ValueError("weekly evaluation requires at least one daily evaluation")
    ordered = sorted(days, key=lambda item: item.day)
    if len({item.day for item in ordered}) != len(ordered):
        raise ValueError("weekly evaluation cannot contain duplicate days")

    supply = SupplyMetrics(
        raw_candidates=sum(item.supply.raw_candidates for item in ordered),
        unique_candidates=sum(item.supply.unique_candidates for item in ordered),
        trend_entities=sum(item.supply.trend_entities for item in ordered),
        approved_cards=sum(item.supply.approved_cards for item in ordered),
    )
    cards: list[CardFact] = []
    for item in ordered:
        for category, category_metrics in item.coverage.items():
            cards.extend(
                CardFact(category, valid=index < category_metrics.valid_cards)
                for index in range(category_metrics.candidates)
            )

    labels: list[HumanEvaluationLabel] = []
    for item in ordered:
        metric = item.quality
        labels.extend([HumanEvaluationLabel.VALID_TREND] * metric.valid_trends)
        labels.extend([HumanEvaluationLabel.DUPLICATE] * metric.duplicates)
        labels.extend([HumanEvaluationLabel.NEWS_ONLY] * metric.news_only_items)
        labels.extend([HumanEvaluationLabel.WRONG_CATEGORY] * metric.classification_errors)
        labels.extend([HumanEvaluationLabel.BAD_ENTITY_MERGE] * metric.merge_errors)
        other_noise = metric.noise_items - metric.news_only_items
        labels.extend([HumanEvaluationLabel.NOT_USEFUL] * other_noise)
        accounted = (
            metric.valid_trends
            + metric.duplicates
            + metric.noise_items
            + metric.classification_errors
            + metric.merge_errors
        )
        labels.extend([HumanEvaluationLabel.INSUFFICIENT_EVIDENCE] * (metric.reviewed - accounted))
    quality_metrics = quality(
        labels,
        checked_claims=sum(item.quality.checked_claims for item in ordered),
        blocked_claims=sum(item.quality.blocked_claims for item in ordered),
    )

    source_sets = [
        frozenset({Source.GOOGLE_TRENDS, Source.WIKIMEDIA})
        for _ in range(sum(item.cross_source.confirmed_entities for item in ordered))
    ]
    source_sets.extend(
        frozenset({Source.GOOGLE_TRENDS})
        for _ in range(
            sum(item.cross_source.eligible_entities for item in ordered)
            - len(source_sets)
        )
    )
    freshness_facts = [
        FreshnessFact(timedelta(minutes=float(minutes)), None)
        for item in ordered
        for minutes in item.freshness.detection_minutes
    ]
    approval_minutes = [
        minutes for item in ordered for minutes in item.freshness.approval_minutes
    ]
    freshness_facts.extend(
        FreshnessFact(None, timedelta(minutes=float(minutes)))
        for minutes in approval_minutes
    )
    freshness_metrics = freshness(freshness_facts)

    calculated_cost = cost(
        [
            CostFact(cost_type, amount)
            for item in ordered
            for cost_type, amount in item.cost.by_type.items()
        ],
        approved=supply.approved_cards,
    )
    cost_metrics = CostMetrics(
        total_cost=calculated_cost.total_cost,
        human_minutes=sum(item.cost.human_minutes for item in ordered),
        cost_per_approved_card=calculated_cost.cost_per_approved_card,
        by_type=calculated_cost.by_type,
    )
    noise_counts: Counter[str] = Counter()
    versions: dict[str, set[str]] = {}
    for item in ordered:
        noise_counts.update(dict(item.top_noise_sources))
        for name, values in item.versions.items():
            versions.setdefault(name, set()).update(values)
    missing = tuple(sorted({value for item in ordered for value in item.missing_denominators}))
    return WeeklyEvaluation(
        week_number=week_number,
        start_date=ordered[0].day,
        end_date=ordered[-1].day,
        complete_days=sum(item.complete_day for item in ordered),
        supply=supply,
        coverage=coverage(cards),
        quality=quality_metrics,
        cross_source=cross_source(source_sets),
        freshness=freshness_metrics,
        cost=cost_metrics,
        top_noise_sources=tuple(sorted(noise_counts.items(), key=lambda item: (-item[1], item[0]))),
        versions={name: tuple(sorted(values)) for name, values in sorted(versions.items())},
        decision="CONTINUE_DATA_COLLECTION",
        missing_denominators=missing,
    )
