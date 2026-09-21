from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.models.enums import EvidenceStatus, Source

UNKNOWN_CAUSE_MESSAGE = "관심 증가는 확인되었지만 증가 원인은 확인되지 않았습니다."


class ClaimKind(StrEnum):
    WHAT = "WHAT"
    INTEREST = "INTEREST"
    CAUSE = "CAUSE"


class ClaimDraft(BaseModel):
    kind: ClaimKind
    text: str = Field(min_length=1)
    evidence_ids: list[int]


class CheckedClaim(BaseModel):
    draft: ClaimDraft
    status: EvidenceStatus
    reason: str
    publishable: bool


class EvidenceRecord(BaseModel):
    id: int
    entity_id: int
    observation_id: int | None = None
    resolution_attempt_id: int | None = None
    raw_fetch_id: int | None = None
    source: Source
    kind: str
    fact: dict[str, Any]
    source_url: str
    observed_at: datetime


class SummaryContext(BaseModel):
    entity_id: int
    canonical_name: str
    description: str | None
    as_of: datetime
    evidence: list[EvidenceRecord]


class SummaryResult(BaseModel):
    claims: list[ClaimDraft]
    why: str
    requested_urls: list[str] = Field(default_factory=list)


class SummaryProvider(Protocol):
    async def summarize(self, context: SummaryContext) -> SummaryResult: ...


def interest_claim_text(entity_name: str, sources: set[Source]) -> str:
    source_names = {
        Source.GOOGLE_TRENDS: "Google Trends",
        Source.WIKIMEDIA: "Wikimedia",
        Source.WIKIDATA: "Wikidata",
        Source.GEEKNEWS: "GeekNews",
    }
    rendered_sources = ", ".join(
        source_names[source] for source in sorted(sources)
    )
    return f"{entity_name} 관심 신호가 {rendered_sources}에서 관측되었습니다."


def what_claim_text(entity_name: str, description: str) -> str:
    return f"{entity_name}: {description}"
