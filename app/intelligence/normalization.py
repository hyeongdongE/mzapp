from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.collectors.base import JsonValue, SourceItem
from app.intelligence.sources import SOURCE_REGISTRY
from app.models.enums import Source

TRACKING_PARAMETERS = frozenset(
    {
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "ref",
        "source",
        "utm_campaign",
        "utm_medium",
        "utm_source",
    }
)


@dataclass(frozen=True)
class NormalizedRawItem:
    raw_fetch_id: int
    source: Source
    external_id: str
    title: str
    url: str
    original_url: str | None
    author: str | None
    published_at: datetime
    collected_at: datetime
    canonical_url: str
    content_hash: str
    normalized_title: str
    snippet: str | None
    metadata: dict[str, JsonValue]


def canonicalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    host = (parsed.hostname or "").lower()
    port = parsed.port
    netloc = host
    if port is not None and not (
        (parsed.scheme.lower() == "https" and port == 443)
        or (parsed.scheme.lower() == "http" and port == 80)
    ):
        netloc = f"{host}:{port}"
    query = urlencode(
        sorted(
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in TRACKING_PARAMETERS
        )
    )
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", query, ""))


def normalize_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_source_item(
    source: Source, item: SourceItem, *, raw_fetch_id: int
) -> NormalizedRawItem:
    definition = SOURCE_REGISTRY[source]
    title = (item.title or item.canonical_text).strip()
    original_url = item.original_url or item.source_url
    canonical_url = canonicalize_url(original_url)
    normalized_title = normalize_title(title)
    allowed_snippet = item.snippet if definition.policy.public_summary else None
    content_material = "\n".join((source.value, canonical_url, normalized_title))
    return NormalizedRawItem(
        raw_fetch_id=raw_fetch_id,
        source=source,
        external_id=item.source_item_id,
        title=title,
        url=item.source_url,
        original_url=original_url,
        author=item.author,
        published_at=item.source_timestamp,
        collected_at=item.observed_at,
        canonical_url=canonical_url,
        content_hash=hashlib.sha256(content_material.encode("utf-8")).hexdigest(),
        normalized_title=normalized_title,
        snippet=allowed_snippet,
        metadata=dict(item.metadata),
    )
