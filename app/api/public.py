from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.public_dependencies import (
    SESSION_COOKIE,
    CurrentUser,
    SessionDependency,
    enforce_same_origin,
)
from app.models.enums import Category, NotificationMode
from app.product.schemas import InterestsInput, SettingsInput
from app.product.users import UserService

router = APIRouter(
    prefix="/api/public", dependencies=[Depends(enforce_same_origin)], tags=["public"]
)

CATEGORY_LABELS = {
    Category.SPORTS: "스포츠",
    Category.ENTERTAINMENT: "엔터",
    Category.FOOD: "음식",
    Category.GAME: "게임",
    Category.AI_TECH: "AI / IT",
    Category.MEME_INTERNET: "인터넷 문화",
    Category.FASHION_BEAUTY: "패션 / 뷰티",
    Category.SHOPPING_PRODUCT: "쇼핑 / 제품",
}


@router.post("/session", status_code=status.HTTP_201_CREATED)
def create_session(request: Request, response: Response, session: SessionDependency) -> dict:
    service = UserService(session)
    existing_token = request.cookies.get(SESSION_COOKIE)
    user = service.find(existing_token) if existing_token else None
    is_new = user is None
    token = existing_token
    if user is None:
        user, token = service.create()
    assert token is not None
    settings = request.app.state.settings
    secure = settings.secure_session_cookie
    if secure is None:
        secure = settings.dashboard_host not in {"127.0.0.1", "localhost", "::1"}
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=60 * 60 * 24 * 180,
        path="/",
    )
    return {"anonymousId": user.id, "isNew": is_new}


@router.get("/categories")
def categories(session: SessionDependency) -> dict:
    rows = UserService(session).selectable_categories()
    return {
        "dataMode": "LIVE",
        "items": [
            {
                "category": row.category.value,
                "label": CATEGORY_LABELS[row.category],
                "status": row.status.value,
            }
            for row in rows
        ],
    }


@router.get("/me/interests")
def get_interests(user: CurrentUser, session: SessionDependency) -> dict:
    return {
        "categories": [category.value for category in UserService(session).interests(user.id)]
    }


@router.put("/me/interests")
def put_interests(
    payload: InterestsInput, user: CurrentUser, session: SessionDependency
) -> dict:
    try:
        selected = UserService(session).replace_interests(user.id, payload.categories)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"categories": [category.value for category in selected]}


@router.get("/settings")
def get_user_settings(user: CurrentUser, session: SessionDependency) -> dict:
    service = UserService(session)
    return {
        "categories": [category.value for category in service.interests(user.id)],
        "notificationMode": service.notification_mode(user.id).value,
        "pushDeliveryEnabled": False,
    }


@router.put("/settings")
def put_user_settings(
    payload: SettingsInput, user: CurrentUser, session: SessionDependency
) -> dict:
    service = UserService(session)
    try:
        selected = service.replace_interests(user.id, payload.categories)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    mode: NotificationMode = service.set_notification_mode(
        user.id, payload.notification_mode
    )
    return {
        "categories": [category.value for category in selected],
        "notificationMode": mode.value,
        "pushDeliveryEnabled": False,
    }
