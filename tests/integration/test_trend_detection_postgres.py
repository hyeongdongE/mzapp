from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
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
