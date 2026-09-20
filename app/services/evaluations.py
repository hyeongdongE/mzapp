from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.enums import HumanEvaluationLabel
from app.models.tables import HumanEvaluation, TrendEntity
from app.services.reviews import EntityNotFound


class EvaluationService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record(
        self,
        entity_id: int,
        label: HumanEvaluationLabel,
        actor: str,
        now: datetime,
    ) -> HumanEvaluation:
        if self._session.get(TrendEntity, entity_id) is None:
            raise EntityNotFound(f"entity {entity_id} not found")
        evaluation = HumanEvaluation(
            entity_id=entity_id,
            label=label,
            actor=actor,
            created_at=now,
        )
        self._session.add(evaluation)
        self._session.flush()
        return evaluation
