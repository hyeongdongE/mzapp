from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.evaluation.database import evaluate_day
from app.models.enums import (
    CandidateStatus,
    Category,
    EvidenceStatus,
    HumanEvaluationLabel,
    ResolutionStatus,
    ReviewAction,
    ReviewStatus,
    RunKind,
    RunStatus,
    Source,
    TrendLifecycle,
)
from app.models.tables import (
    CandidateObservation,
    Claim,
    CollectionRun,
    CostRecord,
    EntityCandidate,
    EntityClassification,
    HumanEvaluation,
    PipelineRun,
    RawPayload,
    Review,
    SourceObservation,
    TrendCandidate,
    TrendEntity,
    TrendSnapshot,
)

DAY = date(2026, 9, 20)
START = datetime(2026, 9, 20, tzinfo=UTC)


def test_evaluate_day_reads_period_facts_without_future_rows(db_session: Session) -> None:
    entity = TrendEntity(
        canonical_name="evaluation topic",
        normalized_name="evaluation topic",
        wikidata_id="Q_EVALUATION",
        resolution_status=ResolutionStatus.RESOLVED,
        entity_types=[],
        category=Category.SPORTS,
        review_status=ReviewStatus.APPROVED,
        version=2,
        created_at=START + timedelta(hours=2),
        updated_at=START + timedelta(hours=12),
    )
    pipeline = PipelineRun(
        kind=RunKind.LIVE,
        as_of=START + timedelta(hours=2),
        started_at=START + timedelta(hours=2),
        completed_at=START + timedelta(hours=3),
        status=RunStatus.SUCCEEDED,
        normalizer_version="normalizer-v1",
        entity_version="entity-v1",
        classifier_version="classifier-v1",
        score_version="score-v1",
        prompt_version="prompt-v1",
    )
    db_session.add_all([entity, pipeline])
    db_session.flush()
    db_session.add(
        EntityClassification(
            entity_id=entity.id,
            pipeline_run_id=pipeline.id,
            category=Category.SPORTS,
            confidence=1,
            reason="TEST",
            classifier_version="classifier-v1",
            classified_at=START + timedelta(hours=2),
        )
    )

    for index, source in enumerate((Source.GOOGLE_TRENDS, Source.WIKIMEDIA), start=1):
        observed_at = START + timedelta(hours=index)
        collection = CollectionRun(
            run_key=f"evaluation-{index}",
            source=source,
            started_at=observed_at,
            completed_at=observed_at,
            status=RunStatus.SUCCEEDED,
        )
        payload = RawPayload(
            source=source,
            payload_hash=f"{index:064d}",
            raw_payload={"data": ""},
            collected_at=observed_at,
            source_timestamp=observed_at,
            collector_version=f"{source.value.lower()}-collector-v1",
            parser_version=f"{source.value.lower()}-parser-v1",
        )
        candidate = TrendCandidate(
            source=source,
            canonical_text=f"evaluation topic {index}",
            normalized_text=f"evaluation topic {index}",
            first_seen_at=observed_at,
            last_seen_at=observed_at,
            status=CandidateStatus.ACTIVE,
            resolution_status=ResolutionStatus.RESOLVED,
            normalizer_version="normalizer-v1",
            generation=1,
        )
        db_session.add_all([collection, payload, candidate])
        db_session.flush()
        observation = SourceObservation(
            run_id=collection.id,
            raw_payload_id=payload.id,
            source=source,
            source_item_id=f"evaluation-{index}",
            canonical_text=candidate.canonical_text,
            source_timestamp=observed_at,
            observed_at=observed_at,
            source_url=(
                "https://trends.google.com/trending/rss?geo=KR"
                if source is Source.GOOGLE_TRENDS
                else "https://wikimedia.org/api/rest_v1/metrics/pageviews/top-per-country/KR/all-access/2026/09/19"
            ),
            metrics={"value": index},
        )
        db_session.add(observation)
        db_session.flush()
        db_session.add_all(
            [
                CandidateObservation(candidate_id=candidate.id, observation_id=observation.id),
                EntityCandidate(
                    entity_id=entity.id,
                    candidate_id=candidate.id,
                    entity_version="entity-v1",
                    match_reason="TEST",
                ),
            ]
        )

    db_session.add_all(
        [
            TrendSnapshot(
                entity_id=entity.id,
                pipeline_run_id=pipeline.id,
                as_of=START + timedelta(hours=2),
                lifecycle=TrendLifecycle.RISING,
                total_score=75,
                breakdown={},
                missing_inputs=[],
                score_version="score-v1",
                system_detected_at=START + timedelta(hours=3),
            ),
            Review(
                entity_id=entity.id,
                action=ReviewAction.APPROVE,
                actor="reviewer",
                payload={},
                created_at=START + timedelta(hours=12),
            ),
            HumanEvaluation(
                entity_id=entity.id,
                label=HumanEvaluationLabel.VALID_TREND,
                actor="reviewer",
                created_at=START + timedelta(hours=13),
            ),
            Claim(
                entity_id=entity.id,
                kind="INTEREST",
                text="blocked",
                status=EvidenceStatus.UNSUPPORTED,
                reason="TEST",
                publishable=False,
                prompt_version="prompt-v1",
                evidence_set_hash="e" * 64,
                created_at=START + timedelta(hours=14),
            ),
            CostRecord(
                pipeline_run_id=pipeline.id,
                cost_type="API",
                amount=Decimal("0.10"),
                human_minutes=0,
                currency="USD",
                metadata_json={},
                recorded_at=START + timedelta(hours=15),
            ),
            CostRecord(
                pipeline_run_id=None,
                cost_type="HUMAN",
                amount=Decimal("0"),
                human_minutes=6,
                currency="USD",
                metadata_json={"hourly_rate": "20"},
                recorded_at=START + timedelta(hours=16),
            ),
        ]
    )
    db_session.commit()

    result = evaluate_day(db_session, DAY)

    assert result.supply.raw_candidates == 2
    assert result.supply.unique_candidates == 2
    assert result.supply.trend_entities == 1
    assert result.supply.approved_cards == 1
    assert result.coverage[Category.SPORTS].candidates == 1
    assert result.coverage[Category.SPORTS].valid_cards == 1
    assert result.quality.precision == Decimal("1.0000")
    assert result.quality.unsupported_summary_rate == Decimal("1.0000")
    assert result.cross_source.rate == Decimal("1.0000")
    assert result.freshness.detection_p50_minutes == Decimal("120.00")
    assert result.freshness.approval_p50_minutes == Decimal("540.00")
    assert result.cost.total_cost == Decimal("2.100000")
    assert result.versions["score"] == ("score-v1",)


def test_evaluate_day_does_not_read_future_evaluations(db_session: Session) -> None:
    db_session.add(
        TrendEntity(
            canonical_name="future entity",
            normalized_name="future entity",
            wikidata_id="Q_EVALUATION_FUTURE",
            resolution_status=ResolutionStatus.RESOLVED,
            entity_types=[],
            review_status=ReviewStatus.PENDING,
            version=1,
            created_at=START,
            updated_at=START,
        )
    )
    db_session.flush()
    entity_id = db_session.query(TrendEntity.id).scalar()
    db_session.add(
        HumanEvaluation(
            entity_id=entity_id,
            label=HumanEvaluationLabel.DUPLICATE,
            actor="future",
            created_at=START + timedelta(days=1),
        )
    )
    db_session.commit()

    result = evaluate_day(db_session, DAY)

    assert result.quality.reviewed == 0
    assert result.quality.duplicate_rate is None


def test_approval_delay_uses_original_detection_from_prior_day(db_session: Session) -> None:
    detected_at = START - timedelta(hours=3)
    pipeline = PipelineRun(
        kind=RunKind.LIVE,
        as_of=detected_at,
        started_at=detected_at,
        completed_at=detected_at,
        status=RunStatus.SUCCEEDED,
        normalizer_version="normalizer-v1",
        entity_version="entity-v1",
        classifier_version="classifier-v1",
        score_version="score-v1",
        prompt_version="prompt-v1",
    )
    entity = TrendEntity(
        canonical_name="prior detection",
        normalized_name="prior detection",
        wikidata_id="Q_PRIOR_DETECTION",
        resolution_status=ResolutionStatus.RESOLVED,
        entity_types=[],
        category=Category.OTHER,
        review_status=ReviewStatus.APPROVED,
        version=2,
        created_at=detected_at,
        updated_at=START + timedelta(hours=1),
    )
    db_session.add_all([pipeline, entity])
    db_session.flush()
    db_session.add_all(
        [
            TrendSnapshot(
                entity_id=entity.id,
                pipeline_run_id=pipeline.id,
                as_of=detected_at,
                lifecycle=TrendLifecycle.NEW,
                total_score=50,
                breakdown={},
                missing_inputs=[],
                score_version="score-v1",
                system_detected_at=detected_at,
            ),
            Review(
                entity_id=entity.id,
                action=ReviewAction.APPROVE,
                actor="reviewer",
                payload={},
                created_at=START + timedelta(hours=1),
            ),
        ]
    )
    db_session.commit()

    result = evaluate_day(db_session, DAY)

    assert result.freshness.detection_samples == 0
    assert result.freshness.approval_samples == 1
    assert result.freshness.approval_p50_minutes == Decimal("240.00")
