from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class OperationalDateFact:
    brief_id: int
    brief_date: date
    brief_version: int
    status: str


@dataclass(frozen=True)
class ExcludedDateFact:
    brief_id: int
    brief_date: date
    brief_version: int
    status: str
    reason: str


@dataclass(frozen=True)
class MissingEventFact:
    canonical_title: str
    canonical_url: str
    discovered_from: str
    reason: str


@dataclass(frozen=True)
class ItemReviewFact:
    brief_item_review_id: int
    brief_item_id: int
    event_cluster_id: int
    usefulness: str
    event_selection: str
    fact_correctness: str
    interpretation_quality: str
    watch_usefulness: str
    verbosity: str
    evidence_set_usefulness: str
    incorrect_merge_verdict: str
    duplicate_escape_verdict: str
    duplicate_of_brief_item_id: int | None
    duplicate_of_event_cluster_id: int | None
    incorrect_merge_membership_ids: tuple[int, ...]


@dataclass(frozen=True)
class IncludedDateFact:
    brief_id: int
    brief_date: date
    brief_version: int
    pipeline_version: str
    generation_version: str
    clustering_versions: tuple[str, ...]
    assessment_versions: tuple[str, ...]
    active_review_seconds: int
    item_reviews: tuple[ItemReviewFact, ...]
    missing_events: tuple[MissingEventFact, ...]


@dataclass(frozen=True)
class BriefQualityFacts:
    reviewer: str
    start_date: date
    end_date: date
    operational_dates: tuple[OperationalDateFact, ...]
    included_dates: tuple[IncludedDateFact, ...]
    excluded_dates: tuple[ExcludedDateFact, ...]


@dataclass(frozen=True)
class RateMetric:
    numerator: int
    denominator: int
    rate: float | None


@dataclass(frozen=True)
class BriefQualityMetrics:
    useful_brief_rate: RateMetric
    event_selection: dict[str, int]
    fact_correctness: dict[str, int]
    interpretation_quality: dict[str, int]
    watch_usefulness: dict[str, int]
    verbosity: dict[str, int]
    evidence_set_usefulness: dict[str, int]
    incorrect_merge: RateMetric
    incorrect_merge_links: tuple[dict, ...]
    duplicate_escape: RateMetric
    duplicate_escape_links: tuple[dict, ...]
    missing_events_per_day: dict[str, int]
    missing_event_discovery_sources: dict[str, int]
    active_review_seconds_by_day: dict[str, int]
    active_review_seconds_p50: int | None
    active_review_seconds_p95: int | None
    reviewed_brief_count: int
    reviewed_date_count: int
    reviewed_item_count: int


@dataclass(frozen=True)
class BriefQualityReport:
    report_schema_version: str
    generated_at: datetime
    reviewer: str
    start_date: date
    end_date: date
    sample_status: str
    pipeline_versions: tuple[str, ...]
    generation_versions: tuple[str, ...]
    clustering_versions: tuple[str, ...]
    assessment_versions: tuple[str, ...]
    operational_dates: tuple[OperationalDateFact, ...]
    included_dates: tuple[IncludedDateFact, ...]
    excluded_dates: tuple[ExcludedDateFact, ...]
    metrics: BriefQualityMetrics
