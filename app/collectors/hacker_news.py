from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime

from app.collectors.base import CollectionBatch, MalformedPayload, SourceItem
from app.collectors.http import SafeHttpClient
from app.models.enums import Source

DEFAULT_BASE_URL = "https://hacker-news.firebaseio.com/v0"


class HackerNewsCollector:
    source = Source.HACKER_NEWS
    collector_version = "hacker-news-api-v1"
    parser_version = "hacker-news-parser-v1"

    def __init__(
        self,
        http: SafeHttpClient,
        *,
        base_url: str = DEFAULT_BASE_URL,
        max_items: int = 30,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._max_items = max_items
        self._now = now or (lambda: datetime.now(UTC))

    async def collect(self, as_of: datetime) -> CollectionBatch:
        del as_of
        top_url = f"{self._base_url}/topstories.json"
        top_bytes = await self._http.get_bytes(top_url)
        try:
            top_ids = json.loads(top_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MalformedPayload("Hacker News top stories payload is invalid") from exc
        if not isinstance(top_ids, list) or not all(isinstance(item, int) for item in top_ids):
            raise MalformedPayload("Hacker News top stories must be integer IDs")
        requested_ids = top_ids[: self._max_items]
        raw_items: list[dict] = []
        request_urls = [top_url]
        for item_id in requested_ids:
            item_url = f"{self._base_url}/item/{item_id}.json"
            request_urls.append(item_url)
            item_bytes = await self._http.get_bytes(item_url)
            try:
                payload = json.loads(item_bytes)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise MalformedPayload("Hacker News item payload is invalid") from exc
            if isinstance(payload, dict):
                raw_items.append(payload)
        collected_at = self._now().astimezone(UTC)
        items = [_parse_story(payload, collected_at) for payload in raw_items]
        items = [item for item in items if item is not None]
        envelope = json.dumps(
            {
                "top_story_ids": requested_ids,
                "items": raw_items,
                "request_urls": request_urls,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return CollectionBatch(
            source=self.source,
            collected_at=collected_at,
            request_url=top_url,
            raw_bytes=envelope,
            items=items,
            collector_version=self.collector_version,
            parser_version=self.parser_version,
        )


def _parse_story(payload: dict, observed_at: datetime) -> SourceItem | None:
    if payload.get("type") != "story" or payload.get("deleted") or payload.get("dead"):
        return None
    item_id = payload.get("id")
    title = payload.get("title")
    timestamp = payload.get("time")
    if not isinstance(item_id, int) or not isinstance(title, str) or not isinstance(timestamp, int):
        raise MalformedPayload("Hacker News story identity, title, or time is invalid")
    discussion_url = f"https://news.ycombinator.com/item?id={item_id}"
    original_url = payload.get("url") if isinstance(payload.get("url"), str) else discussion_url
    return SourceItem(
        source_item_id=f"hn:{item_id}",
        source_timestamp=datetime.fromtimestamp(timestamp, tz=UTC),
        observed_at=observed_at,
        canonical_text=title,
        source_url=discussion_url,
        metrics={
            "hn_score": int(payload.get("score", 0)),
            "hn_comments": int(payload.get("descendants", 0)),
        },
        title=title,
        original_url=original_url,
        author=payload.get("by") if isinstance(payload.get("by"), str) else None,
        metadata={
            "attribution": "Hacker News",
            "hn_score": int(payload.get("score", 0)),
            "hn_comments": int(payload.get("descendants", 0)),
            "original_url": original_url,
        },
    )
