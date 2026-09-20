from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

import httpx

from app.collectors.base import HttpRequestFailed, OutboundHostDenied, ResponseTooLarge

TRANSIENT_STATUS_CODES = frozenset({429, 502, 503, 504})


class SafeHttpClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        allowed_hosts: set[str] | frozenset[str],
        max_bytes: int,
        retries: int,
        timeout_seconds: float = 10.0,
        user_agent: str = "TrendRadarPoC/0.1 (local-development)",
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client
        self._allowed_hosts = frozenset(host.lower() for host in allowed_hosts)
        self._max_bytes = max_bytes
        self._retries = retries
        self._timeout = httpx.Timeout(timeout_seconds)
        self._user_agent = user_agent
        self._sleep = sleep

    async def get_bytes(self, url: str) -> bytes:
        self._validate_url(url)
        for attempt in range(self._retries + 1):
            try:
                result = await self._request_once(url)
                if isinstance(result, bytes):
                    return result
                status_code = result
                if status_code in TRANSIENT_STATUS_CODES and attempt < self._retries:
                    await self._sleep(min(2**attempt, 8))
                    continue
                raise HttpRequestFailed(f"HTTP_{status_code}", status_code)
            except httpx.TimeoutException as exc:
                if attempt < self._retries:
                    await self._sleep(min(2**attempt, 8))
                    continue
                raise HttpRequestFailed("TIMEOUT") from exc
            except httpx.RequestError as exc:
                raise HttpRequestFailed("NETWORK_ERROR") from exc
        raise HttpRequestFailed("RETRY_EXHAUSTED")

    async def _request_once(self, url: str) -> bytes | int:
        async with self._client.stream(
            "GET",
            url,
            headers={"User-Agent": self._user_agent, "Accept": "application/json, text/xml"},
            follow_redirects=False,
            timeout=self._timeout,
        ) as response:
            if not 200 <= response.status_code < 300:
                return response.status_code
            content_length = response.headers.get("content-length")
            if (
                content_length is not None
                and content_length.isdecimal()
                and int(content_length) > self._max_bytes
            ):
                raise ResponseTooLarge("official source response exceeded configured limit")
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > self._max_bytes:
                    raise ResponseTooLarge("official source response exceeded configured limit")
                chunks.append(chunk)
            return b"".join(chunks)

    def _validate_url(self, url: str) -> None:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or host not in self._allowed_hosts:
            raise OutboundHostDenied("outbound URL is not an approved official source")
        if parsed.username is not None or parsed.password is not None:
            raise OutboundHostDenied("outbound URL must not contain credentials")
