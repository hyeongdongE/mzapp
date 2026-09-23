from __future__ import annotations

import hashlib
import html
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import urlsplit
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.collectors.base import CollectionBatch, MalformedPayload, SourceItem
from app.collectors.http import SafeHttpClient
from app.models.enums import Source

ATOM = "{http://www.w3.org/2005/Atom}"
OFFICIAL_HOST = "news.hada.io"


class GeekNewsAtomCollector:
    source = Source.GEEKNEWS
    collector_version = "geeknews-atom-v1"
    parser_version = "geeknews-atom-parser-v2"

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
        del as_of
        raw_bytes = await self._http.get_bytes(self._url)
        collected_at = self._now().astimezone(UTC)
        return CollectionBatch(
            source=self.source,
            collected_at=collected_at,
            request_url=self._url,
            raw_bytes=raw_bytes,
            items=parse_geeknews_atom(raw_bytes, collected_at, self._url),
            collector_version=self.collector_version,
            parser_version=self.parser_version,
            coverage_complete=True,
        )


def parse_geeknews_atom(
    raw_bytes: bytes,
    observed_at: datetime,
    fallback_url: str,
    *,
    decode_html_entities: bool = True,
) -> list[SourceItem]:
    """Parse a stored official GeekNews Atom payload without network I/O."""
    try:
        root = ElementTree.fromstring(raw_bytes, forbid_dtd=True, forbid_entities=True)
    except (ParseError, DefusedXmlException, ValueError) as exc:
        raise MalformedPayload("GeekNews returned malformed Atom XML") from exc
    if root.tag != f"{ATOM}feed":
        raise MalformedPayload("GeekNews Atom feed root is missing")

    parsed: list[SourceItem] = []
    seen: set[str] = set()
    for entry in root.findall(f"{ATOM}entry"):
        title = (entry.findtext(f"{ATOM}title") or "").strip()
        if decode_html_entities:
            title = html.unescape(title)
        entry_id = (entry.findtext(f"{ATOM}id") or "").strip()
        published_raw = (entry.findtext(f"{ATOM}published") or "").strip()
        if not title or not entry_id or not published_raw:
            raise MalformedPayload("GeekNews entry identity, title, or timestamp is missing")
        try:
            source_timestamp = datetime.fromisoformat(
                published_raw.replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise MalformedPayload("GeekNews entry timestamp is invalid") from exc
        if source_timestamp.tzinfo is None:
            raise MalformedPayload("GeekNews entry timestamp must include a timezone")

        digest = hashlib.sha256(entry_id.encode("utf-8")).hexdigest()
        source_item_id = f"geeknews:{digest}"
        if source_item_id in seen:
            continue
        seen.add(source_item_id)

        link = _alternate_link(entry)
        source_url = link if _is_official_url(link) else fallback_url
        parsed.append(
            SourceItem(
                source_item_id=source_item_id,
                source_timestamp=source_timestamp.astimezone(UTC),
                observed_at=observed_at.astimezone(UTC),
                canonical_text=title,
                source_url=source_url,
                metrics={"entry_id": entry_id, "link": source_url},
                title=title,
                original_url=source_url,
                snippet=None,
                metadata={"attribution": "GeekNews"},
            )
        )
    return parsed


def _alternate_link(entry) -> str:
    for link in entry.findall(f"{ATOM}link"):
        if link.attrib.get("rel", "alternate") == "alternate":
            return link.attrib.get("href", "").strip()
    return ""


def _is_official_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme == "https" and parsed.hostname == OFFICIAL_HOST
