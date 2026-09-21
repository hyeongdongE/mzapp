from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import Category, CategoryAvailability
from app.models.tables import CategorySetting


class CategorySettingsService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list(self) -> list[CategorySetting]:
        return list(
            self._session.scalars(
                select(CategorySetting).order_by(CategorySetting.category)
            )
        )

    def set_status(
        self,
        category: Category,
        status: CategoryAvailability,
        *,
        actor: str,
        rationale: str,
        now: datetime | None = None,
    ) -> CategorySetting:
        if category is Category.OTHER:
            raise ValueError("OTHER cannot be exposed to users")
        if not actor.strip() or not rationale.strip():
            raise ValueError("actor and rationale are required")
        row = self._session.get(CategorySetting, category)
        timestamp = now or datetime.now(UTC)
        if row is None:
            row = CategorySetting(
                category=category,
                status=status,
                rationale=rationale.strip(),
                updated_by=actor.strip(),
                updated_at=timestamp,
            )
            self._session.add(row)
        else:
            row.status = status
            row.rationale = rationale.strip()
            row.updated_by = actor.strip()
            row.updated_at = timestamp
        self._session.flush()
        return row
