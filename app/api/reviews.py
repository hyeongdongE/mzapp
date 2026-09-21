from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_dashboard_access
from app.models.enums import Category, HumanEvaluationLabel, ReviewAction
from app.services.evaluations import EvaluationService
from app.services.reviews import (
    EntityNotFound,
    ReviewCommand,
    ReviewError,
    ReviewService,
    StaleReview,
)

router = APIRouter(prefix="/internal", dependencies=[Depends(require_dashboard_access)])
SessionDependency = Annotated[Session, Depends(get_db)]


@router.post("/reviews")
def create_review(
    session: SessionDependency,
    entity_id: Annotated[int, Form()],
    action: Annotated[str, Form()],
    version: Annotated[int, Form()],
    actor: Annotated[str, Form(min_length=1)],
    reason: Annotated[str | None, Form()] = None,
    category: Annotated[str | None, Form()] = None,
    target_entity_id: Annotated[int | None, Form()] = None,
    candidate_ids: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    try:
        parsed_action = ReviewAction(action)
        parsed_category = Category(category) if category else None
        parsed_candidate_ids = tuple(
            int(value.strip())
            for value in (candidate_ids or "").split(",")
            if value.strip()
        )
        ReviewService(session).apply(
            ReviewCommand(
                entity_id=entity_id,
                action=parsed_action,
                expected_version=version,
                actor=actor,
                reason=reason,
                category=parsed_category,
                target_entity_id=target_entity_id,
                candidate_ids=parsed_candidate_ids,
            ),
            datetime.now(UTC),
        )
    except StaleReview as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EntityNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ReviewError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RedirectResponse(f"/internal/entities/{entity_id}", status_code=303)


@router.post("/evaluations")
def create_evaluation(
    session: SessionDependency,
    entity_id: Annotated[int, Form()],
    label: Annotated[str, Form()],
    actor: Annotated[str, Form(min_length=1)],
) -> RedirectResponse:
    try:
        EvaluationService(session).record(
            entity_id,
            HumanEvaluationLabel(label),
            actor,
            datetime.now(UTC),
        )
    except EntityNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RedirectResponse(f"/internal/entities/{entity_id}", status_code=303)
