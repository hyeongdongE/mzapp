from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.models.enums import Category


@dataclass(frozen=True)
class CardFact:
    category: Category
    valid: bool


@dataclass(frozen=True)
class CostFact:
    cost_type: str
    amount: Decimal
    human_minutes: int = 0
    hourly_rate: Decimal = Decimal("0")


@dataclass(frozen=True)
class FreshnessFact:
    detection_delay: timedelta | None
    approval_delay: timedelta | None


@dataclass(frozen=True)
class SupplyMetrics:
    raw_candidates: int
    unique_candidates: int
    trend_entities: int
    approved_cards: int


@dataclass(frozen=True)
class CategoryCoverage:
    candidates: int
    valid_cards: int


@dataclass(frozen=True)
class QualityMetrics:
    reviewed: int
    valid_trends: int
    duplicates: int
    noise_items: int
    news_only_items: int
    classification_errors: int
    merge_errors: int
    precision: Decimal | None
    duplicate_rate: Decimal | None
    noise_rate: Decimal | None
    news_only_rate: Decimal | None
    classification_error_rate: Decimal | None
    merge_error_rate: Decimal | None
    checked_claims: int
    blocked_claims: int
    unsupported_summary_rate: Decimal | None


@dataclass(frozen=True)
class CrossSourceMetrics:
    eligible_entities: int
    confirmed_entities: int
    rate: Decimal | None


@dataclass(frozen=True)
class FreshnessMetrics:
    detection_samples: int
    detection_p50_minutes: Decimal | None
    detection_p95_minutes: Decimal | None
    approval_samples: int
    approval_p50_minutes: Decimal | None
    approval_p95_minutes: Decimal | None
    detection_minutes: tuple[Decimal, ...]
    approval_minutes: tuple[Decimal, ...]


@dataclass(frozen=True)
class CostMetrics:
    total_cost: Decimal
    human_minutes: int
    cost_per_approved_card: Decimal | None
    by_type: dict[str, Decimal]


@dataclass(frozen=True)
class DailyEvaluation:
    day: date
    complete_day: bool
    supply: SupplyMetrics
    coverage: dict[Category, CategoryCoverage]
    quality: QualityMetrics
    cross_source: CrossSourceMetrics
    freshness: FreshnessMetrics
    cost: CostMetrics
    top_noise_sources: tuple[tuple[str, int], ...]
    versions: dict[str, tuple[str, ...]]
    decision: str
    missing_denominators: tuple[str, ...]


@dataclass(frozen=True)
class WeeklyEvaluation:
    week_number: int
    start_date: date
    end_date: date
    complete_days: int
    supply: SupplyMetrics
    coverage: dict[Category, CategoryCoverage]
    quality: QualityMetrics
    cross_source: CrossSourceMetrics
    freshness: FreshnessMetrics
    cost: CostMetrics
    top_noise_sources: tuple[tuple[str, int], ...]
    versions: dict[str, tuple[str, ...]]
    decision: str
    missing_denominators: tuple[str, ...]
