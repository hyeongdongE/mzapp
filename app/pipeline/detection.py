from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import ResolutionStatus, Source, TrendLifecycle
from app.models.tables import (
    CandidateObservation,
    EntityCandidate,
    SourceObservation,
    TrendCandidate,
    TrendEntity,
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
    Source.GEEKNEWS: CURRENT_WINDOW,
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
    current_windows: int
    current_span_hours: float
    first_seen_at: datetime | None
    missing_inputs: tuple[str, ...]


class FeatureExtractor:
    def extract(
        self,
        points: list[SignalPoint],
        as_of: datetime,
    ) -> ExtractedFeatures:
        eligible_raw = [
            point
            for point in points
            if _as_utc(point.source_timestamp) <= as_of and _as_utc(point.observed_at) <= as_of
        ]
        eligible = _deduplicate_occurrences(eligible_raw)
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
        current_timestamps = sorted(_as_utc(point.source_timestamp) for point in current)
        current_span_hours = 0.0
        if len(current_timestamps) >= 2:
            current_span_hours = (
                current_timestamps[-1] - current_timestamps[0]
            ).total_seconds() / 3600
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
        for window_name, window_points in (("current", current), ("previous", previous)):
            for point in window_points:
                missing = _missing_metric_name(point)
                if missing is not None:
                    missing_inputs.add(f"{missing}.{window_name}")
        seen_at = (
            min(_as_utc(point.source_timestamp) for point in eligible)
            if eligible
            else None
        )
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
            current_windows=window_count,
            current_span_hours=round(current_span_hours, 6),
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
        entity = self._session.get(TrendEntity, entity_id)
        if entity is None or entity.resolution_status is not ResolutionStatus.RESOLVED:
            return None
        return self._snapshot(
            entity_id,
            as_of,
            pipeline_run_id=pipeline_run_id,
            candidate_ids=None,
            minimum_timestamp=None,
            persist=True,
        )

    def replay_snapshot(
        self,
        entity_id: int,
        candidate_ids: tuple[int, ...],
        as_of: datetime,
        *,
        from_: datetime,
        pipeline_run_id: int,
        persist: bool,
        points: list[SignalPoint] | None = None,
        history_pipeline_run_id: int | None = None,
    ) -> TrendSnapshot | None:
        if (
            as_of.tzinfo is None
            or as_of.utcoffset() is None
            or as_of.utcoffset().total_seconds() != 0
        ):
            raise ValueError("as_of must be aware UTC")
        if not candidate_ids or self._session.get(TrendEntity, entity_id) is None:
            return None
        return self._snapshot(
            entity_id,
            as_of,
            pipeline_run_id=pipeline_run_id,
            candidate_ids=candidate_ids,
            minimum_timestamp=from_,
            persist=persist,
            points_override=points,
            history_pipeline_run_id=history_pipeline_run_id,
        )

    def _snapshot(
        self,
        entity_id: int,
        as_of: datetime,
        *,
        pipeline_run_id: int,
        candidate_ids: tuple[int, ...] | None,
        minimum_timestamp: datetime | None,
        persist: bool,
        points_override: list[SignalPoint] | None = None,
        history_pipeline_run_id: int | None = None,
    ) -> TrendSnapshot | None:
        if persist:
            existing = self._session.scalar(
                select(TrendSnapshot).where(
                    TrendSnapshot.entity_id == entity_id,
                    TrendSnapshot.as_of == as_of,
                    TrendSnapshot.score_version == self._score_version,
                )
            )
            if existing is not None:
                return existing
        points = points_override
        if points is None:
            points = self._points(
                entity_id,
                as_of,
                candidate_ids=candidate_ids,
                minimum_timestamp=minimum_timestamp,
            )
        features = FeatureExtractor().extract(points, as_of)
        score = ExplainableScorer().score(
            features.signal, missing_inputs=features.missing_inputs
        )
        previous_statement = (
            select(TrendSnapshot)
            .where(
                TrendSnapshot.entity_id == entity_id,
                TrendSnapshot.as_of < as_of,
                TrendSnapshot.score_version == self._score_version,
            )
            .order_by(TrendSnapshot.as_of.desc())
        )
        recent_statement = (
            select(TrendSnapshot)
                .where(
                    TrendSnapshot.entity_id == entity_id,
                    TrendSnapshot.as_of < as_of,
                    TrendSnapshot.as_of >= as_of - CURRENT_WINDOW,
                    TrendSnapshot.score_version == self._score_version,
                )
                .order_by(TrendSnapshot.as_of)
        )
        if history_pipeline_run_id is not None:
            previous_statement = previous_statement.where(
                TrendSnapshot.pipeline_run_id == history_pipeline_run_id
            )
            recent_statement = recent_statement.where(
                TrendSnapshot.pipeline_run_id == history_pipeline_run_id
            )
        previous = self._session.scalar(previous_statement)
        recent_snapshots = list(self._session.scalars(recent_statement))
        high_windows, high_duration = _high_score_state(
            recent_snapshots, as_of, score.total
        )
        if features.current_observations == 0 and (
            previous is None
            or previous.lifecycle not in {TrendLifecycle.RISING, TrendLifecycle.HOT}
        ):
            return None
        lifecycle = None
        lifecycle_first_seen = features.first_seen_at
        if lifecycle_first_seen is None and previous is not None:
            lifecycle_first_seen = _as_utc(previous.as_of)
        if lifecycle_first_seen is not None:
            lifecycle = LifecycleDetector().detect(
                LifecycleContext(
                    first_seen_at=lifecycle_first_seen,
                    current_strength=features.current_strength,
                    previous_strength=features.previous_strength,
                    current_observations=features.current_windows,
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
        if not persist:
            return snapshot
        try:
            with self._session.begin_nested():
                self._session.add(snapshot)
                self._session.flush()
            return snapshot
        except IntegrityError:
            existing = self._session.scalar(
                select(TrendSnapshot).where(
                    TrendSnapshot.entity_id == entity_id,
                    TrendSnapshot.as_of == as_of,
                    TrendSnapshot.score_version == self._score_version,
                )
            )
            if existing is None:
                raise
            return existing

    def _points(
        self,
        entity_id: int,
        as_of: datetime,
        *,
        candidate_ids: tuple[int, ...] | None = None,
        minimum_timestamp: datetime | None = None,
    ) -> list[SignalPoint]:
        statement = (
            select(SourceObservation, TrendCandidate.id, TrendCandidate.normalized_text)
            .join(
                CandidateObservation,
                CandidateObservation.observation_id == SourceObservation.id,
            )
            .join(TrendCandidate, TrendCandidate.id == CandidateObservation.candidate_id)
            .where(
                SourceObservation.source_timestamp <= as_of,
                SourceObservation.observed_at <= as_of,
                SourceObservation.source_timestamp >= as_of - BASELINE_LOOKBACK,
            )
            .order_by(SourceObservation.source_timestamp, SourceObservation.id)
        )
        if candidate_ids is None:
            statement = statement.join(
                EntityCandidate, EntityCandidate.candidate_id == TrendCandidate.id
            ).where(EntityCandidate.entity_id == entity_id)
        else:
            statement = statement.where(TrendCandidate.id.in_(candidate_ids))
        if minimum_timestamp is not None:
            statement = statement.where(
                SourceObservation.source_timestamp >= minimum_timestamp,
                SourceObservation.observed_at >= minimum_timestamp,
            )
        rows = self._session.execute(statement)
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
        source_item_key=observation.source_item_id,
    )


def _strength(point: SignalPoint) -> float:
    if point.metric is not None and point.metric >= 0:
        cap = SOURCE_CAPS.get(point.source, 1_000_000)
        return _clamp(math.log1p(point.metric) / math.log1p(cap))
    if point.rank is not None and point.rank > 0:
        return _clamp(1 - (point.rank - 1) / 1000)
    return 0.0


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _window_for(source: Source) -> timedelta:
    return SOURCE_WINDOWS.get(source, CURRENT_WINDOW)


def _missing_metric_name(point: SignalPoint) -> str | None:
    if point.source is Source.GOOGLE_TRENDS and point.metric is None:
        return "google.approx_traffic_lower_bound"
    if point.source is Source.WIKIMEDIA and point.metric is None and point.rank is None:
        return "wikimedia.views_ceil_or_rank"
    return None


def _deduplicate_occurrences(points: list[SignalPoint]) -> list[SignalPoint]:
    deduplicated: list[SignalPoint] = []
    seen: set[tuple[Source, str]] = set()
    for point in points:
        if point.source_item_key is None:
            deduplicated.append(point)
            continue
        key = (point.source, point.source_item_key)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(point)
    return deduplicated


def _high_score_state(
    snapshots: list[TrendSnapshot], as_of: datetime, current_score: float
) -> tuple[int, float]:
    if current_score < 70:
        return 0, 0.0
    high_tail: list[datetime] = [as_of]
    later = as_of
    for snapshot in reversed(snapshots):
        snapshot_time = _as_utc(snapshot.as_of)
        if snapshot.total_score < 70:
            break
        if later - snapshot_time > timedelta(hours=6, minutes=5):
            break
        high_tail.append(snapshot_time)
        later = snapshot_time
    distinct_windows = {
        int((as_of - timestamp).total_seconds() // (6 * 3600))
        for timestamp in high_tail
    }
    duration_hours = (as_of - min(high_tail)).total_seconds() / 3600
    return len(distinct_windows), round(duration_hours, 6)


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
            "current_windows": features.current_windows,
            "current_span_hours": features.current_span_hours,
            "baseline_presence_ratio": features.baseline.presence_ratio,
            "baseline_structural_noise": features.baseline.structural_noise,
            "baseline_median_rank": features.baseline.median_rank,
            "baseline_median_metric": features.baseline.median_metric,
        },
    }
