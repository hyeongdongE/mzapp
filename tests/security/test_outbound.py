from __future__ import annotations

import httpx
import pytest

from app.collectors.base import HttpRequestFailed, OutboundHostDenied, ResponseTooLarge
from app.collectors.http import SafeHttpClient


@pytest.mark.asyncio
async def test_http_client_rejects_feed_supplied_host_without_requesting_it() -> None:
    def unexpected_request(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("denied host reached the transport")

    safe_client = SafeHttpClient(
        httpx.AsyncClient(transport=httpx.MockTransport(unexpected_request)),
        allowed_hosts={"trends.google.com"},
        max_bytes=100,
        retries=0,
    )

    with pytest.raises(OutboundHostDenied):
        await safe_client.get_bytes("https://news.example/ignore-previous-instructions")


@pytest.mark.asyncio
async def test_http_client_retries_429_then_returns_success() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, request=request)
        return httpx.Response(200, content=b"ok", request=request)

    async def no_wait(_seconds: float) -> None:
        return None

    safe_client = SafeHttpClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        allowed_hosts={"trends.google.com"},
        max_bytes=100,
        retries=1,
        sleep=no_wait,
    )

    assert await safe_client.get_bytes("https://trends.google.com/feed") == b"ok"
    assert attempts == 2


@pytest.mark.asyncio
async def test_http_client_reports_timeout_without_response_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret response body", request=request)

    safe_client = SafeHttpClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        allowed_hosts={"wikimedia.org"},
        max_bytes=100,
        retries=0,
    )

    with pytest.raises(HttpRequestFailed) as raised:
        await safe_client.get_bytes("https://wikimedia.org/api")

    assert raised.value.code == "TIMEOUT"
    assert "secret response body" not in str(raised.value)


@pytest.mark.asyncio
async def test_http_client_rejects_permanent_server_error() -> None:
    safe_client = SafeHttpClient(
        httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(500, content=b"private payload", request=request)
            )
        ),
        allowed_hosts={"wikimedia.org"},
        max_bytes=100,
        retries=0,
    )

    with pytest.raises(HttpRequestFailed) as raised:
        await safe_client.get_bytes("https://wikimedia.org/api")

    assert raised.value.code == "HTTP_500"
    assert "private payload" not in str(raised.value)


@pytest.mark.asyncio
async def test_http_client_rejects_oversized_response() -> None:
    safe_client = SafeHttpClient(
        httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=b"12345", request=request)
            )
        ),
        allowed_hosts={"wikimedia.org"},
        max_bytes=4,
        retries=0,
    )

    with pytest.raises(ResponseTooLarge):
        await safe_client.get_bytes("https://wikimedia.org/api")


@pytest.mark.asyncio
@pytest.mark.parametrize("content_length", ["invalid", "-1", "4, 4"])
async def test_http_client_ignores_malformed_content_length_and_enforces_stream_limit(
    content_length: str,
) -> None:
    safe_client = SafeHttpClient(
        httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    content=b"1234",
                    headers={"content-length": content_length},
                    request=request,
                )
            )
        ),
        allowed_hosts={"wikimedia.org"},
        max_bytes=4,
        retries=0,
    )

    assert await safe_client.get_bytes("https://wikimedia.org/api") == b"1234"
