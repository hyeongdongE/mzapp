from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.collectors.base import MalformedPayload
from app.collectors.github_releases import GitHubReleasesCollector
from app.collectors.http import SafeHttpClient
from app.models.enums import Source

AS_OF = datetime(2026, 9, 23, 3, 0, tzinfo=UTC)
FIXTURE = Path(__file__).parents[1] / "fixtures" / "github_releases.json"


@pytest.mark.asyncio
async def test_github_collector_keeps_published_releases_and_repository_identity() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, content=FIXTURE.read_bytes(), request=request)

    http = SafeHttpClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        allowed_hosts={"api.github.com"},
        max_bytes=2_000_000,
        retries=0,
    )
    collector = GitHubReleasesCollector(
        http, repository="acme/agent-sdk", now=lambda: AS_OF
    )
    batch = await collector.collect(AS_OF)

    assert batch.source is Source.GITHUB_RELEASES
    assert collector.collection_key == "acme/agent-sdk"
    assert len(batch.items) == 1
    assert batch.items[0].source_item_id == "github:acme/agent-sdk:991"
    assert batch.items[0].metadata["repository"] == "acme/agent-sdk"
    assert batch.items[0].metadata["release_tag"] == "v1.0.0"
    assert batch.items[0].snippet == "First stable release."
    assert requested_urls == [
        "https://api.github.com/repos/acme/agent-sdk/releases?per_page=1"
    ]


@pytest.mark.asyncio
async def test_github_collector_rejects_untrusted_public_release_link() -> None:
    payload = FIXTURE.read_text(encoding="utf-8").replace(
        "https://github.com/acme/agent-sdk/releases/tag/v1.0.0",
        "javascript:alert(1)",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=payload, request=request)

    http = SafeHttpClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        allowed_hosts={"api.github.com"},
        max_bytes=2_000_000,
        retries=0,
    )

    with pytest.raises(MalformedPayload, match="release URL"):
        await GitHubReleasesCollector(
            http, repository="acme/agent-sdk", now=lambda: AS_OF
        ).collect(AS_OF)
