import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app


def test_public_dashboard_requires_explicit_allow_and_api_key() -> None:
    with pytest.raises(ValueError, match="public dashboard"):
        create_app(Settings(dashboard_host="0.0.0.0"))
    with pytest.raises(ValueError, match="API key"):
        create_app(Settings(dashboard_host="0.0.0.0", dashboard_allow_public=True))
    with pytest.raises(ValueError, match="API key"):
        create_app(
            Settings(
                dashboard_host="0.0.0.0",
                dashboard_allow_public=True,
                dashboard_api_key="   ",
            )
        )


def test_dashboard_api_key_is_redacted_from_settings_repr() -> None:
    settings = Settings(
        dashboard_host="0.0.0.0",
        dashboard_allow_public=True,
        dashboard_api_key="secret-dashboard-key",
    )

    assert "secret-dashboard-key" not in repr(settings)


def test_public_dashboard_rejects_missing_or_wrong_api_key() -> None:
    public_app = create_app(
        Settings(
            dashboard_host="0.0.0.0",
            dashboard_allow_public=True,
            dashboard_api_key="secret-dashboard-key",
        )
    )

    with TestClient(public_app) as client:
        assert client.get("/internal").status_code == 401
        assert client.get(
            "/internal", headers={"X-API-Key": "wrong"}
        ).status_code == 401
