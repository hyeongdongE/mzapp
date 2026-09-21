from datetime import UTC, datetime

from sqlalchemy import select

from app.models.enums import (
    Category,
    EvidenceStatus,
    ResolutionStatus,
    ReviewStatus,
    RunKind,
    RunStatus,
    Source,
    TrendLifecycle,
)
from app.models.tables import (
    Claim,
    ClaimEvidence,
    ClaimSnapshot,
    Evidence,
    PipelineRun,
    ProductTrendCard,
    TrendEntity,
    TrendSnapshot,
)
from app.product.cards import ProductCardService

NOW = datetime(2026, 9, 21, 3, tzinfo=UTC)


def test_sync_live_projects_only_snapshot_linked_publishable_copy(db_session) -> None:
    run = PipelineRun(
        kind=RunKind.LIVE,
        as_of=NOW,
        started_at=NOW,
        completed_at=NOW,
        status=RunStatus.SUCCEEDED,
        normalizer_version="n1",
        entity_version="e1",
        classifier_version="c1",
        score_version="s1",
        prompt_version="p1",
    )
    entity = TrendEntity(
        canonical_name="검증된 주제",
        normalized_name="검증된 주제",
        resolution_status=ResolutionStatus.RESOLVED,
        entity_types=[],
        category=Category.AI_TECH,
        review_status=ReviewStatus.PENDING,
        version=1,
        created_at=NOW,
        updated_at=NOW,
    )
    db_session.add_all([run, entity])
    db_session.flush()
    snapshot = TrendSnapshot(
        entity_id=entity.id,
        pipeline_run_id=run.id,
        as_of=NOW,
        lifecycle=TrendLifecycle.RISING,
        total_score=71.0,
        breakdown={},
        missing_inputs=[],
        score_version="s1",
        system_detected_at=NOW,
    )
    evidence = Evidence(
        entity_id=entity.id,
        source=Source.WIKIMEDIA,
        kind="TREND_SIGNAL",
        fact={"views": 100},
        source_url="https://wikimedia.org/api/rest_v1/example",
        observed_at=NOW,
        created_at=NOW,
    )
    db_session.add_all([snapshot, evidence])
    db_session.flush()
    claims = [
        Claim(
            entity_id=entity.id,
            kind=kind,
            text=text,
            status=EvidenceStatus.SUPPORTED,
            reason="SUPPORTED",
            publishable=True,
            prompt_version="p1",
            evidence_set_hash=(kind[0].lower() * 64),
            created_at=NOW,
        )
        for kind, text in (
            ("WHAT", "무엇인지 설명"),
            ("INTEREST", "관심 증가가 관측됨"),
        )
    ]
    db_session.add_all(claims)
    db_session.flush()
    for claim in claims:
        db_session.add_all(
            [
                ClaimSnapshot(claim_id=claim.id, snapshot_id=snapshot.id),
                ClaimEvidence(claim_id=claim.id, evidence_id=evidence.id),
            ]
        )
    db_session.flush()

    synced = ProductCardService(db_session).sync_live(NOW)
    card = db_session.scalar(select(ProductTrendCard))

    assert synced == 1
    assert card is not None
    assert card.entity_id == entity.id
    assert card.what_text == "무엇인지 설명"
    assert card.interest_text == "관심 증가가 관측됨"
    assert card.auto_pipeline_result is True
    assert card.sources == [
        {
            "source": "WIKIMEDIA",
            "url": "https://wikimedia.org/api/rest_v1/example",
            "observedAt": NOW.isoformat(),
        }
    ]


def test_sync_live_requires_what_and_interest_claims(db_session) -> None:
    assert ProductCardService(db_session).sync_live(NOW) == 0
    assert db_session.scalar(select(ProductTrendCard)) is None
