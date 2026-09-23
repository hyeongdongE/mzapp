from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import urlparse

from app.collectors.base import CollectionBatch, MalformedPayload, SourceItem
from app.collectors.http import SafeHttpClient
from app.models.enums import Source


class GitHubReleasesCollector:
    source = Source.GITHUB_RELEASES
    collector_version = "github-releases-api-v1"
    parser_version = "github-releases-parser-v1"

    def __init__(
        self,
        http: SafeHttpClient,
        *,
        repository: str,
        api_base_url: str = "https://api.github.com",
        now: Callable[[], datetime] | None = None,
    ) -> None:
        owner, separator, name = repository.partition("/")
        if not separator or not owner or not name or "/" in name:
            raise ValueError("repository must use owner/name")
        self._http = http
        self._repository = repository
        self._url = (
            f"{api_base_url.rstrip('/')}/repos/{owner}/{name}/releases?per_page=1"
        )
        self._now = now or (lambda: datetime.now(UTC))

    @property
    def collection_key(self) -> str:
        return self._repository

    async def collect(self, as_of: datetime) -> CollectionBatch:
        del as_of
        raw_bytes = await self._http.get_bytes(self._url)
        collected_at = self._now().astimezone(UTC)
        try:
            payloads = json.loads(raw_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MalformedPayload("GitHub releases payload is invalid") from exc
        if not isinstance(payloads, list):
            raise MalformedPayload("GitHub releases payload must be a list")
        items = [
            _parse_release(self._repository, payload, collected_at)
            for payload in payloads
            if isinstance(payload, dict) and not payload.get("draft", False)
        ]
        return CollectionBatch(
            source=self.source,
            collected_at=collected_at,
            request_url=self._url,
            raw_bytes=raw_bytes,
            items=items,
            collector_version=self.collector_version,
            parser_version=self.parser_version,
            coverage_complete=True,
        )


def _parse_release(repository: str, payload: dict, observed_at: datetime) -> SourceItem:
    release_id = payload.get("id")
    tag = payload.get("tag_name")
    url = payload.get("html_url")
    published_raw = payload.get("published_at")
    if not isinstance(release_id, int) or not all(
        isinstance(value, str) and value for value in (tag, url, published_raw)
    ):
        raise MalformedPayload("GitHub release identity is incomplete")
    parsed_url = urlparse(url)
    expected_prefix = f"/{repository.casefold()}/releases/"
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname != "github.com"
        or not parsed_url.path.casefold().startswith(expected_prefix)
    ):
        raise MalformedPayload("GitHub release URL is not trusted")
    try:
        published_at = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MalformedPayload("GitHub release timestamp is invalid") from exc
    title = payload.get("name") if isinstance(payload.get("name"), str) else tag
    author = payload.get("author")
    author_login = author.get("login") if isinstance(author, dict) else None
    body = payload.get("body") if isinstance(payload.get("body"), str) else None
    return SourceItem(
        source_item_id=f"github:{repository}:{release_id}",
        source_timestamp=published_at.astimezone(UTC),
        observed_at=observed_at,
        canonical_text=title,
        source_url=url,
        metrics={"release_id": release_id, "prerelease": bool(payload.get("prerelease"))},
        title=title,
        original_url=url,
        author=author_login,
        snippet=body,
        metadata={
            "attribution": "GitHub",
            "repository": repository,
            "release_id": release_id,
            "release_tag": tag,
            "prerelease": bool(payload.get("prerelease")),
        },
    )
