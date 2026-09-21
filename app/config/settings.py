from __future__ import annotations

from functools import lru_cache

from pydantic import HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.models.enums import PublicationPolicyMode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://trend_radar:trend_radar@localhost:5432/trend_radar"
    google_trends_rss_url: HttpUrl = HttpUrl("https://trends.google.com/trending/rss?geo=KR")
    wikimedia_api_url: HttpUrl = HttpUrl("https://wikimedia.org/api/rest_v1")
    wikidata_api_url: HttpUrl = HttpUrl("https://www.wikidata.org/w/api.php")
    http_timeout_seconds: float = 10.0
    http_max_bytes: int = 2_000_000
    http_retries: int = 3
    user_agent: str = "TrendRadarPoC/0.1 (local-development; set-contact@example.com)"
    dashboard_host: str = "127.0.0.1"
    dashboard_allow_public: bool = False
    dashboard_api_key: SecretStr | None = None
    meta_provider_enabled: bool = False
    llm_provider_enabled: bool = False
    publication_policy_mode: PublicationPolicyMode = (
        PublicationPolicyMode.MANUAL_APPROVAL_REQUIRED
    )
    demo_mode_enabled: bool = False
    secure_session_cookie: bool = True

    @field_validator("dashboard_api_key", mode="before")
    @classmethod
    def empty_dashboard_api_key_is_disabled(cls, value: object) -> object | None:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("google_trends_rss_url")
    @classmethod
    def validate_google_endpoint(cls, value: HttpUrl) -> HttpUrl:
        return cls._validate_official_https(value, {"trends.google.com"})

    @field_validator("wikimedia_api_url")
    @classmethod
    def validate_wikimedia_endpoint(cls, value: HttpUrl) -> HttpUrl:
        return cls._validate_official_https(value, {"wikimedia.org"})

    @field_validator("wikidata_api_url")
    @classmethod
    def validate_wikidata_endpoint(cls, value: HttpUrl) -> HttpUrl:
        return cls._validate_official_https(value, {"www.wikidata.org", "wikidata.org"})

    @staticmethod
    def _validate_official_https(value: HttpUrl, allowed_hosts: set[str]) -> HttpUrl:
        if value.scheme != "https" or value.host not in allowed_hosts:
            allowed = ", ".join(sorted(allowed_hosts))
            raise ValueError(f"endpoint must use HTTPS on an approved host: {allowed}")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
