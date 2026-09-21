from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.collectors.base import HttpRequestFailed, MalformedPayload
from app.collectors.geeknews import GeekNewsAtomCollector
from app.collectors.http import SafeHttpClient
from app.models.enums import Source

AS_OF = datetime(2026, 9, 21, 5, 0, tzinfo=UTC)
FEED_URL = "https://news.hada.io/rss/news"
FIXTURE = Path(__file__).parents[1] / "fixtures" / "geeknews_atom.xml"


def http_client(body: bytes, *, timeout: bool = False) -> SafeHttpClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if timeout:
            raise httpx.ReadTimeout("private body", request=request)
        return httpx.Response(200, content=body, request=request)

    return SafeHttpClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        allowed_hosts={"news.hada.io"},
        max_bytes=2_000_000,
        retries=0,
    )


@pytest.mark.asyncio
async def test_geeknews_maps_only_atom_identity_title_link_and_timestamp() -> None:
    acquired_at = datetime(2026, 9, 21, 5, 0, 5, tzinfo=UTC)
    collector = GeekNewsAtomCollector(
        http_client(FIXTURE.read_bytes()), FEED_URL, now=lambda: acquired_at
    )

    batch = await collector.collect(AS_OF)

    assert batch.source is Source.GEEKNEWS
    assert batch.collected_at == acquired_at
    assert batch.raw_bytes == FIXTURE.read_bytes()
    assert [item.canonical_text for item in batch.items] == [
        "LangChain은 유료 광고 운영 에이전트를 어떻게 만들었나",
        "안전하지 않은 링크 예제",
    ]
    assert batch.items[0].source_timestamp == datetime(
        2026, 9, 21, 0, 55, 1, tzinfo=UTC
    )
    assert batch.items[0].source_url == "https://news.hada.io/topic?id=34041"
    assert batch.items[0].metrics == {
        "entry_id": "https://news.hada.io/topic?id=34041",
        "link": "https://news.hada.io/topic?id=34041",
    }
    assert batch.items[1].source_url == FEED_URL
    assert len({item.source_item_id for item in batch.items}) == 2
    assert all(item.source_item_id.startswith("geeknews:") for item in batch.items)


@pytest.mark.asyncio
async def test_geeknews_empty_feed_returns_empty_batch() -> None:
    body = b'<feed xmlns="http://www.w3.org/2005/Atom"><title>GeekNews</title></feed>'

    batch = await GeekNewsAtomCollector(http_client(body), FEED_URL).collect(AS_OF)

    assert batch.items == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        b"not xml",
        b"<!DOCTYPE x [<!ENTITY e SYSTEM 'file:///etc/passwd'>]><feed>&e;</feed>",
        b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>x</title></entry></feed>',
        b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>x</id><title>x</title><published>not-a-time</published></entry></feed>',
    ],
)
async def test_geeknews_rejects_malformed_or_incomplete_atom(body: bytes) -> None:
    with pytest.raises(MalformedPayload):
        await GeekNewsAtomCollector(http_client(body), FEED_URL).collect(AS_OF)


@pytest.mark.asyncio
async def test_geeknews_timeout_uses_redacted_collector_error() -> None:
    with pytest.raises(HttpRequestFailed) as raised:
        await GeekNewsAtomCollector(http_client(b"", timeout=True), FEED_URL).collect(AS_OF)

    assert raised.value.code == "TIMEOUT"
    assert "private body" not in str(raised.value)
