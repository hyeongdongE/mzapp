from fastapi.testclient import TestClient

from app.api.dependencies import get_db
from app.config.settings import Settings
from app.main import create_app


def built_client(tmp_path, api_session):
    (tmp_path / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    app = create_app(Settings(secure_session_cookie=False), spa_path=tmp_path)

    def override_db():
        yield api_session

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def test_built_spa_serves_root_and_history_routes(tmp_path, api_session) -> None:
    with built_client(tmp_path, api_session) as client:
        root = client.get("/")
        deep_link = client.get("/feed")

    assert root.status_code == 200
    assert deep_link.status_code == 200
    assert '<div id="root"></div>' in root.text
    assert '<div id="root"></div>' in deep_link.text


def test_spa_fallback_does_not_intercept_backend_routes(tmp_path, api_session) -> None:
    with built_client(tmp_path, api_session) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/api/public/categories").headers["content-type"].startswith(
            "application/json"
        )
        assert "Today" in client.get("/internal").text


def test_missing_frontend_build_returns_actionable_service_unavailable(tmp_path) -> None:
    app = create_app(Settings(secure_session_cookie=False), spa_path=tmp_path)

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 503
    assert response.json()["detail"] == "frontend build is unavailable; run npm run build"
