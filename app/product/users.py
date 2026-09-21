from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.enums import (
    Category,
    CategoryAvailability,
    NotificationMode,
)
from app.models.tables import (
    AnonymousUser,
    CategorySetting,
    NotificationPreference,
    UserInterest,
)


def credential_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class UserService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, now: datetime | None = None) -> tuple[AnonymousUser, str]:
        timestamp = now or datetime.now(UTC)
        token = secrets.token_urlsafe(32)
        user = AnonymousUser(
            id=str(uuid4()),
            credential_hash=credential_hash(token),
            created_at=timestamp,
            last_seen_at=timestamp,
        )
        self._session.add(user)
        self._session.flush()
        return user, token

    def find(self, token: str, now: datetime | None = None) -> AnonymousUser | None:
        user = self._session.scalar(
            select(AnonymousUser).where(
                AnonymousUser.credential_hash == credential_hash(token)
            )
        )
        if user is not None:
            user.last_seen_at = now or datetime.now(UTC)
            self._session.flush()
        return user

    def selectable_categories(self) -> list[CategorySetting]:
        return list(
            self._session.scalars(
                select(CategorySetting)
                .where(
                    CategorySetting.status.in_(
                        [CategoryAvailability.EXPERIMENTAL, CategoryAvailability.ENABLED]
                    )
                )
                .order_by(CategorySetting.category)
            )
        )

    def interests(self, user_id: str) -> list[Category]:
        return list(
            self._session.scalars(
                select(UserInterest.category)
                .where(UserInterest.user_id == user_id)
                .order_by(UserInterest.category)
            )
        )

    def replace_interests(
        self, user_id: str, categories: list[Category], now: datetime | None = None
    ) -> list[Category]:
        unique = sorted(set(categories), key=lambda item: item.value)
        if not unique or Category.OTHER in unique:
            raise ValueError("select at least one available category")
        allowed = {row.category for row in self.selectable_categories()}
        if not set(unique) <= allowed:
            raise ValueError("one or more categories are not available")
        timestamp = now or datetime.now(UTC)
        self._session.execute(delete(UserInterest).where(UserInterest.user_id == user_id))
        self._session.add_all(
            UserInterest(user_id=user_id, category=category, created_at=timestamp)
            for category in unique
        )
        self._session.flush()
        return unique

    def notification_mode(self, user_id: str) -> NotificationMode:
        preference = self._session.get(NotificationPreference, user_id)
        return preference.mode if preference else NotificationMode.OFF

    def set_notification_mode(
        self, user_id: str, mode: NotificationMode, now: datetime | None = None
    ) -> NotificationMode:
        preference = self._session.get(NotificationPreference, user_id)
        timestamp = now or datetime.now(UTC)
        if preference is None:
            preference = NotificationPreference(
                user_id=user_id, mode=mode, updated_at=timestamp
            )
            self._session.add(preference)
        else:
            preference.mode = mode
            preference.updated_at = timestamp
        self._session.flush()
        return mode
