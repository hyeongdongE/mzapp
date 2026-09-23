from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_dashboard_access
from app.models.enums import (
    BriefItemUsefulness,
    DuplicateEscapeVerdict,
    EventSelectionVerdict,
    EvidenceSetUsefulness,
    FactCorrectness,
    IncorrectMergeVerdict,
    InterpretationQuality,
    MissingEventDiscoverySource,
    VerbosityVerdict,
    WatchUsefulness,
)
from app.models.tables import (
    BriefItem,
    BriefReviewReopen,
    BriefReviewSession,
    DailyBrief,
)
from app.services.brief_quality_review import (
    BriefQualityReviewService,
    ItemReviewInput,
    MissingEventInput,
    ReviewConflict,
)

templates = Jinja2Templates(directory="dashboard/templates")
router = APIRouter(prefix="/internal", dependencies=[Depends(require_dashboard_access)])
SessionDependency = Annotated[Session, Depends(get_db)]


@router.get("/brief-quality", response_class=HTMLResponse)
def brief_quality_list(request: Request, session: SessionDependency) -> HTMLResponse:
    briefs = list(
        session.scalars(
            select(DailyBrief).order_by(DailyBrief.brief_date.desc(), DailyBrief.version.desc())
        )
    )
    rows = []
    for brief in briefs:
        review = session.scalar(
            select(BriefReviewSession).where(BriefReviewSession.brief_id == brief.id)
        )
        item_count = int(
            session.scalar(
                select(func.count()).select_from(BriefItem).where(BriefItem.brief_id == brief.id)
            )
            or 0
        )
        rows.append({"brief": brief, "review": review, "item_count": item_count})
    return templates.TemplateResponse(request, "brief_quality.html", {"rows": rows})


@router.get("/briefs/{brief_id}/quality-review", response_class=HTMLResponse)
def review_page(brief_id: int, request: Request, session: SessionDependency) -> HTMLResponse:
    brief = session.get(DailyBrief, brief_id)
    if brief is None:
        raise HTTPException(404, "brief not found")
    items = list(
        session.scalars(
            select(BriefItem).where(BriefItem.brief_id == brief_id).order_by(BriefItem.position)
        )
    )
    review = session.scalar(
        select(BriefReviewSession).where(BriefReviewSession.brief_id == brief_id)
    )
    service = BriefQualityReviewService(session)
    reopens = (
        []
        if review is None
        else list(
            session.scalars(
                select(BriefReviewReopen).where(BriefReviewReopen.session_id == review.id)
            )
        )
    )
    return templates.TemplateResponse(
        request,
        "brief_quality_review.html",
        {
            "brief": brief,
            "items": items,
            "review": review,
            "reopens": reopens,
            "active_review_seconds": (
                0 if review is None else service.active_review_seconds(review.id)
            ),
        },
    )


@router.post("/briefs/{brief_id}/quality-review/start")
def start_review(
    brief_id: int,
    session: SessionDependency,
    reviewer: Annotated[str, Form()],
) -> RedirectResponse:
    _call(
        lambda: BriefQualityReviewService(session).start_session(
            brief_id, reviewer, now=datetime.now(UTC)
        )
    )
    return _redirect(brief_id)


@router.post("/brief-review-sessions/{review_id}/activity-pulses")
def activity_pulse(
    review_id: int,
    session: SessionDependency,
    client_event_id: Annotated[str, Form()],
    active_seconds: Annotated[int, Form()],
) -> JSONResponse:
    created = _call(
        lambda: BriefQualityReviewService(session).record_activity_pulse(
            review_id, client_event_id, active_seconds, now=datetime.now(UTC)
        )
    )
    return JSONResponse({"recorded": created})


@router.post("/brief-review-sessions/{review_id}/complete")
def complete(review_id: int, session: SessionDependency) -> RedirectResponse:
    review = _call(
        lambda: BriefQualityReviewService(session).complete_session(
            review_id, now=datetime.now(UTC)
        )
    )
    return _redirect(review.brief_id)


@router.post("/brief-review-sessions/{review_id}/items/{brief_item_id}")
def review_item(
    review_id: int,
    brief_item_id: int,
    session: SessionDependency,
    usefulness: Annotated[BriefItemUsefulness, Form()],
    event_selection: Annotated[EventSelectionVerdict, Form()],
    fact_correctness: Annotated[FactCorrectness, Form()],
    interpretation_quality: Annotated[InterpretationQuality, Form()],
    watch_usefulness: Annotated[WatchUsefulness, Form()],
    verbosity: Annotated[VerbosityVerdict, Form()],
    evidence_set_usefulness: Annotated[EvidenceSetUsefulness, Form()],
    incorrect_merge_verdict: Annotated[IncorrectMergeVerdict, Form()],
    duplicate_escape_verdict: Annotated[DuplicateEscapeVerdict, Form()],
    duplicate_of_brief_item_id: Annotated[int | None, Form()] = None,
    duplicate_of_event_cluster_id: Annotated[int | None, Form()] = None,
    incorrect_merge_membership_ids: Annotated[list[int] | None, Form()] = None,
    notes: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    service = BriefQualityReviewService(session)
    _call(
        lambda: service.upsert_item_review(
            review_id,
            brief_item_id,
            ItemReviewInput(
                usefulness=usefulness,
                event_selection=event_selection,
                fact_correctness=fact_correctness,
                interpretation_quality=interpretation_quality,
                watch_usefulness=watch_usefulness,
                verbosity=verbosity,
                evidence_set_usefulness=evidence_set_usefulness,
                incorrect_merge_verdict=incorrect_merge_verdict,
                duplicate_escape_verdict=duplicate_escape_verdict,
                duplicate_of_brief_item_id=duplicate_of_brief_item_id,
                duplicate_of_event_cluster_id=duplicate_of_event_cluster_id,
                incorrect_merge_membership_ids=tuple(incorrect_merge_membership_ids or ()),
                notes=notes,
            ),
            now=datetime.now(UTC),
        )
    )
    review = session.get(BriefReviewSession, review_id)
    assert review is not None
    return _redirect(review.brief_id)


@router.post("/brief-review-sessions/{review_id}/missing-events")
def missing_event(
    review_id: int,
    session: SessionDependency,
    canonical_title: Annotated[str, Form()],
    canonical_url: Annotated[str, Form()],
    discovered_from: Annotated[MissingEventDiscoverySource, Form()],
    reason: Annotated[str, Form()],
) -> RedirectResponse:
    service = BriefQualityReviewService(session)
    _call(
        lambda: service.add_missing_event(
            review_id,
            MissingEventInput(canonical_title, canonical_url, discovered_from, reason),
            now=datetime.now(UTC),
        )
    )
    service.set_missing_events_confirmed(review_id, True)
    review = session.get(BriefReviewSession, review_id)
    assert review is not None
    return _redirect(review.brief_id)


@router.post("/brief-review-sessions/{review_id}/reopen")
def reopen(
    review_id: int,
    session: SessionDependency,
    actor: Annotated[str, Form()],
    reason: Annotated[str, Form()],
) -> RedirectResponse:
    review = _call(
        lambda: BriefQualityReviewService(session).reopen_session(
            review_id, actor=actor, reason=reason, now=datetime.now(UTC)
        )
    )
    return _redirect(review.brief_id)


def _call(operation):
    try:
        return operation()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ReviewConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _redirect(brief_id: int) -> RedirectResponse:
    return RedirectResponse(f"/internal/briefs/{brief_id}/quality-review", status_code=303)
