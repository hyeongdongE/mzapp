from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_dashboard_access
from app.models.enums import Category, ReviewAction, Source
from app.models.tables import (
    CandidateObservation,
    Claim,
    EntityAlias,
    EntityCandidate,
    Evidence,
    Review,
    SourceObservation,
    TrendCandidate,
    TrendEntity,
    TrendSnapshot,
)

SOURCE_NAMES = {
    Source.GOOGLE_TRENDS: "Google Trends",
    Source.WIKIMEDIA: "Wikimedia",
    Source.WIKIDATA: "Wikidata",
}
templates = Jinja2Templates(
    directory=Path(__file__).resolve().parents[2] / "dashboard" / "templates"
)
router = APIRouter(dependencies=[Depends(require_dashboard_access)])
SessionDependency = Annotated[Session, Depends(get_db)]


@router.get("/", response_class=HTMLResponse)
def today(
    request: Request,
    session: SessionDependency,
    day: Annotated[date | None, Query(alias="date")] = None,
) -> HTMLResponse:
    selected_day = day or datetime.now(UTC).date()
    day_start = datetime.combine(selected_day, datetime.min.time(), tzinfo=UTC)
    day_end = day_start + timedelta(days=1)
    counts = {
        "raw_candidates": session.scalar(
            select(func.count()).select_from(TrendCandidate).where(
                TrendCandidate.first_seen_at >= day_start,
                TrendCandidate.first_seen_at < day_end,
            )
        )
        or 0,
        "unique_entities": session.scalar(
            select(func.count()).select_from(TrendEntity).where(
                TrendEntity.created_at >= day_start,
                TrendEntity.created_at < day_end,
            )
        )
        or 0,
        "published": session.scalar(
            select(func.count(func.distinct(Review.entity_id))).where(
                Review.action == ReviewAction.APPROVE,
                Review.created_at >= day_start,
                Review.created_at < day_end,
            )
        )
        or 0,
        "rejected": session.scalar(
            select(func.count(func.distinct(Review.entity_id))).where(
                Review.action.in_([ReviewAction.REJECT, ReviewAction.MARK_NOISE]),
                Review.created_at >= day_start,
                Review.created_at < day_end,
            )
        )
        or 0,
    }
    return templates.TemplateResponse(
        request, "today.html", {"counts": counts, "selected_day": selected_day}
    )


@router.get("/candidates", response_class=HTMLResponse)
def candidates(request: Request, session: SessionDependency) -> HTMLResponse:
    entities = list(session.scalars(select(TrendEntity).order_by(TrendEntity.id)))
    snapshots = list(
        session.scalars(
            select(TrendSnapshot).order_by(
                TrendSnapshot.entity_id, TrendSnapshot.as_of.desc(), TrendSnapshot.id.desc()
            )
        )
    )
    latest = {}
    for snapshot in snapshots:
        latest.setdefault(snapshot.entity_id, snapshot)
    evidence_by_entity: dict[int, list[Evidence]] = defaultdict(list)
    for row in session.scalars(select(Evidence).order_by(Evidence.id)):
        evidence_by_entity[row.entity_id].append(row)
    sources_by_entity: dict[int, set[Source]] = defaultdict(set)
    source_rows = session.execute(
        select(EntityCandidate.entity_id, SourceObservation.source)
        .join(
            CandidateObservation,
            CandidateObservation.candidate_id == EntityCandidate.candidate_id,
        )
        .join(
            SourceObservation,
            SourceObservation.id == CandidateObservation.observation_id,
        )
        .distinct()
    )
    for entity_id, source in source_rows:
        sources_by_entity[entity_id].add(source)
    first_seen_by_entity = dict(
        session.execute(
            select(EntityCandidate.entity_id, func.min(TrendCandidate.first_seen_at))
            .join(TrendCandidate, TrendCandidate.id == EntityCandidate.candidate_id)
            .group_by(EntityCandidate.entity_id)
        ).all()
    )
    rows = [
        {
            "entity": entity,
            "snapshot": latest.get(entity.id),
            "sources": sorted(
                SOURCE_NAMES[source] for source in sources_by_entity[entity.id]
            ),
            "evidence_count": len(evidence_by_entity[entity.id]),
            "first_seen": first_seen_by_entity.get(entity.id),
        }
        for entity in entities
    ]
    return templates.TemplateResponse(request, "candidates.html", {"rows": rows})


@router.get("/entities/{entity_id}", response_class=HTMLResponse)
def detail(
    entity_id: int, request: Request, session: SessionDependency
) -> HTMLResponse:
    entity = session.get(TrendEntity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="entity not found")
    snapshots = list(
        session.scalars(
            select(TrendSnapshot)
            .where(TrendSnapshot.entity_id == entity_id)
            .order_by(TrendSnapshot.as_of.desc())
        )
    )
    evidence = list(
        session.scalars(
            select(Evidence)
            .where(Evidence.entity_id == entity_id)
            .order_by(Evidence.observed_at.desc())
        )
    )
    claims = list(
        session.scalars(
            select(Claim).where(Claim.entity_id == entity_id).order_by(Claim.id)
        )
    )
    aliases = list(
        session.scalars(
            select(EntityAlias).where(EntityAlias.entity_id == entity_id).order_by(EntityAlias.id)
        )
    )
    candidate_ids = select(EntityCandidate.candidate_id).where(
        EntityCandidate.entity_id == entity_id
    )
    linked_candidates = list(
        session.scalars(
            select(TrendCandidate)
            .where(TrendCandidate.id.in_(candidate_ids))
            .order_by(TrendCandidate.first_seen_at, TrendCandidate.id)
        )
    )
    observations = list(
        session.scalars(
            select(SourceObservation)
            .join(
                CandidateObservation,
                CandidateObservation.observation_id == SourceObservation.id,
            )
            .where(CandidateObservation.candidate_id.in_(candidate_ids))
            .order_by(SourceObservation.source_timestamp.desc())
        ).unique()
    )
    return templates.TemplateResponse(
        request,
        "detail.html",
        {
            "entity": entity,
            "snapshots": snapshots,
            "evidence": evidence,
            "claims": claims,
            "aliases": aliases,
            "observations": observations,
            "source_names": SOURCE_NAMES,
            "linked_candidates": linked_candidates,
            "categories": list(Category),
            "merge_targets": list(
                session.scalars(
                    select(TrendEntity)
                    .where(TrendEntity.id != entity_id)
                    .order_by(TrendEntity.canonical_name, TrendEntity.id)
                )
            ),
        },
    )
