from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.enums import Category, DataMode, TrendLifecycle
from app.models.tables import (
    AnonymousUser,
    NotificationPreference,
    ProductEvent,
    ProductTrendCard,
    SavedTrend,
    TrendFeedback,
    TrendInteraction,
    UserInterest,
)

DEMO_FIXTURES = (
    ("entertainment", Category.ENTERTAINMENT, "[DEMO] 신인 그룹 라이브 클립"),
    ("ai-tech", Category.AI_TECH, "[DEMO] 온디바이스 AI 도구"),
    ("food", Category.FOOD, "[DEMO] 피스타치오 디저트"),
    ("game", Category.GAME, "[DEMO] 협동 생존 게임"),
)


class DemoDataService:
    def __init__(self, session: Session, *, enabled: bool) -> None:
        self._session = session
        self._enabled = enabled

    def _require_enabled(self) -> None:
        if not self._enabled:
            raise RuntimeError("DEMO_MODE_ENABLED=true is required")

    def seed(self, now: datetime | None = None) -> int:
        self._require_enabled()
        timestamp = now or datetime.now(UTC)
        created = 0
        for index, (key, category, title) in enumerate(DEMO_FIXTURES):
            existing = self._session.scalar(
                select(ProductTrendCard).where(
                    ProductTrendCard.data_mode == DataMode.DEMO,
                    ProductTrendCard.fixture_key == key,
                )
            )
            if existing is not None:
                continue
            observed = timestamp - timedelta(hours=index + 1)
            self._session.add(
                ProductTrendCard(
                    public_id=str(uuid4()),
                    data_mode=DataMode.DEMO,
                    fixture_key=key,
                    title=title,
                    category=category,
                    lifecycle=(TrendLifecycle.RISING if index % 2 else TrendLifecycle.NEW),
                    what_text="UX 검증을 위해 만든 명시적 DEMO 설명입니다.",
                    interest_text="DEMO 데이터에서 최근 관심 증가 흐름을 재현합니다.",
                    cause_text=(
                        "DEMO 시나리오의 확산 계기입니다. 실제 관측 근거가 아닙니다."
                    ),
                    sources=[
                        {
                            "source": "DEMO_FIXTURE",
                            "url": f"https://example.invalid/trend-radar-demo/{key}",
                            "observedAt": observed.isoformat(),
                        }
                    ],
                    first_seen_at=observed,
                    observed_at=observed,
                    trend_score=80.0 - index * 7,
                    auto_pipeline_result=True,
                    fixture_approved=True,
                    suppressed=False,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
            created += 1
        self._session.flush()
        return created

    def cleanup(self, *, execute: bool) -> int:
        self._require_enabled()
        card_ids = list(
            self._session.scalars(
                select(ProductTrendCard.id).where(
                    ProductTrendCard.data_mode == DataMode.DEMO
                )
            )
        )
        if not execute:
            return len(card_ids)
        if card_ids:
            for model in (TrendFeedback, SavedTrend, TrendInteraction):
                self._session.execute(delete(model).where(model.card_id.in_(card_ids)))
        self._session.execute(
            delete(ProductEvent).where(ProductEvent.data_mode == DataMode.DEMO)
        )
        demo_user_ids = select(AnonymousUser.id).where(
            AnonymousUser.data_mode == DataMode.DEMO
        )
        self._session.execute(
            delete(NotificationPreference).where(
                NotificationPreference.user_id.in_(demo_user_ids)
            )
        )
        self._session.execute(
            delete(UserInterest).where(UserInterest.user_id.in_(demo_user_ids))
        )
        self._session.execute(
            delete(AnonymousUser).where(AnonymousUser.data_mode == DataMode.DEMO)
        )
        self._session.execute(
            delete(ProductTrendCard).where(ProductTrendCard.data_mode == DataMode.DEMO)
        )
        self._session.flush()
        return len(card_ids)
