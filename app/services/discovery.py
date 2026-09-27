from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence.sources import SOURCE_REGISTRY
from app.models.enums import Source
from app.models.tables import RawItem

SEOUL = ZoneInfo("Asia/Seoul")
DISCOVERY_LIMIT = 5


def geeknews_discovery(
    session: Session, *, day: date, now: datetime
) -> dict[str, object]:
    """Present source metadata, never promote community reports to verified facts."""
    policy = SOURCE_REGISTRY[Source.GEEKNEWS].policy
    if not (policy.public_title and policy.public_link and policy.public_attribution):
        return {"day": day.isoformat(), "status": "UNVERIFIED_DISCOVERY", "items": []}

    start = datetime.combine(day, time.min, tzinfo=SEOUL).astimezone(UTC)
    end = start + timedelta(days=1)
    rows = session.scalars(
        select(RawItem)
        .where(
            RawItem.source == Source.GEEKNEWS,
            RawItem.published_at >= start,
            RawItem.published_at < end,
            RawItem.published_at <= now,
            RawItem.collected_at <= now,
        )
        .order_by(RawItem.published_at.desc(), RawItem.id.desc())
        .limit(100)
    )
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if row.external_id in seen or not _official_geeknews_url(row.url):
            continue
        seen.add(row.external_id)
        items.append(
            {
                "title": row.title,
                "url": row.url,
                "publishedAt": _aware_utc(row.published_at).astimezone(SEOUL).isoformat(),
            }
        )
        if len(items) == DISCOVERY_LIMIT:
            break
    return {"day": day.isoformat(), "status": "UNVERIFIED_DISCOVERY", "items": items}


def _official_geeknews_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        query = parse_qs(parsed.query)
        topic_ids = query.get("id", [])
        return (
            parsed.scheme == "https"
            and parsed.hostname == "news.hada.io"
            and parsed.path == "/topic"
            and set(query) == {"id"}
            and len(topic_ids) == 1
            and topic_ids[0].isdigit()
            and not parsed.fragment
            and not (parsed.username or parsed.password or parsed.port)
        )
    except ValueError:
        return False


def _aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
