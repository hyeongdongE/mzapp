from datetime import UTC, datetime

from app.models.enums import Category, CategoryAvailability
from app.models.tables import CategorySetting

NOW = datetime(2026, 9, 21, 4, tzinfo=UTC)


def seed_categories(api_session) -> None:
    api_session.add_all(
        [
            CategorySetting(
                category=Category.AI_TECH,
                status=CategoryAvailability.EXPERIMENTAL,
                rationale="evaluation",
                updated_by="operator",
                updated_at=NOW,
            ),
            CategorySetting(
                category=Category.FOOD,
                status=CategoryAvailability.DISABLED,
                rationale="insufficient evidence",
                updated_by="operator",
                updated_at=NOW,
            ),
        ]
    )
    api_session.commit()


def authenticate(client) -> None:
    assert client.post("/api/public/session").status_code == 201


def test_categories_only_return_user_selectable_live_categories(client, api_session) -> None:
    seed_categories(api_session)

    response = client.get("/api/public/categories")

    assert response.status_code == 200
    assert response.json() == {
        "dataMode": "LIVE",
        "items": [
            {
                "category": "AI_TECH",
                "label": "AI / IT",
                "status": "EXPERIMENTAL",
            }
        ],
    }


def test_interests_require_one_selectable_category_and_reject_other(
    client, api_session
) -> None:
    seed_categories(api_session)
    authenticate(client)

    assert client.put("/api/public/me/interests", json={"categories": []}).status_code == 422
    assert client.put(
        "/api/public/me/interests", json={"categories": ["OTHER"]}
    ).status_code == 422
    assert client.put(
        "/api/public/me/interests", json={"categories": ["FOOD"]}
    ).status_code == 422

    response = client.put(
        "/api/public/me/interests", json={"categories": ["AI_TECH"]}
    )
    assert response.status_code == 200
    assert client.get("/api/public/me/interests").json() == {
        "categories": ["AI_TECH"]
    }


def test_notification_preference_round_trip(client, api_session) -> None:
    seed_categories(api_session)
    authenticate(client)
    client.put("/api/public/me/interests", json={"categories": ["AI_TECH"]})

    response = client.put(
        "/api/public/settings",
        json={"categories": ["AI_TECH"], "notificationMode": "DAILY_DIGEST"},
    )

    assert response.status_code == 200
    assert client.get("/api/public/settings").json() == {
        "categories": ["AI_TECH"],
        "notificationMode": "DAILY_DIGEST",
        "pushDeliveryEnabled": False,
    }


def test_user_state_isolated_by_cookie(client, api_session) -> None:
    seed_categories(api_session)
    authenticate(client)
    client.put("/api/public/me/interests", json={"categories": ["AI_TECH"]})
    first_cookie = client.cookies.get("trend_radar_session")
    client.cookies.clear()
    authenticate(client)

    assert client.get("/api/public/me/interests").json() == {"categories": []}
    client.cookies.set("trend_radar_session", first_cookie)
    assert client.get("/api/public/me/interests").json() == {
        "categories": ["AI_TECH"]
    }
