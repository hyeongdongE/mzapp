from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from app.intelligence.deduplication import Deduplicator, DuplicateKind
from app.models.enums import Source

VERSION_PATTERN = re.compile(r"\bv?(\d+)\.(\d+)(?:\.\d+)?(?:[-+][a-z0-9.-]+)?\b")
TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*")
STOPWORDS = frozenset(
    {
        "a",
        "an",
        "for",
        "in",
        "introducing",
        "is",
        "new",
        "of",
        "on",
        "out",
        "released",
        "release",
        "support",
        "the",
        "to",
        "update",
        "version",
    }
)


class ClusterAction(StrEnum):
    MERGE = "MERGE"
    NEW = "NEW"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class ClusterDecision:
    action: ClusterAction
    cluster_id: int
    score: float
    reason_codes: tuple[str, ...]
    item_id: int


class ClusterItem(Protocol):
    id: int
    source: Source
    external_id: str
    canonical_url: str
    content_hash: str
    normalized_title: str
    item_metadata: dict[str, Any]


@dataclass
class EventClusterDraft:
    id: int
    members: list[ClusterItem] = field(default_factory=list)
    needs_review: bool = False

    @property
    def source_count(self) -> int:
        return len({item.source for item in self.members})


@dataclass(frozen=True)
class ClusteringResult:
    clusters: tuple[EventClusterDraft, ...]
    decisions: tuple[ClusterDecision, ...]
    incorrect_merge_count: int


class ConservativeClusterer:
    def __init__(self, *, deduplicator: Deduplicator | None = None) -> None:
        self._deduplicator = deduplicator or Deduplicator()

    def process(self, items: list[ClusterItem]) -> ClusteringResult:
        clusters: list[EventClusterDraft] = []
        decisions: list[ClusterDecision] = []
        incorrect_merges = 0
        for candidate in sorted(items, key=lambda item: item.id):
            merge = self._best_candidate(candidate, clusters, ClusterAction.MERGE)
            if merge is not None:
                cluster, score, reasons = merge
                if _conflicts_with_expected_event(candidate, cluster.members):
                    incorrect_merges += 1
                cluster.members.append(candidate)
                decisions.append(
                    ClusterDecision(
                        ClusterAction.MERGE,
                        cluster.id,
                        score,
                        reasons,
                        candidate.id,
                    )
                )
                continue

            review = self._best_candidate(candidate, clusters, ClusterAction.REVIEW)
            cluster = EventClusterDraft(
                id=len(clusters) + 1,
                members=[candidate],
                needs_review=review is not None,
            )
            clusters.append(cluster)
            if review is None:
                action = ClusterAction.NEW
                score = 0.0
                reasons = ("NO_HIGH_PRECISION_MATCH",)
            else:
                action = ClusterAction.REVIEW
                score = review[1]
                reasons = review[2] + (f"CANDIDATE_CLUSTER_{review[0].id}",)
            decisions.append(
                ClusterDecision(action, cluster.id, score, reasons, candidate.id)
            )
        return ClusteringResult(tuple(clusters), tuple(decisions), incorrect_merges)

    def _best_candidate(
        self,
        candidate: ClusterItem,
        clusters: list[EventClusterDraft],
        action: ClusterAction,
    ) -> tuple[EventClusterDraft, float, tuple[str, ...]] | None:
        matches: list[tuple[EventClusterDraft, float, tuple[str, ...]]] = []
        for cluster in clusters:
            pair_matches = [
                _pair_decision(candidate, member, self._deduplicator)
                for member in cluster.members
            ]
            eligible = [match for match in pair_matches if match[0] is action]
            if eligible:
                _, score, reasons = max(eligible, key=lambda match: match[1])
                matches.append((cluster, score, reasons))
        if not matches:
            return None
        return max(matches, key=lambda match: (match[1], -match[0].id))


def _pair_decision(
    candidate: ClusterItem,
    existing: ClusterItem,
    deduplicator: Deduplicator,
) -> tuple[ClusterAction, float, tuple[str, ...]]:
    duplicate = deduplicator.decide(candidate, [existing])
    if duplicate.kind is DuplicateKind.EXACT:
        return ClusterAction.MERGE, 1.0, duplicate.reason_codes

    if _explicit_release_conflict(candidate, existing):
        return ClusterAction.NEW, 0.0, ("EXPLICIT_RELEASE_CONFLICT",)

    shared_entities = _entity_phrases(candidate) & _entity_phrases(existing)
    shared_versions = _release_versions(candidate) & _release_versions(existing)
    similarity = _token_similarity(candidate.normalized_title, existing.normalized_title)
    if shared_entities and shared_versions and similarity >= 0.25:
        return (
            ClusterAction.MERGE,
            0.9,
            ("SHARED_ENTITY", "SHARED_RELEASE", "COMPATIBLE_TITLE"),
        )
    if shared_entities and similarity >= 0.45:
        return ClusterAction.REVIEW, 0.6, ("AMBIGUOUS_ENTITY_TITLE_MATCH",)
    return ClusterAction.NEW, 0.0, ("NO_HIGH_PRECISION_MATCH",)


def _release_versions(item: ClusterItem) -> set[str]:
    versions = {
        f"{match.group(1)}.{match.group(2)}"
        for match in VERSION_PATTERN.finditer(item.normalized_title)
    }
    tag = item.item_metadata.get("release_tag")
    if isinstance(tag, str):
        versions.update(
            f"{match.group(1)}.{match.group(2)}"
            for match in VERSION_PATTERN.finditer(tag.casefold())
        )
    return versions


def _entity_phrases(item: ClusterItem) -> set[str]:
    tokens = [token for token in TOKEN_PATTERN.findall(item.normalized_title) if token]
    significant = [
        token
        for token in tokens
        if token not in STOPWORDS and VERSION_PATTERN.fullmatch(token) is None
    ]
    phrases = {
        f"{left} {right}"
        for left, right in zip(significant, significant[1:], strict=False)
    }
    repository = item.item_metadata.get("repository")
    if isinstance(repository, str) and "/" in repository:
        owner, product = repository.casefold().split("/", 1)
        phrases.update({owner.replace("-", " "), product.replace("-", " ")})
    if item.source is Source.OFFICIAL_CLOUDFLARE:
        phrases.add("cloudflare")
    if item.source is Source.OFFICIAL_AWS:
        phrases.add("aws")
    return phrases


def _token_similarity(left: str, right: str) -> float:
    left_tokens = set(TOKEN_PATTERN.findall(left))
    right_tokens = set(TOKEN_PATTERN.findall(right))
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union) if union else 0.0


def _explicit_release_conflict(left: ClusterItem, right: ClusterItem) -> bool:
    left_repository = left.item_metadata.get("repository")
    right_repository = right.item_metadata.get("repository")
    left_release = left.item_metadata.get("release_id")
    right_release = right.item_metadata.get("release_id")
    return (
        isinstance(left_repository, str)
        and isinstance(right_repository, str)
        and left_repository.casefold() == right_repository.casefold()
        and left_release is not None
        and right_release is not None
        and str(left_release) != str(right_release)
    )


def _conflicts_with_expected_event(
    candidate: ClusterItem, members: list[ClusterItem]
) -> bool:
    candidate_event = getattr(candidate, "event_id", None)
    if candidate_event is None:
        return False
    return any(
        getattr(member, "event_id", candidate_event) != candidate_event
        for member in members
    )
