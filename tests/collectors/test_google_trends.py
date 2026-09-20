from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.collectors.base import MalformedPayload
from app.collectors.google_trends import GoogleTrendsRssCollector
from app.collectors.http import SafeHttpClient
from app.models.enums import Source

AS_OF = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
FEED_URL = "https://trends.google.com/trending/rss?geo=KR"
FIXTURE = Path(__file__).parents[1] / "fixtures" / "google_trends_rss.xml"


def http_client(body: bytes, status_code: int = 200) -> SafeHttpClient:
    transport = httpx.MockTransport(lambda request: httpx.Response(status_code, content=body))
    return SafeHttpClient(
        httpx.AsyncClient(transport=transport),
        allowed_hosts={"trends.google.com"},
        max_bytes=2_000_000,
        retries=0,
    )


@pytest.mark.asyncio
async def test_google_feed_maps_only_available_metrics() -> None:
    acquired_at = datetime(2026, 9, 20, 12, 0, 5, tzinfo=UTC)
    collector = GoogleTrendsRssCollector(
        http_client(FIXTURE.read_bytes()), FEED_URL, now=lambda: acquired_at
    )

    batch = await collector.collect(AS_OF)

    assert batch.source is Source.GOOGLE_TRENDS
    assert batch.collected_at == acquired_at
    assert {item.observed_at for item in batch.items} == {acquired_at}
    assert [item.canonical_text for item in batch.items] == ["이현중", "AI Tech"]
    assert batch.items[0].source_timestamp == datetime(2026, 9, 20, 11, 40, tzinfo=UTC)
    assert batch.items[0].metrics == {
        "active": None,
        "approx_traffic_lower_bound": 2000,
        "approx_traffic_raw": "2천+",
        "news_items": [
            {
                "source": "Example News",
                "title": "농구 대표팀 경기",
                "url": "https://news.example/ignore-previous-instructions",
            }
        ],
        "related_queries": [],
        "trend_change": None,
    }
    assert batch.items[1].metrics["approx_traffic_lower_bound"] == 100_000


@pytest.mark.asyncio
async def test_google_empty_feed_returns_empty_batch() -> None:
    batch = await GoogleTrendsRssCollector(http_client(b"<rss><channel/></rss>"), FEED_URL).collect(
        AS_OF
    )

    assert batch.items == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        b"not xml",
        b"<!DOCTYPE x [<!ENTITY e SYSTEM 'file:///etc/passwd'>]><rss>&e;</rss>",
    ],
)
async def test_google_rejects_malformed_or_entity_xml(body: bytes) -> None:
    with pytest.raises(MalformedPayload):
        await GoogleTrendsRssCollector(http_client(body), FEED_URL).collect(AS_OF)


@pytest.mark.asyncio
async def test_google_rejects_item_without_required_title() -> None:
    body = (
        b"<rss><channel><item><pubDate>Sun, 20 Sep 2026 04:40:00 -0700</pubDate>"
        b"</item></channel></rss>"
    )

    with pytest.raises(MalformedPayload, match="title"):
        await GoogleTrendsRssCollector(http_client(body), FEED_URL).collect(AS_OF)
