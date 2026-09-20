from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.collectors.http import SafeHttpClient
from app.collectors.wikidata import WikidataClient

FIXTURES = Path(__file__).parents[1] / "fixtures"
ENDPOINT = "https://www.wikidata.org/w/api.php"


@pytest.mark.asyncio
async def test_wikidata_uses_read_only_actions_and_parses_entity_metadata() -> None:
    requested: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url)
        action = request.url.params["action"]
        fixture = (
            "wikidata_search.json" if action == "wbsearchentities" else "wikidata_entities.json"
        )
        return httpx.Response(200, content=(FIXTURES / fixture).read_bytes(), request=request)

    safe_http = SafeHttpClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        allowed_hosts={"www.wikidata.org"},
        max_bytes=100_000,
        retries=0,
    )
    acquired_at = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)

    result = await WikidataClient(safe_http, ENDPOINT, now=lambda: acquired_at).lookup("이현중")

    assert [url.params["action"] for url in requested] == [
        "wbsearchentities",
        "wbgetentities",
    ]
    assert requested[0].params["language"] == "ko"
    assert requested[0].params["type"] == "item"
    assert result.matches[0].entity_id == "Q123"
    assert result.matches[0].label == "이현중"
    assert {"Lee Hyunjung", "이현중 농구", "Hyunjung Lee"} <= set(result.matches[0].aliases)
    assert result.matches[0].instance_of == ("Q5",)
    assert len(result.raw_responses) == 2
    assert {response.collected_at for response in result.raw_responses} == {acquired_at}
