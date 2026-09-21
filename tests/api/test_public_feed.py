import pytest

from app.models.enums import Category, CategoryAvailability, ReviewStatus, RunKind, RunStatus
from app.models.tables import CategorySetting
from tests.api.public_fixtures import authenticate_with_interest, seed_live_card


def test_feed_returns_only_fully_eligible_live_cards_without_internal_score(
    client, api_session
) -> None:
    visible = seed_live_card(api_session)
    authenticate_with_interest(client)

    response = client.get("/api/public/feed")

    assert response.status_code == 200
    assert [item["trendId"] for item in response.json()["items"]] == [visible.public_id]
    assert "trendScore" not in response.text
    assert response.json()["dataMode"] == "LIVE"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"review_status": ReviewStatus.PENDING},
        {"category_status": CategoryAvailability.DISABLED},
        {"run_kind": RunKind.REPLAY},
        {"run_status": RunStatus.FAILED},
        {"publishable": False},
        {"suppressed": True},
    ],
)
def test_feed_hides_card_when_any_publication_gate_fails(client, api_session, kwargs) -> None:
    category_status = kwargs.pop("category_status", None)
    seed_live_card(api_session, **kwargs)
    authenticate_with_interest(client)
    if category_status is not None:
        api_session.get(CategorySetting, Category.AI_TECH).status = category_status
        api_session.commit()

    assert client.get("/api/public/feed").json()["items"] == []


def test_feed_returns_intentional_empty_state_for_unselected_category(client, api_session) -> None:
    seed_live_card(api_session)
    assert client.post("/api/public/session").status_code == 201

    response = client.get("/api/public/feed")

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_feed_ranking_penalizes_already_known_card(client, api_session) -> None:
    first = seed_live_card(api_session, title="먼저 뜰 카드", score=80)
    second = seed_live_card(api_session, title="다음 카드", score=70)
    authenticate_with_interest(client)
    client.put(
        f"/api/public/trends/{first.public_id}/feedback",
        json={"feedbackType": "ALREADY_KNEW"},
    )

    items = client.get("/api/public/feed").json()["items"]

    assert [item["trendId"] for item in items] == [second.public_id, first.public_id]


def test_detail_uses_supported_unknown_cause_copy_and_safe_sources(client, api_session) -> None:
    card = seed_live_card(api_session)
    authenticate_with_interest(client)

    response = client.get(f"/api/public/trends/{card.public_id}")

    assert response.status_code == 200
    assert response.json()["why"] == "관심 증가는 확인되었지만 증가 원인은 확인되지 않았습니다."
    assert response.json()["sources"][0]["source"] == "WIKIMEDIA"
    assert "raw" not in response.text.lower()


def test_ineligible_detail_is_not_disclosed(client, api_session) -> None:
    card = seed_live_card(api_session, review_status=ReviewStatus.PENDING)
    authenticate_with_interest(client)

    assert client.get(f"/api/public/trends/{card.public_id}").status_code == 404
