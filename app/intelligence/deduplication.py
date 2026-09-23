from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from app.intelligence.normalization import canonicalize_url
from app.models.enums import Source


class DuplicateKind(StrEnum):
    EXACT = "EXACT"
    DISTINCT = "DISTINCT"


@dataclass(frozen=True)
class DuplicateDecision:
    kind: DuplicateKind
    matched_item_id: int | None
    reason_codes: tuple[str, ...]


class DeduplicationItem(Protocol):
    id: int
    source: Source
    external_id: str
    canonical_url: str
    content_hash: str
    normalized_title: str
    item_metadata: dict[str, Any]


class Deduplicator:
    """Find only deterministic duplicate identities; title similarity is never enough."""

    def decide(
        self,
        candidate: DeduplicationItem,
        existing: list[DeduplicationItem],
    ) -> DuplicateDecision:
        for item in sorted(existing, key=lambda value: value.id):
            reason = _exact_identity(candidate, item)
            if reason is not None:
                return DuplicateDecision(DuplicateKind.EXACT, item.id, (reason,))
        return DuplicateDecision(
            DuplicateKind.DISTINCT,
            None,
            ("NO_DETERMINISTIC_IDENTITY",),
        )


def _exact_identity(
    candidate: DeduplicationItem, existing: DeduplicationItem
) -> str | None:
    if (
        candidate.source == existing.source
        and candidate.external_id
        and candidate.external_id == existing.external_id
    ):
        return "SAME_SOURCE_EXTERNAL_ID"

    if (
        candidate.canonical_url
        and existing.canonical_url
        and canonicalize_url(candidate.canonical_url)
        == canonicalize_url(existing.canonical_url)
    ):
        return "SAME_CANONICAL_URL"

    if candidate.content_hash and candidate.content_hash == existing.content_hash:
        return "SAME_CONTENT_HASH"

    if (
        candidate.source is Source.GITHUB_RELEASES
        and existing.source is Source.GITHUB_RELEASES
        and _github_identity(candidate) is not None
        and _github_identity(candidate) == _github_identity(existing)
    ):
        return "SAME_GITHUB_RELEASE"
    return None


def _github_identity(item: DeduplicationItem) -> tuple[str, str] | None:
    repository = item.item_metadata.get("repository")
    release_id = item.item_metadata.get("release_id")
    if not isinstance(repository, str) or release_id is None:
        return None
    return repository.casefold(), str(release_id)
