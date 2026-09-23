from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.collectors.base import CollectionBatch, MalformedPayload, SourceItem
from app.collectors.http import SafeHttpClient
from app.models.enums import Source

DC_CREATOR = "{http://purl.org/dc/elements/1.1/}creator"
ALLOWED_SOURCES = frozenset({Source.OFFICIAL_CLOUDFLARE, Source.OFFICIAL_AWS})
PUBLIC_ITEM_HOSTS = {
    Source.OFFICIAL_CLOUDFLARE: frozenset({"blog.cloudflare.com"}),
    Source.OFFICIAL_AWS: frozenset({"aws.amazon.com"}),
}


class OfficialFeedCollector:
    collector_version = "official-rss-v1"
    parser_version = "official-rss-parser-v1"

    def __init__(
        self,
        source: Source,
        http: SafeHttpClient,
        url: str,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if source not in ALLOWED_SOURCES:
            raise ValueError("official feed source is not approved")
        self.source = source
        self._http = http
        self._url = url
        self._now = now or (lambda: datetime.now(UTC))

    async def collect(self, as_of: datetime) -> CollectionBatch:
        del as_of
        raw_bytes = await self._http.get_bytes(self._url)
        collected_at = self._now().astimezone(UTC)
        return CollectionBatch(
            source=self.source,
            collected_at=collected_at,
            request_url=self._url,
            raw_bytes=raw_bytes,
            items=parse_official_feed(raw_bytes, collected_at, source=self.source),
            collector_version=self.collector_version,
            parser_version=self.parser_version,
            coverage_complete=True,
        )


def parse_official_feed(
    raw_bytes: bytes, observed_at: datetime, *, source: Source
) -> list[SourceItem]:
    try:
        root = ElementTree.fromstring(raw_bytes, forbid_dtd=True, forbid_entities=True)
    except (ParseError, DefusedXmlException, ValueError) as exc:
        raise MalformedPayload("official RSS feed is malformed") from exc
    parsed: list[SourceItem] = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or url).strip()
        published_raw = (item.findtext("pubDate") or "").strip()
        if not title or not url or not guid or not published_raw:
            raise MalformedPayload("official RSS item is incomplete")
        parsed_url = urlparse(url)
        if (
            parsed_url.scheme != "https"
            or parsed_url.hostname not in PUBLIC_ITEM_HOSTS[source]
        ):
            raise MalformedPayload("official RSS item URL is not trusted")
        try:
            published_at = parsedate_to_datetime(published_raw).astimezone(UTC)
        except (TypeError, ValueError) as exc:
            raise MalformedPayload("official RSS item timestamp is invalid") from exc
        author = (item.findtext(DC_CREATOR) or "").strip() or None
        parsed.append(
            SourceItem(
                source_item_id=guid,
                source_timestamp=published_at,
                observed_at=observed_at,
                canonical_text=title,
                source_url=url,
                metrics={},
                title=title,
                original_url=url,
                author=author,
                snippet=(item.findtext("description") or "").strip() or None,
                metadata={"attribution": author or "Official source"},
            )
        )
    return parsed
