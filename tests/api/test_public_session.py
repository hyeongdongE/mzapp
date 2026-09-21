from sqlalchemy import select

from app.models.tables import AnonymousUser


def test_anonymous_session_sets_opaque_http_only_cookie_and_stores_only_hash(
    client, api_session
) -> None:
    response = client.post("/api/public/session")

    assert response.status_code == 201
    cookie = response.headers["set-cookie"]
    assert "trend_radar_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    token = client.cookies.get("trend_radar_session")
    user = api_session.scalar(select(AnonymousUser))
    assert token is not None and len(token) >= 40
    assert user is not None
    assert user.credential_hash != token
    assert len(user.credential_hash) == 64
    assert response.json() == {"isNew": True}


def test_existing_session_is_reused(client, api_session) -> None:
    first = client.post("/api/public/session")
    second = client.post("/api/public/session")

    assert first.json()["isNew"] is True
    assert second.json()["isNew"] is False


def test_mutation_rejects_cross_origin_browser_request(client) -> None:
    response = client.post(
        "/api/public/session", headers={"Origin": "https://attacker.example"}
    )

    assert response.status_code == 403


def test_missing_or_forged_session_cannot_read_user_state(client) -> None:
    assert client.get("/api/public/me/interests").status_code == 401
    client.cookies.set("trend_radar_session", "forged-token")
    assert client.get("/api/public/me/interests").status_code == 401
