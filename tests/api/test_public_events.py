from sqlalchemy import select

from app.models.enums import ProductEventType
from app.models.tables import ProductEvent, TrendInteraction
from tests.api.public_fixtures import authenticate_with_interest, seed_live_card


def test_impression_event_is_validated_and_updates_interaction(client, api_session) -> None:
    card = seed_live_card(api_session)
    authenticate_with_interest(client)

    response = client.post(
        "/api/public/events",
        json={"eventType": "TREND_IMPRESSION", "trendId": card.public_id},
    )

    assert response.status_code == 202
    event = api_session.scalar(
        select(ProductEvent).where(
            ProductEvent.event_type == ProductEventType.TREND_IMPRESSION
        )
    )
    interaction = api_session.scalar(select(TrendInteraction))
    assert event.event_type is ProductEventType.TREND_IMPRESSION
    assert interaction.impression_count == 1
    assert interaction.first_impression_at is not None


def test_duplicate_impression_within_short_window_is_idempotent(client, api_session) -> None:
    card = seed_live_card(api_session)
    authenticate_with_interest(client)
    payload = {"eventType": "TREND_IMPRESSION", "trendId": card.public_id}

    assert client.post("/api/public/events", json=payload).status_code == 202
    assert client.post("/api/public/events", json=payload).status_code == 202

    interaction = api_session.scalar(select(TrendInteraction))
    events = list(
        api_session.scalars(
            select(ProductEvent).where(
                ProductEvent.event_type == ProductEventType.TREND_IMPRESSION
            )
        )
    )
    assert interaction.impression_count == 1
    assert len(events) == 1


def test_client_cannot_spoof_outcome_events(client, api_session) -> None:
    seed_live_card(api_session)
    authenticate_with_interest(client)

    response = client.post(
        "/api/public/events", json={"eventType": "FEEDBACK_NEW_USEFUL"}
    )

    assert response.status_code == 422


def test_impression_requires_an_eligible_card(client, api_session) -> None:
    seed_live_card(api_session)
    authenticate_with_interest(client)

    response = client.post(
        "/api/public/events",
        json={"eventType": "TREND_IMPRESSION", "trendId": "unknown"},
    )

    assert response.status_code == 404


def test_internal_product_pages_are_available_under_protected_prefix(client) -> None:
    assert client.get("/internal/users").status_code == 200
    assert client.get("/internal/mvp-metrics").status_code == 200
    assert client.get("/internal/category-performance").status_code == 200
