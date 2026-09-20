from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.collectors.base import MalformedPayload
from app.collectors.http import SafeHttpClient
from app.collectors.wikimedia import WikimediaTopPagesCollector
from app.models.enums import Source

AS_OF = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
BASE_URL = "https://wikimedia.org/api/rest_v1"
FIXTURE = Path(__file__).parents[1] / "fixtures" / "wikimedia_top_kr.json"


def http_client(body: bytes, requested_urls: list[str] | None = None) -> SafeHttpClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if requested_urls is not None:
            requested_urls.append(str(request.url))
        return httpx.Response(200, content=body)

    return SafeHttpClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        allowed_hosts={"wikimedia.org"},
        max_bytes=2_000_000,
        retries=0,
    )


@pytest.mark.asyncio
async def test_wikimedia_maps_country_page_metrics_without_relabeling_views() -> None:
    urls: list[str] = []
    collector = WikimediaTopPagesCollector(http_client(FIXTURE.read_bytes(), urls), BASE_URL)

    batch = await collector.collect(AS_OF)

    assert urls == [
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/top-per-country/KR/all-access/2026/09/18"
    ]
    assert batch.source is Source.WIKIMEDIA
    assert [item.canonical_text for item in batch.items] == [
        "위키백과:대문",
        "이현중 (농구 선수)",
    ]
    assert batch.items[1].metrics == {
        "access": "all-access",
        "article": "이현중_(농구_선수)",
        "country": "KR",
        "date": "2026-09-18",
        "project": "ko.wikipedia",
        "rank": 12,
        "views_ceil": 2500,
    }


@pytest.mark.asyncio
async def test_wikimedia_empty_articles_returns_empty_batch() -> None:
    body = (
        b'{"items":[{"country":"KR","access":"all-access","year":"2026",'
        b'"month":"09","day":"18","articles":[]}]}'
    )

    batch = await WikimediaTopPagesCollector(http_client(body), BASE_URL).collect(AS_OF)

    assert batch.items == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        b'{"items": {}}',
        b'{"items":[{"country":"KR","articles":[{"rank":1}]}]}',
    ],
)
async def test_wikimedia_rejects_malformed_payload(body: bytes) -> None:
    with pytest.raises(MalformedPayload):
        await WikimediaTopPagesCollector(http_client(body), BASE_URL).collect(AS_OF)
