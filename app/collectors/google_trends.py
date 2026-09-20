from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.collectors.base import CollectionBatch, MalformedPayload, SourceItem
from app.collectors.http import SafeHttpClient
from app.models.enums import Source

HT = "{https://trends.google.com/trending/rss}"
TRAFFIC_PATTERN = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s*(천|만|[KkMm])?\+?$")
TRAFFIC_MULTIPLIERS = {None: 1, "천": 1_000, "만": 10_000, "k": 1_000, "m": 1_000_000}


class GoogleTrendsRssCollector:
    source = Source.GOOGLE_TRENDS
    collector_version = "google-rss-v1"
    parser_version = "google-rss-parser-v1"

    def __init__(
        self,
        http: SafeHttpClient,
        url: str,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._http = http
        self._url = url
        self._now = now or (lambda: datetime.now(UTC))

    async def collect(self, as_of: datetime) -> CollectionBatch:
        raw_bytes = await self._http.get_bytes(self._url)
        collected_at = self._now().astimezone(UTC)
        items = self._parse(raw_bytes, collected_at)
        return CollectionBatch(
            source=self.source,
            collected_at=collected_at,
            request_url=self._url,
            raw_bytes=raw_bytes,
            items=items,
            collector_version=self.collector_version,
            parser_version=self.parser_version,
        )

    def _parse(self, raw_bytes: bytes, observed_at: datetime) -> list[SourceItem]:
        return parse_google_trends_rss(raw_bytes, observed_at, self._url)


def parse_google_trends_rss(
    raw_bytes: bytes, observed_at: datetime, fallback_url: str
) -> list[SourceItem]:
    """Parse a stored Google Trends payload without performing network I/O."""
    return _GoogleTrendsParser(fallback_url).parse(raw_bytes, observed_at)


class _GoogleTrendsParser:
    def __init__(self, fallback_url: str) -> None:
        self._url = fallback_url

    def parse(self, raw_bytes: bytes, observed_at: datetime) -> list[SourceItem]:
        try:
            root = ElementTree.fromstring(raw_bytes, forbid_dtd=True, forbid_entities=True)
        except (ParseError, DefusedXmlException, ValueError) as exc:
            raise MalformedPayload("Google Trends returned malformed XML") from exc
        channel = root.find("channel")
        if channel is None:
            raise MalformedPayload("Google Trends RSS channel is missing")
        return [self._parse_item(item, observed_at) for item in channel.findall("item")]

    def _parse_item(self, item, observed_at: datetime) -> SourceItem:
        title = (item.findtext("title") or "").strip()
        if not title:
            raise MalformedPayload("Google Trends item title is missing")
        pub_date_raw = (item.findtext("pubDate") or "").strip()
        if not pub_date_raw:
            raise MalformedPayload("Google Trends item publication timestamp is missing")
        try:
            source_timestamp = parsedate_to_datetime(pub_date_raw).astimezone(UTC)
        except (TypeError, ValueError, OverflowError) as exc:
            raise MalformedPayload("Google Trends item publication timestamp is invalid") from exc
        traffic_raw = (item.findtext(f"{HT}approx_traffic") or "").strip() or None
        news_items = []
        for news in item.findall(f"{HT}news_item"):
            news_items.append(
                {
                    "source": (news.findtext(f"{HT}news_item_source") or "").strip() or None,
                    "title": (news.findtext(f"{HT}news_item_title") or "").strip() or None,
                    "url": (news.findtext(f"{HT}news_item_url") or "").strip() or None,
                }
            )
        stable_key = f"{title.casefold()}|{source_timestamp.isoformat()}".encode()
        source_item_id = f"google:{hashlib.sha256(stable_key).hexdigest()}"
        source_url = (item.findtext("link") or "").strip()
        if urlsplit(source_url).hostname != "trends.google.com":
            source_url = self._url
        return SourceItem(
            source_item_id=source_item_id,
            source_timestamp=source_timestamp,
            observed_at=observed_at,
            canonical_text=title,
            source_url=source_url,
            metrics={
                "active": None,
                "approx_traffic_lower_bound": parse_approx_traffic(traffic_raw),
                "approx_traffic_raw": traffic_raw,
                "news_items": news_items,
                "related_queries": [],
                "trend_change": None,
            },
        )


def parse_approx_traffic(value: str | None) -> int | None:
    if value is None:
        return None
    normalized = value.replace(",", "").strip()
    match = TRAFFIC_PATTERN.fullmatch(normalized)
    if match is None:
        return None
    number, unit = match.groups()
    try:
        multiplier = TRAFFIC_MULTIPLIERS[unit.lower() if unit in {"K", "k", "M", "m"} else unit]
        return int(Decimal(number) * multiplier)
    except (InvalidOperation, KeyError):
        return None
