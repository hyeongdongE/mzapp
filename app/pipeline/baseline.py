from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median

from app.models.enums import Source

BASELINE_DAYS = 28
STRUCTURAL_NAMES = {
    "main page",
    "mainpage",
    "대문",
    "위키백과 대문",
    "위키피디아 대문",
}
STRUCTURAL_PREFIXES = ("special ", "특수 ")


def is_structural_name(name: str) -> bool:
    return name in STRUCTURAL_NAMES or name.startswith(STRUCTURAL_PREFIXES)


@dataclass(frozen=True)
class SignalPoint:
    source: Source
    source_timestamp: datetime
    observed_at: datetime
    normalized_text: str
    metric: float | None
    rank: int | None
    news_count: int
    candidate_id: int


@dataclass(frozen=True)
class BaselineStats:
    presence_ratio: float
    median_rank: float | None
    median_metric: float | None
    structural_noise: bool
    source_count: int
    alias_repetition: float
    news_only: bool
    penalty: float
    observation_count: int


class BaselineAnalyzer:
    def compute(self, points: list[SignalPoint], as_of: datetime) -> BaselineStats:
        window_start = as_of - timedelta(days=BASELINE_DAYS)
        eligible = [
            point
            for point in points
            if window_start <= point.source_timestamp < as_of
            and point.observed_at <= as_of
        ]
        return self.summarize(eligible)

    def summarize(self, eligible: list[SignalPoint]) -> BaselineStats:
        present_days = {point.source_timestamp.date() for point in eligible}
        presence_ratio = min(1.0, len(present_days) / BASELINE_DAYS)
        ranks = [point.rank for point in eligible if point.rank is not None]
        metrics = [point.metric for point in eligible if point.metric is not None]
        normalized_names = {point.normalized_text for point in eligible}
        structural = any(is_structural_name(name) for name in normalized_names)
        sources = {point.source for point in eligible}
        unique_names = {point.normalized_text for point in eligible}
        alias_repetition = 0.0
        if len(unique_names) > 1:
            alias_repetition = (len(unique_names) - 1) / len(unique_names)
        news_only = bool(eligible) and sources == {Source.GOOGLE_TRENDS} and any(
            point.news_count > 0 for point in eligible
        )
        return BaselineStats(
            presence_ratio=presence_ratio,
            median_rank=float(median(ranks)) if ranks else None,
            median_metric=float(median(metrics)) if metrics else None,
            structural_noise=structural,
            source_count=len(sources),
            alias_repetition=alias_repetition,
            news_only=news_only,
            penalty=1.0 if structural else presence_ratio,
            observation_count=len(eligible),
        )
