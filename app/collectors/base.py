from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.models.enums import Source

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


class CollectorError(RuntimeError):
    code = "COLLECTOR_ERROR"


class MalformedPayload(CollectorError):
    code = "MALFORMED_PAYLOAD"


class OutboundHostDenied(CollectorError):
    code = "OUTBOUND_HOST_DENIED"


class ResponseTooLarge(CollectorError):
    code = "RESPONSE_TOO_LARGE"


class HttpRequestFailed(CollectorError):
    def __init__(self, code: str, status_code: int | None = None) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(f"official source request failed ({code})")


class IncompleteCoverage(CollectorError):
    code = "INCOMPLETE_COVERAGE"


@dataclass(frozen=True)
class SourceItem:
    source_item_id: str
    source_timestamp: datetime
    observed_at: datetime
    canonical_text: str
    source_url: str
    metrics: dict[str, JsonValue]
    title: str | None = None
    original_url: str | None = None
    author: str | None = None
    snippet: str | None = None
    metadata: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class CollectionBatch:
    source: Source
    collected_at: datetime
    request_url: str
    raw_bytes: bytes
    items: list[SourceItem]
    collector_version: str
    parser_version: str
    coverage_complete: bool = False


class Collector(Protocol):
    source: Source

    async def collect(self, as_of: datetime) -> CollectionBatch: ...
