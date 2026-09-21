from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.models.enums import DataMode
from app.models.tables import AnonymousUser
from app.product.users import UserService

SESSION_COOKIE = "trend_radar_session"
SessionDependency = Annotated[Session, Depends(get_db)]


def enforce_same_origin(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    origin = request.headers.get("origin")
    if origin is None:
        return
    expected = str(request.base_url).rstrip("/")
    if origin.rstrip("/") != expected:
        raise HTTPException(status_code=403, detail="cross-origin mutation denied")


def current_user(
    request: Request,
    session: SessionDependency,
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> AnonymousUser:
    if not token:
        raise HTTPException(status_code=401, detail="anonymous session required")
    user = UserService(session).find(token)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid anonymous session")
    expected_mode = (
        DataMode.DEMO if request.app.state.settings.demo_mode_enabled else DataMode.LIVE
    )
    if user.data_mode is not expected_mode:
        raise HTTPException(status_code=401, detail="session data mode mismatch")
    return user


CurrentUser = Annotated[AnonymousUser, Depends(current_user)]
