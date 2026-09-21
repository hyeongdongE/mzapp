from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import (
    CandidateStatus,
    HumanEvaluationLabel,
    ResolutionStatus,
    ReviewAction,
    ReviewStatus,
    Source,
)
from app.models.tables import (
    EntityAlias,
    EntityCandidate,
    HumanEvaluation,
    Review,
    TrendCandidate,
    TrendEntity,
)

NOW = datetime(2026, 9, 21, 2, tzinfo=UTC)


def seed_entity(session: Session) -> TrendEntity:
    entity = TrendEntity(
        canonical_name="review target",
        normalized_name="review target",
        wikidata_id="Q_REVIEW",
        resolution_status=ResolutionStatus.RESOLVED,
        entity_types=[],
        review_status=ReviewStatus.PENDING,
        version=1,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(entity)
    session.commit()
    return entity


def test_reject_action_is_audited_and_atomic(
    client: TestClient, api_session: Session
) -> None:
    entity = seed_entity(api_session)

    response = client.post(
        "/reviews",
        data={
            "entity_id": entity.id,
            "action": "REJECT",
            "reason": "NEWS_ONLY",
            "version": 1,
            "actor": "local-reviewer",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    api_session.expire_all()
    review = api_session.scalar(select(Review).where(Review.entity_id == entity.id))
    assert review is not None
    assert review.reason == "NEWS_ONLY"
    assert review.previous_status is ReviewStatus.PENDING
    assert review.resulting_status is ReviewStatus.REJECTED
    assert review.auto_pipeline_result is None
    assert review.human_override_reason == "NEWS_ONLY"
    assert api_session.get(TrendEntity, entity.id).review_status is ReviewStatus.REJECTED
    assert api_session.get(TrendEntity, entity.id).version == 2


def test_stale_review_version_returns_conflict_without_audit(
    client: TestClient, api_session: Session
) -> None:
    entity = seed_entity(api_session)

    response = client.post(
        "/reviews",
        data={
            "entity_id": entity.id,
            "action": "APPROVE",
            "version": 0,
            "actor": "local-reviewer",
        },
    )

    assert response.status_code == 409
    assert api_session.scalar(select(func.count()).select_from(Review)) == 0
    api_session.expire_all()
    assert api_session.get(TrendEntity, entity.id).review_status is ReviewStatus.PENDING


def test_invalid_change_category_is_atomic(
    client: TestClient, api_session: Session
) -> None:
    entity = seed_entity(api_session)

    response = client.post(
        "/reviews",
        data={
            "entity_id": entity.id,
            "action": "CHANGE_CATEGORY",
            "category": "NOT_A_CATEGORY",
            "version": 1,
            "actor": "local-reviewer",
        },
    )

    assert response.status_code == 422
    assert api_session.scalar(select(func.count()).select_from(Review)) == 0
    api_session.expire_all()
    assert api_session.get(TrendEntity, entity.id).version == 1


def test_human_evaluation_label_is_recorded(
    client: TestClient, api_session: Session
) -> None:
    entity = seed_entity(api_session)

    response = client.post(
        "/evaluations",
        data={
            "entity_id": entity.id,
            "label": "VALID_TREND",
            "actor": "local-reviewer",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    evaluation = api_session.scalar(
        select(HumanEvaluation).where(HumanEvaluation.entity_id == entity.id)
    )
    assert evaluation is not None
    assert evaluation.label is HumanEvaluationLabel.VALID_TREND


def test_merge_moves_candidate_and_alias_and_audits_target(
    client: TestClient, api_session: Session
) -> None:
    source = seed_entity(api_session)
    target = TrendEntity(
        canonical_name="merge target",
        normalized_name="merge target",
        wikidata_id="Q_MERGE_TARGET",
        resolution_status=ResolutionStatus.RESOLVED,
        entity_types=[],
        review_status=ReviewStatus.PENDING,
        version=4,
        created_at=NOW,
        updated_at=NOW,
    )
    candidate = TrendCandidate(
        source=Source.GOOGLE_TRENDS,
        canonical_text="merge candidate",
        normalized_text="merge candidate",
        first_seen_at=NOW,
        last_seen_at=NOW,
        status=CandidateStatus.ACTIVE,
        resolution_status=ResolutionStatus.RESOLVED,
        normalizer_version="normalizer-v1",
        generation=1,
    )
    api_session.add_all([target, candidate])
    api_session.flush()
    api_session.add_all(
        [
            EntityCandidate(
                entity_id=source.id,
                candidate_id=candidate.id,
                entity_version="entity-v1",
                match_reason="TEST_FIXTURE",
            ),
            EntityAlias(
                entity_id=source.id,
                alias="shared alias",
                normalized_alias="shared alias",
                language="en",
                source="WIKIDATA_ALIAS",
                approved=True,
            ),
            EntityAlias(
                entity_id=target.id,
                alias="shared alias",
                normalized_alias="shared alias",
                language="en",
                source="WIKIDATA_ALIAS",
                approved=True,
            ),
        ]
    )
    api_session.commit()

    response = client.post(
        "/reviews",
        data={
            "entity_id": source.id,
            "action": "MERGE",
            "target_entity_id": target.id,
            "version": source.version,
            "actor": "local-reviewer",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    api_session.expire_all()
    assert api_session.scalar(
        select(EntityCandidate.entity_id).where(EntityCandidate.candidate_id == candidate.id)
    ) == target.id
    assert api_session.scalar(
        select(func.count()).select_from(EntityAlias).where(EntityAlias.entity_id == target.id)
    ) == 1
    review = api_session.scalar(select(Review).where(Review.entity_id == source.id))
    assert review is not None
    assert review.action is ReviewAction.MERGE
    assert review.payload["target_entity_id"] == target.id
    assert api_session.get(TrendEntity, source.id).review_status is ReviewStatus.REJECTED
    assert api_session.get(TrendEntity, target.id).version == 5


def test_split_moves_only_explicit_candidates(
    client: TestClient, api_session: Session
) -> None:
    source = seed_entity(api_session)
    target = TrendEntity(
        canonical_name="split target",
        normalized_name="split target",
        wikidata_id="Q_SPLIT_TARGET",
        resolution_status=ResolutionStatus.RESOLVED,
        entity_types=[],
        review_status=ReviewStatus.PENDING,
        version=1,
        created_at=NOW,
        updated_at=NOW,
    )
    candidates = [
        TrendCandidate(
            source=Source.GOOGLE_TRENDS,
            canonical_text=f"split candidate {index}",
            normalized_text=f"split candidate {index}",
            first_seen_at=NOW,
            last_seen_at=NOW,
            status=CandidateStatus.ACTIVE,
            resolution_status=ResolutionStatus.RESOLVED,
            normalizer_version="normalizer-v1",
            generation=1,
        )
        for index in range(2)
    ]
    api_session.add_all([target, *candidates])
    api_session.flush()
    api_session.add_all(
        [
            EntityCandidate(
                entity_id=source.id,
                candidate_id=candidate.id,
                entity_version="entity-v1",
                match_reason="TEST_FIXTURE",
            )
            for candidate in candidates
        ]
    )
    api_session.commit()

    response = client.post(
        "/reviews",
        data={
            "entity_id": source.id,
            "action": "SPLIT",
            "target_entity_id": target.id,
            "candidate_ids": str(candidates[0].id),
            "version": source.version,
            "actor": "local-reviewer",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    api_session.expire_all()
    links = dict(
        api_session.execute(
            select(EntityCandidate.candidate_id, EntityCandidate.entity_id)
        ).all()
    )
    assert links[candidates[0].id] == target.id
    assert links[candidates[1].id] == source.id
