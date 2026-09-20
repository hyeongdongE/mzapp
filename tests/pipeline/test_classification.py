from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.models.enums import Category, ResolutionStatus, ReviewStatus, RunKind, RunStatus
from app.models.tables import EntityClassification, PipelineRun, TrendEntity
from app.pipeline.classification import EntityClassifier

AS_OF = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def entity(description: str, entity_type: str | None = None) -> TrendEntity:
    return TrendEntity(
        canonical_name="test",
        normalized_name="test",
        description=description,
        entity_type=entity_type,
        resolution_status=ResolutionStatus.RESOLVED,
        review_status=ReviewStatus.PENDING,
        version=1,
    )


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("대한민국의 농구 선수", Category.SPORTS),
        ("대한민국의 배우", Category.ENTERTAINMENT),
        ("인공지능 소프트웨어 기업", Category.AI_TECH),
        ("한국의 화장품 브랜드", Category.FASHION_BEAUTY),
    ],
)
def test_rule_classification_uses_explicit_description_tokens(description, expected):
    result = EntityClassifier().classify(entity(description))

    assert result.category is expected
    assert result.confidence == 0.9
    assert result.reason.startswith("DESCRIPTION_TOKEN:")


def test_unknown_classification_falls_back_to_other_for_review():
    result = EntityClassifier().classify(entity("분류 근거 없음", entity_type="Q5"))

    assert result.category is Category.OTHER
    assert result.confidence == 0.0
    assert result.reason == "NO_MATCH_NEEDS_REVIEW"


@pytest.mark.parametrize("description", ["가수분해 효소", "선수금 회계 항목"])
def test_korean_tokens_do_not_match_inside_unrelated_compound_words(description):
    result = EntityClassifier().classify(entity(description))

    assert result.category is Category.OTHER
    assert result.reason == "NO_MATCH_NEEDS_REVIEW"


def test_classification_appends_history_instead_of_overwriting(db_session):
    value = entity("대한민국의 농구 선수")
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
    db_session.add_all([value, run])
    db_session.flush()
    classifier = EntityClassifier()

    classifier.persist(db_session, value, pipeline_run_id=run.id, classified_at=AS_OF)
    classifier.persist(db_session, value, pipeline_run_id=run.id, classified_at=AS_OF)

    assert db_session.scalar(select(func.count()).select_from(EntityClassification)) == 2
    assert value.category is Category.SPORTS
