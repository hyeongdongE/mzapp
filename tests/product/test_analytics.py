from datetime import timedelta

from app.models.enums import DataMode, FeedbackType
from app.models.tables import (
    AnonymousUser,
    ProductTrendCard,
    SavedTrend,
    TrendFeedback,
    TrendInteraction,
)
from app.product.analytics import ProductAnalytics
from tests.api.public_fixtures import NOW, authenticate_with_interest, seed_live_card

pytest_plugins = ["tests.api.conftest"]


def test_live_metrics_calculate_discovery_open_save_and_feedback_rates(
    client, api_session
) -> None:
    card = seed_live_card(api_session)
    authenticate_with_interest(client)
    client.post(
        "/api/public/events",
        json={"eventType": "TREND_IMPRESSION", "trendId": card.public_id},
    )
    client.get(f"/api/public/trends/{card.public_id}")
    client.put(
        f"/api/public/trends/{card.public_id}/feedback",
        json={"feedbackType": "NEW_AND_USEFUL"},
    )
    client.put(f"/api/public/trends/{card.public_id}/save")

    metrics = ProductAnalytics(api_session).summary(DataMode.LIVE)

    assert metrics["impressions"] == 1
    assert metrics["opens"] == 1
    assert metrics["discovery_value_rate"] == 1.0
    assert metrics["already_known_rate"] == 0.0
    assert metrics["save_rate"] == 1.0


def test_demo_events_never_enter_live_metrics(api_session) -> None:
    user = AnonymousUser(
        id="demo-user",
        credential_hash="d" * 64,
        data_mode=DataMode.DEMO,
        created_at=NOW,
        last_seen_at=NOW,
    )
    card = ProductTrendCard(
        public_id="demo-card",
        data_mode=DataMode.DEMO,
        fixture_key="demo-card",
        title="DEMO",
        category="FOOD",
        lifecycle="RISING",
        what_text="demo",
        interest_text="demo",
        sources=[],
        first_seen_at=NOW,
        observed_at=NOW,
        trend_score=1,
        auto_pipeline_result=True,
        suppressed=False,
        created_at=NOW,
        updated_at=NOW,
    )
    api_session.add_all([user, card])
    api_session.flush()
    api_session.add_all(
        [
            TrendInteraction(
                user_id=user.id,
                card_id=card.id,
                first_impression_at=NOW,
                last_impression_at=NOW,
                impression_count=20,
                open_count=10,
            ),
            TrendFeedback(
                user_id=user.id,
                card_id=card.id,
                feedback_type=FeedbackType.NEW_AND_USEFUL,
                created_at=NOW,
                updated_at=NOW,
            ),
            SavedTrend(user_id=user.id, card_id=card.id, created_at=NOW),
        ]
    )
    api_session.commit()

    assert ProductAnalytics(api_session).summary(DataMode.LIVE)["impressions"] == 0


def test_return_metrics_use_user_first_and_last_seen_dates(api_session) -> None:
    from app.models.tables import AnonymousUser

    api_session.add(
        AnonymousUser(
            id="returning-user",
            credential_hash="a" * 64,
            data_mode=DataMode.LIVE,
            created_at=NOW,
            last_seen_at=NOW + timedelta(days=7, minutes=1),
        )
    )
    api_session.commit()

    metrics = ProductAnalytics(api_session).summary(DataMode.LIVE)

    assert metrics["d1_return_rate"] == 1.0
    assert metrics["d7_return_rate"] == 1.0
