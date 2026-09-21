from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.models.enums import (
    Category,
    CategoryAvailability,
    DataMode,
    EvidenceStatus,
    ResolutionStatus,
    ReviewStatus,
    RunKind,
    RunStatus,
    TrendLifecycle,
)
from app.models.tables import (
    CategorySetting,
    Claim,
    ClaimSnapshot,
    PipelineRun,
    ProductTrendCard,
    TrendEntity,
    TrendSnapshot,
)

NOW = datetime(2026, 9, 21, 5, tzinfo=UTC)


def seed_live_card(
    session,
    *,
    title: str = "검증된 트렌드",
    category: Category = Category.AI_TECH,
    score: float = 70.0,
    hours_old: int = 1,
    review_status: ReviewStatus = ReviewStatus.APPROVED,
    category_status: CategoryAvailability = CategoryAvailability.EXPERIMENTAL,
    run_kind: RunKind = RunKind.LIVE,
    run_status: RunStatus = RunStatus.SUCCEEDED,
    publishable: bool = True,
    suppressed: bool = False,
) -> ProductTrendCard:
    setting = session.get(CategorySetting, category)
    if setting is None:
        session.add(
            CategorySetting(
                category=category,
                status=category_status,
                rationale="test evaluation",
                updated_by="test",
                updated_at=NOW,
            )
        )
    else:
        setting.status = category_status
    run = PipelineRun(
        kind=run_kind,
        as_of=NOW - timedelta(hours=hours_old),
        started_at=NOW,
        completed_at=NOW,
        status=run_status,
        normalizer_version="n1",
        entity_version="e1",
        classifier_version="c1",
        score_version="s1",
        prompt_version="p1",
    )
    entity = TrendEntity(
        canonical_name=title,
        normalized_name=title,
        resolution_status=ResolutionStatus.RESOLVED,
        entity_types=[],
        category=category,
        review_status=review_status,
        version=1,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add_all([run, entity])
    session.flush()
    snapshot = TrendSnapshot(
        entity_id=entity.id,
        pipeline_run_id=run.id,
        as_of=run.as_of,
        lifecycle=TrendLifecycle.RISING,
        total_score=score,
        breakdown={},
        missing_inputs=[],
        score_version="s1",
        system_detected_at=run.as_of,
    )
    session.add(snapshot)
    session.flush()
    claim = Claim(
        entity_id=entity.id,
        kind="WHAT",
        text="근거 있는 설명",
        status=EvidenceStatus.SUPPORTED,
        reason="SUPPORTED",
        publishable=publishable,
        prompt_version="p1",
        evidence_set_hash=uuid4().hex * 2,
        created_at=NOW,
    )
    session.add(claim)
    session.flush()
    session.add(ClaimSnapshot(claim_id=claim.id, snapshot_id=snapshot.id))
    card = ProductTrendCard(
        public_id=str(uuid4()),
        data_mode=DataMode.LIVE,
        entity_id=entity.id,
        snapshot_id=snapshot.id,
        pipeline_run_id=run.id,
        title=title,
        category=category,
        lifecycle=TrendLifecycle.RISING,
        what_text="근거 있는 설명",
        interest_text="관심 증가가 관측되었습니다.",
        cause_text=None,
        sources=[
            {
                "source": "WIKIMEDIA",
                "url": "https://wikimedia.org/api/rest_v1/example",
                "observedAt": run.as_of.isoformat(),
            }
        ],
        first_seen_at=run.as_of,
        observed_at=run.as_of,
        trend_score=score,
        auto_pipeline_result=publishable,
        suppressed=suppressed,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(card)
    session.commit()
    return card


def authenticate_with_interest(client, category: Category = Category.AI_TECH) -> None:
    assert client.post("/api/public/session").status_code == 201
    response = client.put(
        "/api/public/me/interests", json={"categories": [category.value]}
    )
    assert response.status_code == 200
