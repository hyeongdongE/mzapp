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
    assert settings.geeknews_rss_url.host == "news.hada.io"
    assert settings.hacker_news_api_url.host == "hacker-news.firebaseio.com"
    assert settings.github_api_url.host == "api.github.com"
    assert settings.cloudflare_rss_url.host == "blog.cloudflare.com"
    assert settings.aws_rss_url.host == "aws.amazon.com"
    assert settings.github_release_repositories
    assert settings.dashboard_host == "127.0.0.1"


def test_settings_reject_unapproved_geeknews_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEEKNEWS_RSS_URL", "https://example.test/rss")

    with pytest.raises(ValidationError):
        get_settings()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("HACKER_NEWS_API_URL", "https://example.test/v0"),
        ("GITHUB_API_URL", "https://example.test"),
        ("CLOUDFLARE_RSS_URL", "https://example.test/rss"),
        ("AWS_RSS_URL", "https://example.test/rss"),
    ],
)
def test_settings_reject_unapproved_intelligence_hosts(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError):
        get_settings()
