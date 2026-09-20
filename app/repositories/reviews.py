from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tables import Review, TrendEntity


class ReviewRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def entity_for_update(self, entity_id: int) -> TrendEntity | None:
        return self._session.scalar(
            select(TrendEntity).where(TrendEntity.id == entity_id).with_for_update()
        )

    def add(self, review: Review) -> Review:
        self._session.add(review)
        self._session.flush()
        return review
