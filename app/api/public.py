from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.public_dependencies import (
    SESSION_COOKIE,
    CurrentUser,
    SessionDependency,
    enforce_same_origin,
)
from app.models.enums import Category, DataMode, NotificationMode, ProductEventType
from app.product.analytics import ProductAnalytics
from app.product.feed import FeedService
from app.product.schemas import EventInput, FeedbackInput, InterestsInput, SettingsInput
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
        user, token = service.create(
            data_mode=(
                DataMode.DEMO
                if request.app.state.settings.demo_mode_enabled
                else DataMode.LIVE
            )
        )
    else:
        ProductAnalytics(session).record(user, ProductEventType.RETURN_VISIT)
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
    analytics = ProductAnalytics(session)
    for category in selected:
        analytics.record(user, ProductEventType.INTEREST_SELECTED, category=category)
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


def _feed_service(request: Request, session: SessionDependency) -> FeedService:
    return FeedService(session, request.app.state.settings.publication_policy_mode)


@router.get("/feed")
def feed(request: Request, user: CurrentUser, session: SessionDependency) -> dict:
    ProductAnalytics(session).record(user, ProductEventType.FEED_VIEWED)
    return {
        "dataMode": "LIVE",
        "items": _feed_service(request, session).ranked_items(user.id),
    }


@router.get("/trends/{public_id}")
def trend_detail(
    public_id: str, request: Request, user: CurrentUser, session: SessionDependency
) -> dict:
    service = _feed_service(request, session)
    card = service.get_eligible(user.id, public_id)
    if card is None:
        raise HTTPException(status_code=404, detail="trend not found")
    service.record_open(user.id, card.id)
    ProductAnalytics(session).record(user, ProductEventType.TREND_OPENED, card=card)
    return service.detail(user.id, card)


@router.put("/trends/{public_id}/feedback")
def put_feedback(
    public_id: str,
    payload: FeedbackInput,
    request: Request,
    user: CurrentUser,
    session: SessionDependency,
) -> dict:
    service = _feed_service(request, session)
    card = service.get_eligible(user.id, public_id)
    if card is None:
        raise HTTPException(status_code=404, detail="trend not found")
    feedback = service.feedback(user.id, card.id, payload.feedback_type)
    event_type = {
        "NEW_AND_USEFUL": ProductEventType.FEEDBACK_NEW_USEFUL,
        "ALREADY_KNEW": ProductEventType.FEEDBACK_ALREADY_KNEW,
        "NOT_INTERESTED": ProductEventType.FEEDBACK_NOT_INTERESTED,
        "INCORRECT": ProductEventType.FEEDBACK_INCORRECT,
    }[feedback.feedback_type.value]
    ProductAnalytics(session).record(user, event_type, card=card)
    return {"feedback": feedback.feedback_type.value}


@router.put("/trends/{public_id}/save")
def save_trend(
    public_id: str, request: Request, user: CurrentUser, session: SessionDependency
) -> dict:
    service = _feed_service(request, session)
    card = service.get_eligible(user.id, public_id)
    if card is None:
        raise HTTPException(status_code=404, detail="trend not found")
    service.save(user.id, card.id)
    ProductAnalytics(session).record(user, ProductEventType.TREND_SAVED, card=card)
    return {"saved": True}


@router.delete("/trends/{public_id}/save", status_code=status.HTTP_204_NO_CONTENT)
def unsave_trend(
    public_id: str, request: Request, user: CurrentUser, session: SessionDependency
) -> Response:
    service = _feed_service(request, session)
    card = service.get_eligible(user.id, public_id)
    if card is None:
        raise HTTPException(status_code=404, detail="trend not found")
    service.unsave(user.id, card.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/saved")
def saved(request: Request, user: CurrentUser, session: SessionDependency) -> dict:
    return {"dataMode": "LIVE", "items": _feed_service(request, session).saved_items(user.id)}


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
def create_event(
    payload: EventInput,
    request: Request,
    user: CurrentUser,
    session: SessionDependency,
) -> dict:
    analytics = ProductAnalytics(session)
    if payload.event_type is ProductEventType.ONBOARDING_STARTED:
        analytics.record(user, payload.event_type)
        return {"accepted": True}
    if payload.event_type is ProductEventType.TREND_IMPRESSION:
        if not payload.trend_id:
            raise HTTPException(status_code=422, detail="trendId is required")
        service = _feed_service(request, session)
        card = service.get_eligible(user.id, payload.trend_id)
        if card is None:
            raise HTTPException(status_code=404, detail="trend not found")
        analytics.impression(user, card)
        return {"accepted": True}
    raise HTTPException(status_code=422, detail="event is recorded by the server")
