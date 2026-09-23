from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.public_dependencies import SessionDependency, enforce_same_origin
from app.models.enums import BriefStatus
from app.models.tables import BriefItem, DailyBrief

router = APIRouter(
    prefix="/api/public",
    dependencies=[Depends(enforce_same_origin)],
    tags=["today"],
)
PUBLIC_STATUSES = (BriefStatus.PUBLISHED, BriefStatus.LOW_SIGNAL_DAY)


@router.get("/today")
def today(session: SessionDependency) -> dict:
    brief = session.scalar(
        select(DailyBrief)
        .where(DailyBrief.status.in_(PUBLIC_STATUSES))
        .order_by(DailyBrief.brief_date.desc(), DailyBrief.version.desc())
        .limit(1)
    )
    if brief is None:
        raise HTTPException(status_code=404, detail="published brief not found")
    return _serialize_brief(session, brief)


@router.get("/briefs/{brief_date}")
def dated_brief(brief_date: date, session: SessionDependency) -> dict:
    brief = session.scalar(
        select(DailyBrief)
        .where(
            DailyBrief.brief_date == brief_date,
            DailyBrief.status.in_(PUBLIC_STATUSES),
        )
        .order_by(DailyBrief.version.desc())
        .limit(1)
    )
    if brief is None:
        raise HTTPException(status_code=404, detail="published brief not found")
    return _serialize_brief(session, brief)


def _serialize_brief(session: Session, brief: DailyBrief) -> dict:
    items = list(
        session.scalars(
            select(BriefItem)
            .where(BriefItem.brief_id == brief.id)
            .order_by(BriefItem.position)
        )
    )
    empty_message = None
    if brief.status is BriefStatus.LOW_SIGNAL_DAY and not items:
        empty_message = "오늘은 기준을 충족한 중요한 변화가 없습니다."
    return {
        "briefDate": brief.brief_date.isoformat(),
        "status": brief.status.value,
        "todayInOneLine": brief.today_in_one_line,
        "readingTimeSeconds": brief.reading_time_seconds,
        "emptyStateMessage": empty_message,
        "statistics": {
            "rawItemCount": brief.raw_item_count,
            "eventClusterCount": brief.event_cluster_count,
            "candidateCount": brief.candidate_count,
            "selectedCount": brief.selected_count,
        },
        "items": [_serialize_item(item) for item in items],
    }


def _serialize_item(item: BriefItem) -> dict:
    return {
        "position": item.position,
        "headline": item.headline,
        "category": item.category,
        "whatHappened": item.what_happened,
        "whyItMatters": item.why_it_matters,
        "fact": item.fact_text.splitlines(),
        "interpretation": item.interpretation_text,
        "watch": item.watch_text,
        "sources": item.source_links,
        "importance": item.importance,
    }
