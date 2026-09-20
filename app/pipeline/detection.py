from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import Source
from app.models.tables import (
    CandidateObservation,
    EntityCandidate,
    SourceObservation,
    TrendCandidate,
    TrendSnapshot,
)
from app.pipeline.baseline import (
    BaselineAnalyzer,
    BaselineStats,
    SignalPoint,
    is_structural_name,
)
from app.pipeline.entity import validate_live_cutoff
from app.pipeline.lifecycle import LifecycleContext, LifecycleDetector
from app.pipeline.scoring import ExplainableScorer, ScoreBreakdown, TrendSignal

CURRENT_WINDOW = timedelta(hours=24)
SOURCE_WINDOWS = {
    Source.GOOGLE_TRENDS: CURRENT_WINDOW,
    Source.WIKIMEDIA: timedelta(hours=72),
}
BASELINE_LOOKBACK = timedelta(days=32)
SOURCE_CAPS = {
    Source.GOOGLE_TRENDS: 1_000_000,
    Source.WIKIMEDIA: 10_000_000,
}


@dataclass(frozen=True)
class ExtractedFeatures:
    signal: TrendSignal
    baseline: BaselineStats
    current_strength: float
    previous_strength: float
    current_observations: int
    first_seen_at: datetime | None
    missing_inputs: tuple[str, ...]


class FeatureExtractor:
    def extract(
        self,
        points: list[SignalPoint],
        as_of: datetime,
        *,
        first_seen_at: datetime | None = None,
    ) -> ExtractedFeatures:
        eligible = [
            point
            for point in points
            if _as_utc(point.source_timestamp) <= as_of and _as_utc(point.observed_at) <= as_of
        ]
        current = [
            point
            for point in eligible
            if as_of - _window_for(point.source) < _as_utc(point.source_timestamp) <= as_of
        ]
        previous = [
            point
            for point in eligible
            if as_of - 2 * _window_for(point.source)
            < _as_utc(point.source_timestamp)
            <= as_of - _window_for(point.source)
        ]
        baseline_points = [
            point
            for point in eligible
            if as_of - _window_for(point.source) - timedelta(days=28)
            <= _as_utc(point.source_timestamp)
            <= as_of - _window_for(point.source)
        ]
        baseline = BaselineAnalyzer().summarize(baseline_points)
        current_strength = round(sum(_strength(point) for point in current), 6)
        previous_strength = round(sum(_strength(point) for point in previous), 6)
        if previous_strength == 0:
            velocity = 1.0 if current_strength > 0 else 0.0
        else:
            velocity = _clamp((current_strength - previous_strength) / previous_strength)
        structural = any(is_structural_name(point.normalized_text) for point in eligible)
        baseline_penalty = 1.0 if structural else baseline.penalty
        novelty = 0.0 if structural else _clamp(1 - baseline.presence_ratio)
        window_count = len(
            {
                int(_as_utc(point.source_timestamp).timestamp() // (6 * 3600))
                for point in current
            }
        )
        persistence = _clamp(window_count / 4)
        current_sources = {point.source for point in current}
        cross_source = 1.0 if len(current_sources) >= 2 else 0.0
        current_names = {point.normalized_text for point in current}
        repetition = (
            (len(current_names) - 1) / len(current_names)
            if len(current_names) > 1
            else 0.0
        )
        news_only = current_sources == {Source.GOOGLE_TRENDS} and any(
            point.news_count > 0 for point in current
        )
        missing_inputs: set[str] = set()
        for point in current:
            if point.source is Source.GOOGLE_TRENDS and point.metric is None:
                missing_inputs.add("google.approx_traffic_lower_bound")
            if point.source is Source.WIKIMEDIA and point.metric is None:
                missing_inputs.add("wikimedia.views_ceil")
        seen_at = first_seen_at
        if seen_at is None and eligible:
            seen_at = min(_as_utc(point.source_timestamp) for point in eligible)
        if seen_at is not None:
            seen_at = _as_utc(seen_at)
        return ExtractedFeatures(
            signal=TrendSignal(
                velocity=velocity,
                novelty=novelty,
                persistence=persistence,
                cross_source=cross_source,
                baseline_penalty=baseline_penalty,
                repetition_penalty=repetition,
                news_only_penalty=1.0 if news_only else 0.0,
            ),
            baseline=baseline,
            current_strength=current_strength,
            previous_strength=previous_strength,
            current_observations=len(current),
            first_seen_at=seen_at,
            missing_inputs=tuple(sorted(missing_inputs)),
        )


class TrendDetector:
    def __init__(
        self,
        session: Session,
        *,
        now: Callable[[], datetime] | None = None,
        score_version: str = "score-v1",
    ) -> None:
        self._session = session
        self._now = now or (lambda: datetime.now(UTC))
        self._score_version = score_version

    def snapshot(
        self, entity_id: int, as_of: datetime, *, pipeline_run_id: int
    ) -> TrendSnapshot | None:
        validate_live_cutoff(as_of, self._now().astimezone(UTC))
        existing = self._session.scalar(
            select(TrendSnapshot).where(
                TrendSnapshot.entity_id == entity_id,
                TrendSnapshot.as_of == as_of,
                TrendSnapshot.score_version == self._score_version,
            )
        )
        if existing is not None:
            return existing
        points = self._points(entity_id, as_of)
        first_seen = self._session.scalar(
            select(func.min(TrendCandidate.first_seen_at))
            .join(EntityCandidate, EntityCandidate.candidate_id == TrendCandidate.id)
            .where(EntityCandidate.entity_id == entity_id)
        )
        features = FeatureExtractor().extract(
            points, as_of, first_seen_at=first_seen
        )
        score = ExplainableScorer().score(
            features.signal, missing_inputs=features.missing_inputs
        )
        previous = self._session.scalar(
            select(TrendSnapshot)
            .where(
                TrendSnapshot.entity_id == entity_id,
                TrendSnapshot.as_of < as_of,
                TrendSnapshot.score_version == self._score_version,
            )
            .order_by(TrendSnapshot.as_of.desc())
        )
        high_snapshots = list(
            self._session.scalars(
                select(TrendSnapshot)
                .where(
                    TrendSnapshot.entity_id == entity_id,
                    TrendSnapshot.as_of < as_of,
                    TrendSnapshot.as_of >= as_of - CURRENT_WINDOW,
                    TrendSnapshot.score_version == self._score_version,
                    TrendSnapshot.total_score >= 70,
                )
                .order_by(TrendSnapshot.as_of)
            )
        )
        high_windows = len(high_snapshots) + (1 if score.total >= 70 else 0)
        high_duration = 0.0
        if high_snapshots and score.total >= 70:
            high_duration = (as_of - _as_utc(high_snapshots[0].as_of)).total_seconds() / 3600
        lifecycle = None
        if features.first_seen_at is not None:
            lifecycle = LifecycleDetector().detect(
                LifecycleContext(
                    first_seen_at=features.first_seen_at,
                    current_strength=features.current_strength,
                    previous_strength=features.previous_strength,
                    current_observations=features.current_observations,
                    score=score.total,
                    baseline_presence=features.baseline.presence_ratio,
                    previous_lifecycle=previous.lifecycle if previous else None,
                    high_score_windows=high_windows,
                    high_score_duration_hours=high_duration,
                ),
                as_of,
            )
        if lifecycle is None:
            return None
        snapshot = TrendSnapshot(
            entity_id=entity_id,
            pipeline_run_id=pipeline_run_id,
            as_of=as_of,
            lifecycle=lifecycle,
            total_score=score.total,
            breakdown=_breakdown(score, features),
            missing_inputs=list(score.missing_inputs),
            score_version=self._score_version,
            system_detected_at=self._now().astimezone(UTC),
        )
        self._session.add(snapshot)
        self._session.flush()
        return snapshot

    def _points(self, entity_id: int, as_of: datetime) -> list[SignalPoint]:
        rows = self._session.execute(
            select(SourceObservation, TrendCandidate.id, TrendCandidate.normalized_text)
            .join(
                CandidateObservation,
                CandidateObservation.observation_id == SourceObservation.id,
            )
            .join(TrendCandidate, TrendCandidate.id == CandidateObservation.candidate_id)
            .join(EntityCandidate, EntityCandidate.candidate_id == TrendCandidate.id)
            .where(
                EntityCandidate.entity_id == entity_id,
                SourceObservation.source_timestamp <= as_of,
                SourceObservation.observed_at <= as_of,
                SourceObservation.source_timestamp >= as_of - BASELINE_LOOKBACK,
            )
            .order_by(SourceObservation.source_timestamp, SourceObservation.id)
        )
        return [
            _to_point(observation, candidate_id, normalized_text)
            for observation, candidate_id, normalized_text in rows
        ]


def _to_point(
    observation: SourceObservation, candidate_id: int, normalized_text: str
) -> SignalPoint:
    metrics: dict[str, Any] = observation.metrics or {}
    metric = None
    rank = None
    news_count = 0
    if observation.source is Source.GOOGLE_TRENDS:
        raw_metric = metrics.get("approx_traffic_lower_bound")
        if isinstance(raw_metric, (int, float)) and not isinstance(raw_metric, bool):
            metric = float(raw_metric)
        news_items = metrics.get("news_items")
        news_count = len(news_items) if isinstance(news_items, list) else 0
    elif observation.source is Source.WIKIMEDIA:
        raw_metric = metrics.get("views_ceil")
        if isinstance(raw_metric, (int, float)) and not isinstance(raw_metric, bool):
            metric = float(raw_metric)
        raw_rank = metrics.get("rank")
        if isinstance(raw_rank, int) and not isinstance(raw_rank, bool):
            rank = raw_rank
    return SignalPoint(
        source=observation.source,
        source_timestamp=_as_utc(observation.source_timestamp),
        observed_at=_as_utc(observation.observed_at),
        normalized_text=normalized_text,
        metric=metric,
        rank=rank,
        news_count=news_count,
        candidate_id=candidate_id,
    )


def _strength(point: SignalPoint) -> float:
    if point.metric is not None and point.metric >= 0:
        cap = SOURCE_CAPS.get(point.source, 1_000_000)
        return _clamp(math.log1p(point.metric) / math.log1p(cap))
    if point.rank is not None and point.rank > 0:
        return _clamp(1 - (point.rank - 1) / 1000)
    return 0.1


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _window_for(source: Source) -> timedelta:
    return SOURCE_WINDOWS.get(source, CURRENT_WINDOW)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _breakdown(score: ScoreBreakdown, features: ExtractedFeatures) -> dict[str, Any]:
    return {
        "components": score.components,
        "weights": score.weights,
        "contributions": score.contributions,
        "interpretation": score.interpretation,
        "inputs": {
            "current_strength": features.current_strength,
            "previous_strength": features.previous_strength,
            "current_observations": features.current_observations,
            "baseline_presence_ratio": features.baseline.presence_ratio,
            "baseline_structural_noise": features.baseline.structural_noise,
            "baseline_median_rank": features.baseline.median_rank,
            "baseline_median_metric": features.baseline.median_metric,
        },
    }
