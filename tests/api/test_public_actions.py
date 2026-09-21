from sqlalchemy import func, select

from app.models.enums import FeedbackType
from app.models.tables import SavedTrend, TrendFeedback, TrendInteraction
from tests.api.public_fixtures import authenticate_with_interest, seed_live_card


def test_feedback_upserts_for_current_user(client, api_session) -> None:
    card = seed_live_card(api_session)
    authenticate_with_interest(client)

    first = client.put(
        f"/api/public/trends/{card.public_id}/feedback",
        json={"feedbackType": "NEW_AND_USEFUL"},
    )
    second = client.put(
        f"/api/public/trends/{card.public_id}/feedback",
        json={"feedbackType": "INCORRECT"},
    )

    assert first.status_code == second.status_code == 200
    assert api_session.scalar(select(func.count()).select_from(TrendFeedback)) == 1
    feedback = api_session.scalar(select(TrendFeedback))
    assert feedback.feedback_type is FeedbackType.INCORRECT


def test_save_is_idempotent_and_delete_is_scoped(client, api_session) -> None:
    card = seed_live_card(api_session)
    authenticate_with_interest(client)

    assert client.put(f"/api/public/trends/{card.public_id}/save").status_code == 200
    assert client.put(f"/api/public/trends/{card.public_id}/save").status_code == 200
    assert api_session.scalar(select(func.count()).select_from(SavedTrend)) == 1
    assert client.get("/api/public/saved").json()["items"][0]["trendId"] == card.public_id
    assert client.delete(f"/api/public/trends/{card.public_id}/save").status_code == 204
    assert api_session.scalar(select(func.count()).select_from(SavedTrend)) == 0


def test_open_count_is_aggregated_per_user_and_card(client, api_session) -> None:
    card = seed_live_card(api_session)
    authenticate_with_interest(client)

    client.get(f"/api/public/trends/{card.public_id}")
    client.get(f"/api/public/trends/{card.public_id}")

    interaction = api_session.scalar(select(TrendInteraction))
    assert interaction is not None
    assert interaction.open_count == 2


def test_wrong_mode_or_unknown_card_actions_return_not_found(client, api_session) -> None:
    seed_live_card(api_session)
    authenticate_with_interest(client)

    assert client.put(
        "/api/public/trends/not-a-card/feedback",
        json={"feedbackType": "NEW_AND_USEFUL"},
    ).status_code == 404
