from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

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
from app.pipeline.detection import TrendDetector
from app.repositories.entities import EntityRepository

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="TEST_DATABASE_URL is required for PostgreSQL trend verification",
)
AS_OF = datetime(2026, 9, 21, 0, 0, tzinfo=UTC)


def test_postgres_persists_explainable_score_json_and_timezone() -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL)
    with Session(engine) as session:
        observations = []
        for index, hours_ago, traffic in ((1, 7, 100), (2, 1, 200)):
            timestamp = AS_OF - timedelta(hours=hours_ago)
            collection = CollectionRun(
                run_key=f"score-postgres:{index}",
                source=Source.GOOGLE_TRENDS,
                started_at=timestamp,
                completed_at=timestamp,
                status=RunStatus.SUCCEEDED,
            )
            payload = RawPayload(
                source=Source.GOOGLE_TRENDS,
                payload_hash=f"{index + 100:064d}",
                raw_payload={"data": ""},
                collected_at=timestamp,
                source_timestamp=timestamp,
                collector_version="test",
                parser_version="test",
            )
            session.add_all([collection, payload])
            session.flush()
            observation = SourceObservation(
                run_id=collection.id,
                raw_payload_id=payload.id,
                source=Source.GOOGLE_TRENDS,
                source_item_id=f"score-postgres:{index}",
                canonical_text="postgres topic",
                source_timestamp=timestamp,
                observed_at=timestamp,
                source_url="https://trends.google.com/trending/rss?geo=KR",
                metrics={
                    "approx_traffic_lower_bound": traffic,
                    "news_items": [{"title": "news"}],
                },
            )
            session.add(observation)
            session.flush()
            observations.append(observation)
        candidate = TrendCandidate(
            source=Source.GOOGLE_TRENDS,
            canonical_text="postgres topic",
            normalized_text="postgres topic",
            first_seen_at=AS_OF - timedelta(hours=7),
            last_seen_at=AS_OF - timedelta(hours=1),
            status=CandidateStatus.ACTIVE,
            resolution_status=ResolutionStatus.RESOLVED,
            normalizer_version="normalizer-v1",
            generation=1,
        )
        entity = TrendEntity(
            canonical_name="postgres topic",
            normalized_name="postgres topic",
            wikidata_id="Q_SCORE_POSTGRES",
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
        session.add_all([candidate, entity, run])
        session.flush()
        session.add_all(
            CandidateObservation(candidate_id=candidate.id, observation_id=observation.id)
            for observation in observations
        )
        assert EntityRepository(session).link_candidate(entity.id, candidate.id, "test")
        snapshot = TrendDetector(session, now=lambda: AS_OF).snapshot(
            entity.id, AS_OF, pipeline_run_id=run.id
        )
        assert snapshot is not None
        session.commit()
        snapshot_id = snapshot.id

    with Session(engine) as session:
        persisted = session.scalar(
            select(TrendSnapshot).where(TrendSnapshot.id == snapshot_id)
        )
        assert persisted is not None
        assert persisted.lifecycle is TrendLifecycle.RISING
        assert persisted.total_score == 60.0
        assert persisted.as_of.tzinfo is not None
        assert persisted.breakdown["interpretation"] == "internal_relative_score_not_probability"
        assert persisted.breakdown["components"]["news_only_penalty"] == 1.0
    engine.dispose()


def test_concurrent_snapshot_insert_returns_one_idempotent_row() -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL)
    timestamp = AS_OF - timedelta(hours=1)
    with Session(engine) as session:
        collection = CollectionRun(
            run_key="score-concurrent",
            source=Source.GOOGLE_TRENDS,
            started_at=timestamp,
            completed_at=timestamp,
            status=RunStatus.SUCCEEDED,
        )
        payload = RawPayload(
            source=Source.GOOGLE_TRENDS,
            payload_hash=f"{999:064d}",
            raw_payload={"data": ""},
            collected_at=timestamp,
            source_timestamp=timestamp,
            collector_version="test",
            parser_version="test",
        )
        session.add_all([collection, payload])
        session.flush()
        observation = SourceObservation(
            run_id=collection.id,
            raw_payload_id=payload.id,
            source=Source.GOOGLE_TRENDS,
            source_item_id="score-concurrent",
            canonical_text="concurrent score",
            source_timestamp=timestamp,
            observed_at=timestamp,
            source_url="https://trends.google.com/trending/rss?geo=KR",
            metrics={"approx_traffic_lower_bound": 500, "news_items": []},
        )
        candidate = TrendCandidate(
            source=Source.GOOGLE_TRENDS,
            canonical_text="concurrent score",
            normalized_text="concurrent score",
            first_seen_at=timestamp,
            last_seen_at=timestamp,
            status=CandidateStatus.ACTIVE,
            resolution_status=ResolutionStatus.RESOLVED,
            normalizer_version="normalizer-v1",
            generation=1,
        )
        entity = TrendEntity(
            canonical_name="concurrent score",
            normalized_name="concurrent score",
            wikidata_id="Q_SCORE_CONCURRENT",
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
        session.add_all([observation, candidate, entity, run])
        session.flush()
        session.add(
            CandidateObservation(candidate_id=candidate.id, observation_id=observation.id)
        )
        assert EntityRepository(session).link_candidate(entity.id, candidate.id, "test")
        session.commit()
        entity_id = entity.id
        run_id = run.id

    barrier = Barrier(2)

    def synchronize_snapshot_inserts(
        _conn, _cursor, statement, _parameters, _context, _executemany
    ) -> None:
        if statement.lstrip().upper().startswith("INSERT INTO TREND_SNAPSHOTS"):
            barrier.wait(timeout=10)

    event.listen(engine, "before_cursor_execute", synchronize_snapshot_inserts)

    def create_snapshot() -> int:
        with Session(engine) as session:
            snapshot = TrendDetector(session, now=lambda: AS_OF).snapshot(
                entity_id, AS_OF, pipeline_run_id=run_id
            )
            assert snapshot is not None
            session.commit()
            return snapshot.id

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            snapshot_ids = list(executor.map(lambda _: create_snapshot(), range(2)))
    finally:
        event.remove(engine, "before_cursor_execute", synchronize_snapshot_inserts)

    assert len(set(snapshot_ids)) == 1
    with Session(engine) as session:
        count = session.scalar(
            select(func.count()).select_from(TrendSnapshot).where(
                TrendSnapshot.entity_id == entity_id,
                TrendSnapshot.as_of == AS_OF,
                TrendSnapshot.score_version == "score-v1",
            )
        )
        assert count == 1
    engine.dispose()
