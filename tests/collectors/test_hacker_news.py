from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.collectors.hacker_news import HackerNewsCollector
from app.collectors.http import SafeHttpClient
from app.models.enums import Source

AS_OF = datetime(2026, 9, 23, 3, 0, tzinfo=UTC)
FIXTURES = Path(__file__).parents[1] / "fixtures"


def hn_http() -> SafeHttpClient:
    stories = (FIXTURES / "hacker_news_topstories.json").read_bytes()
    items = json.loads((FIXTURES / "hacker_news_items.json").read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in items}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/topstories.json"):
            return httpx.Response(200, content=stories, request=request)
        item_id = int(request.url.path.rsplit("/", 1)[-1].removesuffix(".json"))
        return httpx.Response(200, json=by_id[item_id], request=request)

    return SafeHttpClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        allowed_hosts={"hacker-news.firebaseio.com"},
        max_bytes=2_000_000,
        retries=0,
    )


@pytest.mark.asyncio
async def test_hn_collector_preserves_topstory_and_item_payloads() -> None:
    batch = await HackerNewsCollector(hn_http(), max_items=2, now=lambda: AS_OF).collect(AS_OF)

    assert batch.source is Source.HACKER_NEWS
    assert batch.items[0].metadata["hn_score"] == 412
    assert batch.items[0].original_url == "https://acme.example/blog/agent-sdk-1"
    assert batch.items[1].original_url == "https://news.ycombinator.com/item?id=44002"
    envelope = json.loads(batch.raw_bytes)
    assert envelope["top_story_ids"] == [44001, 44002]
    assert [item["id"] for item in envelope["items"]] == [44001, 44002]
    assert len(envelope["request_urls"]) == 3
