from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.config.settings import Settings
from app.main import create_app
from app.models.enums import DataMode
from app.models.tables import AnonymousUser, ProductTrendCard
from app.product.demo import DemoDataService


@contextmanager
def demo_client(api_session: Session) -> Iterator[TestClient]:
    app = create_app(Settings(demo_mode_enabled=True, secure_session_cookie=False))

    def override_db():
        yield api_session
        api_session.commit()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield client


def test_demo_mode_exposes_labelled_fixture_categories_and_feed(api_session) -> None:
    DemoDataService(api_session, enabled=True).seed()
    with demo_client(api_session) as client:
        categories = client.get("/api/public/categories").json()
        assert categories["dataMode"] == "DEMO"
        assert len(categories["items"]) == 4
        assert client.post("/api/public/session").status_code == 201
        assert client.put(
            "/api/public/me/interests", json={"categories": ["AI_TECH", "FOOD"]}
        ).status_code == 200
        feed = client.get("/api/public/feed").json()
        assert feed["dataMode"] == "DEMO"
        assert {item["category"] for item in feed["items"]} == {"AI_TECH", "FOOD"}


def test_test_mode_card_is_never_public_even_when_demo_is_enabled(api_session) -> None:
    DemoDataService(api_session, enabled=True).seed()
    card = api_session.query(ProductTrendCard).first()
    card.data_mode = DataMode.TEST
    card.fixture_key = "test-only"
    api_session.commit()
    with demo_client(api_session) as client:
        assert all(
            item["category"] != card.category.value
            for item in client.get("/api/public/categories").json()["items"]
        )


def test_live_cookie_is_not_reused_for_demo_session(client, api_session) -> None:
    live = client.post("/api/public/session").json()
    live_token = client.cookies.get("trend_radar_session")

    with demo_client(api_session) as demo:
        demo.cookies.set("trend_radar_session", live_token)
        created = demo.post("/api/public/session").json()

    assert created["isNew"] is True
    assert created["anonymousId"] != live["anonymousId"]
    assert {user.data_mode for user in api_session.scalars(select(AnonymousUser))} == {
        DataMode.LIVE,
        DataMode.DEMO,
    }
