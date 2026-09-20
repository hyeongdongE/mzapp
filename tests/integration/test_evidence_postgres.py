from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.ai.contracts import UNKNOWN_CAUSE_MESSAGE
from app.ai.summary import SummaryService
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
    Claim,
    ClaimEvidence,
    ClaimSnapshot,
    CollectionRun,
    EntityCandidate,
    Evidence,
    PipelineRun,
    RawPayload,
    SourceObservation,
    SummaryCache,
    TrendCandidate,
    TrendEntity,
    TrendSnapshot,
)

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="TEST_DATABASE_URL is required for PostgreSQL evidence verification",
)
AS_OF = datetime(2026, 9, 21, 1, 30, tzinfo=UTC)


@pytest.mark.asyncio
async def test_postgres_persists_idempotent_claim_evidence_and_snapshot_provenance() -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL)
    with Session(engine) as session:
        collection = CollectionRun(
            run_key="evidence-postgres",
            source=Source.GOOGLE_TRENDS,
            started_at=AS_OF,
            completed_at=AS_OF,
            status=RunStatus.SUCCEEDED,
        )
        payload = RawPayload(
            source=Source.GOOGLE_TRENDS,
            payload_hash="9" * 64,
            raw_payload={"data": ""},
            collected_at=AS_OF,
            source_timestamp=AS_OF,
            collector_version="test",
            parser_version="test",
        )
        run = PipelineRun(
            kind=RunKind.LIVE,
            as_of=AS_OF,
            started_at=AS_OF,
            completed_at=AS_OF,
            status=RunStatus.SUCCEEDED,
            normalizer_version="normalizer-v1",
            entity_version="entity-v1",
            classifier_version="classifier-v1",
            score_version="score-v1",
            prompt_version="prompt-v1",
        )
        entity = TrendEntity(
            canonical_name="postgres evidence topic",
            normalized_name="postgres evidence topic",
            wikidata_id="Q_EVIDENCE_POSTGRES",
            resolution_status=ResolutionStatus.RESOLVED,
            entity_types=[],
            review_status=ReviewStatus.PENDING,
            version=1,
        )
        session.add_all([collection, payload, run, entity])
        session.flush()
        observation = SourceObservation(
            run_id=collection.id,
            raw_payload_id=payload.id,
            source=Source.GOOGLE_TRENDS,
            source_item_id="evidence-postgres",
            canonical_text=entity.canonical_name,
            source_timestamp=AS_OF,
            observed_at=AS_OF,
            source_url="https://trends.google.com/trending/rss?geo=KR",
            metrics={"traffic": 100},
        )
        snapshot = TrendSnapshot(
            entity_id=entity.id,
            pipeline_run_id=run.id,
            as_of=AS_OF,
            lifecycle=TrendLifecycle.RISING,
            total_score=80,
            breakdown={},
            missing_inputs=[],
            score_version="score-v1",
            system_detected_at=AS_OF,
        )
        session.add_all([observation, snapshot])
        session.flush()
        candidate = TrendCandidate(
            source=Source.GOOGLE_TRENDS,
            canonical_text=entity.canonical_name,
            normalized_text=entity.normalized_name,
            first_seen_at=AS_OF,
            last_seen_at=AS_OF,
            status=CandidateStatus.ACTIVE,
            resolution_status=ResolutionStatus.RESOLVED,
            normalizer_version="normalizer-v1",
            generation=1,
        )
        session.add(candidate)
        session.flush()
        session.add_all(
            [
                CandidateObservation(
                    candidate_id=candidate.id, observation_id=observation.id
                ),
                EntityCandidate(
                    entity_id=entity.id,
                    candidate_id=candidate.id,
                    entity_version="entity-v1",
                    match_reason="test",
                ),
            ]
        )
        session.add(
            Evidence(
                entity_id=entity.id,
                observation_id=observation.id,
                source=Source.GOOGLE_TRENDS,
                kind="TREND_SIGNAL",
                fact={
                    "canonical_text": entity.canonical_name,
                    "metrics": {"traffic": 100},
                    "source_timestamp": AS_OF.isoformat(),
                },
                source_url=observation.source_url,
                observed_at=AS_OF,
            )
        )
        session.flush()
        service = SummaryService(session)

        first = await service.generate_top(
            as_of=AS_OF,
            top_n=1,
            prompt_version="prompt-v1",
            score_version="score-v1",
        )
        second = await service.generate_top(
            as_of=AS_OF,
            top_n=1,
            prompt_version="prompt-v1",
            score_version="score-v1",
        )
        session.commit()

        assert [claim.id for claim in first] == [claim.id for claim in second]
        assert len(first) == 2

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Claim)) == 2
        assert session.scalar(select(func.count()).select_from(ClaimEvidence)) == 2
        assert session.scalar(select(func.count()).select_from(ClaimSnapshot)) == 2
        assert session.scalar(select(func.count()).select_from(SummaryCache)) == 1
        cause = session.scalar(select(Claim).where(Claim.kind == "CAUSE"))
        assert cause is not None
        assert cause.text == UNKNOWN_CAUSE_MESSAGE
        assert cause.publishable is True
        link = session.scalar(
            select(ClaimSnapshot).where(ClaimSnapshot.claim_id == cause.id)
        )
        assert link is not None
        persisted_snapshot = session.get(TrendSnapshot, link.snapshot_id)
        assert persisted_snapshot is not None
        assert persisted_snapshot.as_of.tzinfo is not None
    engine.dispose()
