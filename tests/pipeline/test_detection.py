from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.models.enums import (
    CandidateStatus,
    ResolutionStatus,
    ReviewStatus,
    RunKind,
    RunStatus,
    Source,
    TrendLifecycle,
)
from app.models.tables import (
    CandidateObservation,
    CollectionRun,
    PipelineRun,
    RawPayload,
    SourceObservation,
    TrendCandidate,
    TrendEntity,
    TrendSnapshot,
)
from app.pipeline.baseline import SignalPoint
from app.pipeline.detection import FeatureExtractor, TrendDetector, _high_score_state
from app.pipeline.lifecycle import LifecycleContext, LifecycleDetector
from app.pipeline.scoring import ExplainableScorer
from app.repositories.entities import EntityRepository

AS_OF = datetime(2026, 9, 21, 0, 0, tzinfo=UTC)


def point(
    hours_ago: int,
    *,
    source: Source = Source.GOOGLE_TRENDS,
    metric: float | None = 100,
    observed_at: datetime | None = None,
    candidate_id: int = 1,
    news_count: int = 0,
    source_item_key: str | None = None,
) -> SignalPoint:
    timestamp = AS_OF - timedelta(hours=hours_ago)
    return SignalPoint(
        source=source,
        source_timestamp=timestamp,
        observed_at=observed_at or timestamp,
        normalized_text="topic",
        metric=metric,
        rank=None,
        news_count=news_count,
        candidate_id=candidate_id,
        source_item_key=source_item_key,
    )


def test_feature_extractor_ignores_future_and_late_acquired_data() -> None:
    valid = point(1)
    future = point(-1, metric=1_000_000)
    learned_later = point(2, metric=1_000_000, observed_at=AS_OF + timedelta(minutes=1))

    expected = FeatureExtractor().extract([valid], AS_OF)
    actual = FeatureExtractor().extract([valid, future, learned_later], AS_OF)

    assert actual.current_observations == 1
    assert actual.current_strength == expected.current_strength
    assert actual.signal == expected.signal


def test_feature_extractor_requires_real_second_source_for_cross_source_bonus() -> None:
    one_source = FeatureExtractor().extract([point(1), point(2)], AS_OF)
    two_sources = FeatureExtractor().extract(
        [point(1), point(2, source=Source.WIKIMEDIA)], AS_OF
    )

    assert one_source.signal.cross_source == 0
    assert two_sources.signal.cross_source == 1
    assert two_sources.signal.repetition_penalty == 0


def test_wikimedia_known_lag_uses_72_hour_source_window() -> None:
    extracted = FeatureExtractor().extract(
        [point(1), point(60, source=Source.WIKIMEDIA)], AS_OF
    )

    assert extracted.current_observations == 2
    assert extracted.signal.cross_source == 1


def test_missing_metrics_create_no_strength_or_rising_state() -> None:
    extracted = FeatureExtractor().extract(
        [
            point(7, metric=None, source_item_key="missing-1"),
            point(1, metric=None, source_item_key="missing-2"),
        ],
        AS_OF,
    )
    score = ExplainableScorer().score(
        extracted.signal, missing_inputs=extracted.missing_inputs
    )
    lifecycle = LifecycleDetector().detect(
        LifecycleContext(
            first_seen_at=extracted.first_seen_at,
            current_strength=extracted.current_strength,
            previous_strength=extracted.previous_strength,
            current_observations=extracted.current_windows,
            score=score.total,
            baseline_presence=extracted.baseline.presence_ratio,
        ),
        AS_OF,
    )

    assert extracted.current_strength == 0
    assert "google.approx_traffic_lower_bound.current" in extracted.missing_inputs
    assert lifecycle is TrendLifecycle.NEW


def test_repeated_same_source_item_is_one_observation_window() -> None:
    original = point(1, news_count=3, source_item_key="same-rss-item")
    repeated = replace(original, observed_at=AS_OF - timedelta(minutes=5))

    extracted = FeatureExtractor().extract([original, repeated], AS_OF)
    score = ExplainableScorer().score(extracted.signal)
    lifecycle = LifecycleDetector().detect(
        LifecycleContext(
            first_seen_at=extracted.first_seen_at,
            current_strength=extracted.current_strength,
            previous_strength=0,
            current_observations=extracted.current_windows,
            score=score.total,
            baseline_presence=0,
            high_score_windows=extracted.current_windows,
            high_score_duration_hours=extracted.current_span_hours,
        ),
        AS_OF,
    )

    assert extracted.current_observations == 1
    assert extracted.current_windows == 1
    assert lifecycle is TrendLifecycle.NEW


def test_wikimedia_lag_does_not_count_as_high_score_duration() -> None:
    extracted = FeatureExtractor().extract(
        [
            point(1, metric=1_000_000, source_item_key="google-item"),
            point(
                60,
                source=Source.WIKIMEDIA,
                metric=10_000_000,
                source_item_key="wikimedia-item",
            ),
        ],
        AS_OF,
    )
    score = ExplainableScorer().score(extracted.signal)
    high_windows, high_duration = _high_score_state([], AS_OF, score.total)

    lifecycle = LifecycleDetector().detect(
        LifecycleContext(
            first_seen_at=extracted.first_seen_at,
            current_strength=extracted.current_strength,
            previous_strength=0,
            current_observations=extracted.current_windows,
            score=score.total,
            baseline_presence=0,
            high_score_windows=high_windows,
            high_score_duration_hours=high_duration,
        ),
        AS_OF,
    )

    assert score.total >= 70
    assert extracted.current_span_hours == 59
    assert high_windows == 1
    assert high_duration == 0
    assert lifecycle is TrendLifecycle.RISING


def test_high_score_history_uses_distinct_persisted_windows_not_run_count() -> None:
    repeated_runs = [
        SimpleNamespace(as_of=AS_OF - timedelta(minutes=minute), total_score=90)
        for minute in (3, 2, 1)
    ]

    windows, duration = _high_score_state(repeated_runs, AS_OF, 90)

    assert windows == 1
    assert duration == 3 / 60


def test_high_score_history_requires_actual_six_hour_persistence() -> None:
    history = [SimpleNamespace(as_of=AS_OF - timedelta(hours=6), total_score=90)]

    windows, duration = _high_score_state(history, AS_OF, 90)

    assert windows == 2
    assert duration == 6


def _add_observation(
    db_session,
    *,
    index: int,
    timestamp: datetime,
    metric: int,
    observed_at: datetime | None = None,
) -> SourceObservation:
    run = CollectionRun(
        run_key=f"detection:{index}",
        source=Source.GOOGLE_TRENDS,
        started_at=timestamp,
        completed_at=timestamp,
        status=RunStatus.SUCCEEDED,
    )
    payload = RawPayload(
        source=Source.GOOGLE_TRENDS,
        payload_hash=f"{index:064d}",
        raw_payload={"data": ""},
        collected_at=timestamp,
        source_timestamp=timestamp,
        collector_version="test",
        parser_version="test",
    )
    db_session.add_all([run, payload])
    db_session.flush()
    observation = SourceObservation(
        run_id=run.id,
        raw_payload_id=payload.id,
        source=Source.GOOGLE_TRENDS,
        source_item_id=f"detection:{index}",
        canonical_text="topic",
        source_timestamp=timestamp,
        observed_at=observed_at or timestamp,
        source_url="https://trends.google.com/trending/rss?geo=KR",
        metrics={
            "approx_traffic_lower_bound": metric,
            "news_items": [{"title": "news"}],
        },
    )
    db_session.add(observation)
    db_session.flush()
    return observation


def test_detector_persists_one_explainable_snapshot_idempotently(db_session) -> None:
    observations = [
        _add_observation(db_session, index=1, timestamp=AS_OF - timedelta(hours=7), metric=100),
        _add_observation(db_session, index=2, timestamp=AS_OF - timedelta(hours=1), metric=200),
    ]
    candidate = TrendCandidate(
        source=Source.GOOGLE_TRENDS,
        canonical_text="topic",
        normalized_text="topic",
        first_seen_at=AS_OF - timedelta(hours=7),
        last_seen_at=AS_OF - timedelta(hours=1),
        status=CandidateStatus.ACTIVE,
        resolution_status=ResolutionStatus.RESOLVED,
        normalizer_version="normalizer-v1",
        generation=1,
    )
    entity = TrendEntity(
        canonical_name="topic",
        normalized_name="topic",
        wikidata_id="Q_DETECTION",
        entity_type=None,
        entity_types=[],
        resolution_status=ResolutionStatus.RESOLVED,
        review_status=ReviewStatus.PENDING,
        version=1,
    )
    run = PipelineRun(
        kind=RunKind.LIVE,
        as_of=AS_OF,
        started_at=AS_OF,
        status=RunStatus.RUNNING,
        normalizer_version="normalizer-v1",
        entity_version="entity-v1",
        classifier_version="classifier-v1",
        score_version="score-v1",
        prompt_version="prompt-v1",
    )
    db_session.add_all([candidate, entity, run])
    db_session.flush()
    db_session.add_all(
        CandidateObservation(candidate_id=candidate.id, observation_id=observation.id)
        for observation in observations
    )
    EntityRepository(db_session).link_candidate(entity.id, candidate.id, "test")
    db_session.flush()
    detector = TrendDetector(db_session, now=lambda: AS_OF)

    first = detector.snapshot(entity.id, AS_OF, pipeline_run_id=run.id)
    second = detector.snapshot(entity.id, AS_OF, pipeline_run_id=run.id)

    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert first.lifecycle is TrendLifecycle.RISING
    assert first.total_score == 60.0
    assert first.breakdown["interpretation"] == "internal_relative_score_not_probability"
    assert first.breakdown["components"]["cross_source"] == 0
    assert db_session.scalar(select(func.count()).select_from(TrendSnapshot)) == 1

    entity.resolution_status = ResolutionStatus.NEEDS_REVIEW
    assert detector.snapshot(
        entity.id, AS_OF + timedelta(minutes=1), pipeline_run_id=run.id
    ) is None
    assert db_session.scalar(select(func.count()).select_from(TrendSnapshot)) == 1


@pytest.mark.parametrize(
    ("source_timestamp", "observed_at"),
    [
        (AS_OF + timedelta(minutes=2), AS_OF + timedelta(minutes=3)),
        (AS_OF - timedelta(minutes=2), AS_OF + timedelta(minutes=1)),
    ],
)
def test_cutoff_excluded_observation_cannot_create_new_snapshot(
    db_session, source_timestamp: datetime, observed_at: datetime
) -> None:
    observation = _add_observation(
        db_session,
        index=90,
        timestamp=source_timestamp,
        observed_at=observed_at,
        metric=10_000,
    )
    candidate = TrendCandidate(
        source=Source.GOOGLE_TRENDS,
        canonical_text="future topic",
        normalized_text="future topic",
        first_seen_at=source_timestamp,
        last_seen_at=source_timestamp,
        status=CandidateStatus.ACTIVE,
        resolution_status=ResolutionStatus.RESOLVED,
        normalizer_version="normalizer-v1",
        generation=1,
    )
    entity = TrendEntity(
        canonical_name="future topic",
        normalized_name="future topic",
        wikidata_id="Q_FUTURE_DETECTION",
        entity_type=None,
        entity_types=[],
        resolution_status=ResolutionStatus.RESOLVED,
        review_status=ReviewStatus.PENDING,
        version=1,
    )
    run = PipelineRun(
        kind=RunKind.LIVE,
        as_of=AS_OF,
        started_at=AS_OF,
        status=RunStatus.RUNNING,
        normalizer_version="normalizer-v1",
        entity_version="entity-v1",
        classifier_version="classifier-v1",
        score_version="score-v1",
        prompt_version="prompt-v1",
    )
    db_session.add_all([candidate, entity, run])
    db_session.flush()
    db_session.add(
        CandidateObservation(candidate_id=candidate.id, observation_id=observation.id)
    )
    assert EntityRepository(db_session).link_candidate(entity.id, candidate.id, "test")

    snapshot = TrendDetector(db_session, now=lambda: AS_OF).snapshot(
        entity.id, AS_OF, pipeline_run_id=run.id
    )

    assert snapshot is None
    assert db_session.scalar(select(func.count()).select_from(TrendSnapshot)) == 0
