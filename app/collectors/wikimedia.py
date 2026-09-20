from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from app.collectors.base import CollectionBatch, MalformedPayload, SourceItem
from app.collectors.http import SafeHttpClient
from app.models.enums import Source


class WikimediaTopPagesCollector:
    source = Source.WIKIMEDIA
    collector_version = "wikimedia-top-per-country-v1"
    parser_version = "wikimedia-top-per-country-parser-v1"

    def __init__(
        self,
        http: SafeHttpClient,
        base_url: str,
        *,
        country: str = "KR",
        access: str = "all-access",
        data_lag_days: int = 2,
        target_date: date | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._country = country
        self._access = access
        self._data_lag_days = data_lag_days
        self._target_date = target_date
        self._now = now or (lambda: datetime.now(UTC))

    async def collect(self, as_of: datetime) -> CollectionBatch:
        target_date = self._target_date or (
            as_of.astimezone(UTC).date() - timedelta(days=self._data_lag_days)
        )
        request_url = (
            f"{self._base_url}/metrics/pageviews/top-per-country/"
            f"{self._country}/{self._access}/{target_date:%Y/%m/%d}"
        )
        raw_bytes = await self._http.get_bytes(request_url)
        collected_at = self._now().astimezone(UTC)
        items = self._parse(raw_bytes, collected_at, request_url)
        return CollectionBatch(
            source=self.source,
            collected_at=collected_at,
            request_url=request_url,
            raw_bytes=raw_bytes,
            items=items,
            collector_version=self.collector_version,
            parser_version=self.parser_version,
        )

    def _parse(self, raw_bytes: bytes, observed_at: datetime, source_url: str) -> list[SourceItem]:
        try:
            payload = json.loads(raw_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MalformedPayload("Wikimedia returned malformed JSON") from exc
        top_items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(top_items, list):
            raise MalformedPayload("Wikimedia items must be a list")
        parsed: list[SourceItem] = []
        for top_item in top_items:
            parsed.extend(self._parse_top_item(top_item, observed_at, source_url))
        return parsed

    def _parse_top_item(
        self, value: Any, observed_at: datetime, source_url: str
    ) -> list[SourceItem]:
        if not isinstance(value, dict):
            raise MalformedPayload("Wikimedia item must be an object")
        articles = value.get("articles")
        required_date = (value.get("year"), value.get("month"), value.get("day"))
        if not isinstance(articles, list) or not all(
            isinstance(part, str) for part in required_date
        ):
            raise MalformedPayload("Wikimedia item date or articles is invalid")
        try:
            item_date = datetime.strptime("-".join(required_date), "%Y-%m-%d").date()
        except ValueError as exc:
            raise MalformedPayload("Wikimedia item date is invalid") from exc
        source_timestamp = datetime.combine(item_date, time.min, tzinfo=UTC)
        return [
            self._parse_article(article, value, source_timestamp, observed_at, source_url)
            for article in articles
        ]

    def _parse_article(
        self,
        article: Any,
        top_item: dict[str, Any],
        source_timestamp: datetime,
        observed_at: datetime,
        source_url: str,
    ) -> SourceItem:
        if not isinstance(article, dict):
            raise MalformedPayload("Wikimedia article must be an object")
        title = article.get("article")
        project = article.get("project")
        rank = article.get("rank")
        if not isinstance(title, str) or not isinstance(project, str) or not isinstance(rank, int):
            raise MalformedPayload("Wikimedia article, project, or rank is missing")
        date_text = source_timestamp.date().isoformat()
        stable_key = f"{top_item.get('country')}|{date_text}|{project}|{title}".encode()
        source_item_id = f"wikimedia:{hashlib.sha256(stable_key).hexdigest()}"
        views_ceil = article.get("views_ceil")
        if views_ceil is not None and not isinstance(views_ceil, int):
            raise MalformedPayload("Wikimedia views_ceil must be an integer or null")
        return SourceItem(
            source_item_id=source_item_id,
            source_timestamp=source_timestamp,
            observed_at=observed_at,
            canonical_text=title.replace("_", " "),
            source_url=source_url,
            metrics={
                "access": top_item.get("access"),
                "article": title,
                "country": top_item.get("country"),
                "date": date_text,
                "project": project,
                "rank": rank,
                "views_ceil": views_ceil,
            },
        )
