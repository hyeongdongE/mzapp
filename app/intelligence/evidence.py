from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app.intelligence.sources import SOURCE_REGISTRY
from app.models.enums import EvidenceKind, Source, SourceType


class EvidenceItem(Protocol):
    source: Source
    external_id: str
    title: str
    url: str
    canonical_url: str
    published_at: datetime
    collected_at: datetime
    item_metadata: dict[str, Any]


@dataclass(frozen=True)
class EvidenceDraft:
    kind: EvidenceKind
    fact: dict[str, Any]
    source_url: str
    observed_at: datetime
    publishable: bool


def evidence_from_raw_item(item: EvidenceItem) -> EvidenceDraft:
    definition = SOURCE_REGISTRY[item.source]
    kind = {
        SourceType.OFFICIAL: EvidenceKind.OFFICIAL,
        SourceType.DEVELOPER: EvidenceKind.DEVELOPER,
        SourceType.COMMUNITY: EvidenceKind.COMMUNITY,
        SourceType.EARLY_SIGNAL: EvidenceKind.EARLY_SIGNAL,
    }[definition.source_type]
    return EvidenceDraft(
        kind=kind,
        fact={
            "external_id": item.external_id,
            "title": item.title,
            "canonical_url": item.canonical_url,
            "published_at": item.published_at.isoformat(),
            "attribution": item.item_metadata.get("attribution", definition.display_name),
        },
        source_url=item.url,
        observed_at=item.collected_at,
        publishable=(
            definition.policy.public_title
            and definition.policy.public_link
            and definition.policy.public_attribution
        ),
    )
