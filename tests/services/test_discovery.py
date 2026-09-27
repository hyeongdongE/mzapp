from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select

from app.models.enums import Source
from app.models.tables import RawItem
from app.services.discovery import geeknews_discovery
from tests.intelligence.helpers import NOW, EvidenceSpec, seed_event


def _item(session, index: int, *, source: Source = Source.GEEKNEWS) -> RawItem:
    seed_event(
        session,
        [EvidenceSpec(source, f"Source headline {index}")],
        suffix=f"discovery-{index}",
    )
    item = session.scalar(
        select(RawItem).where(RawItem.external_id == f"discovery-{index}:1")
    )
    assert item is not None
    item.url = f"https://news.hada.io/topic?id={index}"
    item.published_at = NOW + timedelta(minutes=index)
    item.collected_at = NOW + timedelta(minutes=index)
    session.flush()
    return item


def test_discovery_is_bounded_source_metadata_not_verified_brief(db_session) -> None:
    for index in range(7):
        _item(db_session, index)
    _item(db_session, 10, source=Source.GITHUB_RELEASES)

    result = geeknews_discovery(
        db_session, day=date(2026, 9, 23), now=NOW + timedelta(hours=1)
    )

    assert result["status"] == "UNVERIFIED_DISCOVERY"
    assert len(result["items"]) == 5
    assert [item["title"] for item in result["items"]] == [
        f"Source headline {index}" for index in range(6, 1, -1)
    ]
    assert all(set(item) == {"title", "url", "publishedAt"} for item in result["items"])
    assert "fact" not in result


def test_discovery_rejects_untrusted_links_and_future_items(db_session) -> None:
    invalid = _item(db_session, 1)
    invalid.url = "https://news.hada.io.evil.example/topic?id=1"
    _item(db_session, 2)
    _item(db_session, 3)
    fallback = _item(db_session, 4)
    fallback.url = "https://news.hada.io/rss/news"
    fallback.published_at = NOW + timedelta(minutes=1)
    fallback.collected_at = NOW + timedelta(minutes=1)

    result = geeknews_discovery(
        db_session, day=date(2026, 9, 23), now=NOW + timedelta(minutes=2)
    )

    assert [item["title"] for item in result["items"]] == ["Source headline 2"]


def test_discovery_returns_empty_when_no_source_items(db_session) -> None:
    result = geeknews_discovery(db_session, day=date(2026, 9, 23), now=NOW)

    assert result == {"day": "2026-09-23", "status": "UNVERIFIED_DISCOVERY", "items": []}


def test_discovery_rejects_extra_query_parameters(db_session) -> None:
    item = _item(db_session, 1)
    item.url = "https://news.hada.io/topic?id=1&redirect=https://evil.example"

    result = geeknews_discovery(
        db_session, day=date(2026, 9, 23), now=NOW + timedelta(hours=1)
    )

    assert result["items"] == []
