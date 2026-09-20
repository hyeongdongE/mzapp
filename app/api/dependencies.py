from __future__ import annotations

import hmac
from collections.abc import Iterator

from fastapi import Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.db import session_scope


def get_db() -> Iterator[Session]:
    with session_scope() as session:
        yield session


def dashboard_settings(request: Request) -> Settings:
    return request.app.state.settings


def require_dashboard_access(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    settings = dashboard_settings(request)
    if settings.dashboard_host in {"127.0.0.1", "localhost", "::1"}:
        return
    configured = settings.dashboard_api_key
    if configured is None or x_api_key is None:
        raise HTTPException(status_code=401, detail="dashboard API key required")
    if not hmac.compare_digest(x_api_key, configured.get_secret_value()):
        raise HTTPException(status_code=401, detail="invalid dashboard API key")
