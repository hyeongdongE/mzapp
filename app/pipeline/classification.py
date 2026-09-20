from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.enums import Category
from app.models.tables import EntityClassification, TrendEntity

CLASSIFIER_VERSION = "classifier-v1"

INSTANCE_RULES = {
    "Q349": Category.SPORTS,
    "Q11424": Category.ENTERTAINMENT,
    "Q7889": Category.GAME,
    "Q2095": Category.FOOD,
}

DESCRIPTION_RULES = (
    (Category.SPORTS, ("농구", "축구", "야구", "선수", "athlete", "player")),
    (Category.ENTERTAINMENT, ("배우", "가수", "영화", "드라마", "actor", "singer")),
    (Category.AI_TECH, ("인공지능", "소프트웨어", "반도체", "artificial intelligence", "ai ")),
    (Category.FOOD, ("음식", "요리", "식당", "food", "restaurant")),
    (Category.GAME, ("비디오 게임", "게임", "video game")),
    (Category.MEME_INTERNET, ("인터넷 밈", "밈", "internet meme")),
    (Category.FASHION_BEAUTY, ("화장품", "패션", "뷰티", "cosmetic", "fashion")),
    (Category.SHOPPING_PRODUCT, ("제품", "쇼핑", "상품", "product", "retail")),
)


@dataclass(frozen=True)
class ClassificationResult:
    category: Category
    confidence: float
    reason: str
    classifier_version: str = CLASSIFIER_VERSION


class EntityClassifier:
    def classify(self, entity: TrendEntity) -> ClassificationResult:
        if entity.entity_type in INSTANCE_RULES:
            category = INSTANCE_RULES[entity.entity_type]
            return ClassificationResult(category, 1.0, f"INSTANCE_OF:{entity.entity_type}")
        description = (entity.description or "").casefold()
        for category, tokens in DESCRIPTION_RULES:
            for token in tokens:
                if token in description:
                    return ClassificationResult(category, 0.9, f"DESCRIPTION_TOKEN:{token}")
        return ClassificationResult(Category.OTHER, 0.0, "NO_MATCH_NEEDS_REVIEW")

    def persist(
        self,
        session: Session,
        entity: TrendEntity,
        *,
        pipeline_run_id: int,
        classified_at: datetime,
    ) -> EntityClassification:
        result = self.classify(entity)
        classification = EntityClassification(
            entity_id=entity.id,
            pipeline_run_id=pipeline_run_id,
            category=result.category,
            confidence=result.confidence,
            reason=result.reason,
            classifier_version=result.classifier_version,
            classified_at=classified_at,
        )
        session.add(classification)
        entity.category = result.category
        session.flush()
        return classification
