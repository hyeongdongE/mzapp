from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config.settings import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_settings_reject_non_https_external_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_TRENDS_RSS_URL", "http://example.test/feed")

    with pytest.raises(ValidationError):
        get_settings()


def test_settings_reject_unapproved_external_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WIKIMEDIA_API_URL", "https://example.test/api")

    with pytest.raises(ValidationError):
        get_settings()


def test_settings_use_official_endpoints_by_default() -> None:
    settings = get_settings()

    assert settings.google_trends_rss_url.host == "trends.google.com"
    assert settings.wikimedia_api_url.host == "wikimedia.org"
    assert settings.wikidata_api_url.host == "www.wikidata.org"
    assert settings.dashboard_host == "127.0.0.1"
