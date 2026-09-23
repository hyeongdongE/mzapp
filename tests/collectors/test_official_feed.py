from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.collectors.http import SafeHttpClient
from app.collectors.official_feed import OfficialFeedCollector
from app.models.enums import Source

AS_OF = datetime(2026, 9, 23, 3, 0, tzinfo=UTC)
FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "host", "url", "fixture", "expected_title"),
    [
        (
            Source.OFFICIAL_CLOUDFLARE,
            "blog.cloudflare.com",
            "https://blog.cloudflare.com/rss/",
            "cloudflare_feed.xml",
            "Introducing Agent Runtime",
        ),
        (
            Source.OFFICIAL_AWS,
            "aws.amazon.com",
            "https://aws.amazon.com/blogs/aws/feed/",
            "aws_feed.xml",
            "AWS announces a new agent service",
        ),
    ],
)
async def test_official_feed_maps_primary_source_metadata(
    source: Source, host: str, url: str, fixture: str, expected_title: str
) -> None:
    body = (FIXTURES / fixture).read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, request=request)

    http = SafeHttpClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        allowed_hosts={host},
        max_bytes=2_000_000,
        retries=0,
    )
    batch = await OfficialFeedCollector(source, http, url, now=lambda: AS_OF).collect(AS_OF)

    assert batch.items[0].title == expected_title
    assert batch.items[0].metadata["attribution"]
    assert batch.items[0].original_url.startswith("https://")
