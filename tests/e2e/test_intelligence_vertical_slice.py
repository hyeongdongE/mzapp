from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from app.api.today import today
from app.collectors.geeknews import GeekNewsAtomCollector
from app.collectors.github_releases import GitHubReleasesCollector
from app.collectors.hacker_news import HackerNewsCollector
from app.collectors.http import SafeHttpClient
from app.collectors.official_feed import OfficialFeedCollector
from app.models.enums import BriefStatus, Source
from app.models.tables import (
    BriefItem,
    BriefItemFact,
    EventAssessment,
    EventCluster,
    EventEvidence,
    EventFact,
    RawFetch,
    RawItem,
    SourceHealth,
)
from app.services.intelligence_scheduler import IntelligencePipeline

FIXTURES = Path(__file__).parents[1] / "fixtures"
AS_OF = datetime(2026, 9, 23, 23, 0, tzinfo=UTC)


def recorded_http() -> SafeHttpClient:
    hn_items = {
        item["id"]: item
        for item in json.loads((FIXTURES / "hacker_news_items.json").read_text())
    }

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/topstories.json"):
            body = (FIXTURES / "hacker_news_topstories.json").read_bytes()
        elif "/item/" in url:
            item_id = int(request.url.path.split("/")[-1].removesuffix(".json"))
            body = json.dumps(hn_items[item_id]).encode()
        elif url == "https://news.hada.io/rss/news":
            body = (FIXTURES / "geeknews_atom.xml").read_bytes()
        elif "/repos/acme/agent-sdk/releases" in url:
            body = (FIXTURES / "github_releases.json").read_bytes()
        elif url == "https://blog.cloudflare.com/rss/":
            body = (FIXTURES / "cloudflare_feed.xml").read_bytes()
        elif url == "https://aws.amazon.com/blogs/aws/feed/":
            body = (FIXTURES / "aws_feed.xml").read_bytes()
        else:
            raise AssertionError(f"unexpected recorded request: {url}")
        return httpx.Response(200, content=body, request=request)

    return SafeHttpClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        allowed_hosts={
            "news.hada.io",
            "hacker-news.firebaseio.com",
            "api.github.com",
            "blog.cloudflare.com",
            "aws.amazon.com",
        },
        max_bytes=2_000_000,
        retries=0,
    )


@pytest.mark.asyncio
async def test_recorded_http_payloads_cross_the_complete_today_path(db_session) -> None:
    http = recorded_http()
    collectors = [
        GeekNewsAtomCollector(http, "https://news.hada.io/rss/news", now=lambda: AS_OF),
        HackerNewsCollector(http, max_items=2, now=lambda: AS_OF),
        GitHubReleasesCollector(
            http,
            repository="acme/agent-sdk",
            now=lambda: AS_OF,
        ),
        OfficialFeedCollector(
            Source.OFFICIAL_CLOUDFLARE,
            http,
            "https://blog.cloudflare.com/rss/",
            now=lambda: AS_OF,
        ),
        OfficialFeedCollector(
            Source.OFFICIAL_AWS,
            http,
            "https://aws.amazon.com/blogs/aws/feed/",
            now=lambda: AS_OF,
        ),
    ]
    pipeline = IntelligencePipeline(
        db_session,
        now=lambda: AS_OF,
        github_repositories=("acme/agent-sdk",),
    )

    collection = await pipeline.collect(collectors, as_of=AS_OF)
    processing = pipeline.process(
        AS_OF - timedelta(days=3),
        AS_OF + timedelta(hours=1),
        version="cluster-e2e-v1",
        assessment_version="assessment-e2e-v1",
    )
    generated = pipeline.generate(
        date(2026, 9, 24),
        now=datetime(2026, 9, 24, 0, 0, tzinfo=UTC),
        version="brief-e2e-v1",
    )
    assert generated.status is BriefStatus.DRAFT
    brief = pipeline.publish(
        date(2026, 9, 24),
        now=datetime(2026, 9, 24, 0, 30, tzinfo=UTC),
    )
    payload = today(db_session)

    assert all(result.succeeded for result in collection)
    assert {result.source for result in collection} == {
        Source.GEEKNEWS,
        Source.HACKER_NEWS,
        Source.GITHUB_RELEASES,
        Source.OFFICIAL_CLOUDFLARE,
        Source.OFFICIAL_AWS,
    }
    assert processing.assigned_items > 0
    assert db_session.scalar(select(func.count()).select_from(RawFetch)) == 5
    assert db_session.scalar(select(func.count()).select_from(RawItem)) >= 7
    assert db_session.scalar(select(func.count()).select_from(EventCluster)) > 0
    assert db_session.scalar(select(func.count()).select_from(EventEvidence)) > 0
    assert db_session.scalar(select(func.count()).select_from(EventFact)) > 0
    assert db_session.scalar(select(func.count()).select_from(EventAssessment)) > 0
    assert brief.status in {BriefStatus.PUBLISHED, BriefStatus.LOW_SIGNAL_DAY}
    assert brief.reading_time_seconds <= 300
    cards = db_session.scalars(select(BriefItem)).all()
    assert cards
    assert len({card.event_cluster_id for card in cards}) == len(cards)
    assert all(card.source_links for card in cards)
    assert db_session.scalar(select(func.count()).select_from(BriefItemFact)) > 0
    assert payload["statistics"]["selectedCount"] == len(cards)
    assert "factIds" not in payload["items"][0]
    assert all(
        health.freshness_state == "FRESH"
        for health in db_session.scalars(select(SourceHealth))
    )
