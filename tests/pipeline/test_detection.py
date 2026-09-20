from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
from app.pipeline.detection import FeatureExtractor, TrendDetector
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


def _add_observation(
    db_session, *, index: int, timestamp: datetime, metric: int
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
        observed_at=timestamp,
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
