from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.collectors.base import CollectorError
from app.collectors.wikidata import (
    WikidataClient,
    WikidataLookup,
    WikidataLookupFailed,
    WikidataRawResponse,
)
from app.models.enums import CandidateStatus, ResolutionStatus
from app.models.tables import TrendCandidate
from app.pipeline.classification import classify_metadata
from app.pipeline.normalization import normalize_text
from app.repositories.entities import EntityRepository


@dataclass(frozen=True)
class ResolutionResult:
    entity_id: int | None
    status: ResolutionStatus
    reason: str
    raw_responses: tuple[WikidataRawResponse, ...] = ()


class EntityResolver:
    def __init__(
        self,
        session: Session,
        wikidata: WikidataClient,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._wikidata = wikidata
        self._repo = EntityRepository(session)
        self._now = now or (lambda: datetime.now(UTC))

    async def resolve(self, candidate: TrendCandidate, as_of: datetime) -> ResolutionResult:
        validate_live_cutoff(as_of, self._now().astimezone(UTC))
        if candidate.status in {CandidateStatus.REJECTED, CandidateStatus.MERGED}:
            return self._needs_review(candidate, "INACTIVE_CANDIDATE")
        linked_entities = self._repo.entities_for_candidate(candidate.id)
        if len(linked_entities) > 1:
            return self._needs_review(candidate, "MULTIPLE_EXISTING_ENTITY_LINKS")
        linked_entity = linked_entities[0] if linked_entities else None
        stored = self._repo.entities_by_alias(candidate.normalized_text)
        if len(stored) == 1:
            if linked_entity is not None and linked_entity.id != stored[0].id:
                return self._needs_review(candidate, "ENTITY_RELINK_CONFLICT")
            return self._resolve_to(candidate, stored[0].id, "EXACT_STORED_ALIAS")
        if len(stored) > 1:
            return self._needs_review(candidate, "AMBIGUOUS_STORED_ALIAS")
        try:
            lookup = await self._wikidata.lookup(candidate.canonical_text)
        except WikidataLookupFailed as exc:
            return self._needs_review_with_raw(
                candidate, "WIKIDATA_UNAVAILABLE", tuple(exc.raw_responses)
            )
        except CollectorError:
            return self._needs_review(candidate, "WIKIDATA_UNAVAILABLE")
        exact = [match for match in lookup.matches if _is_exact(candidate.normalized_text, match)]
        if exact and not lookup.complete:
            return self._needs_review(candidate, "TRUNCATED_WIKIDATA", lookup)
        if len(exact) != 1:
            reason = "AMBIGUOUS_WIKIDATA" if len(exact) > 1 else "NO_EXACT_WIKIDATA_MATCH"
            return self._needs_review(candidate, reason, lookup)
        match = exact[0]
        metadata_classification = classify_metadata(match.instance_of, match.description)
        if metadata_classification.reason.startswith("CONFLICTING_RULES_NEEDS_REVIEW"):
            return self._needs_review(candidate, "CONFLICTING_WIKIDATA_METADATA", lookup)
        if linked_entity is not None and linked_entity.wikidata_id != match.entity_id:
            return self._needs_review(candidate, "ENTITY_RELINK_CONFLICT", lookup)
        entity = self._repo.by_wikidata_id(match.entity_id)
        if entity is None:
            entity = self._repo.create_entity(
                canonical_name=match.label,
                normalized_name=normalize_text(match.label),
                wikidata_id=match.entity_id,
                entity_type=match.instance_of[0] if match.instance_of else None,
                entity_types=match.instance_of,
                description=match.description,
            )
        else:
            entity.entity_type = match.instance_of[0] if match.instance_of else None
            entity.entity_types = list(match.instance_of)
            entity.description = match.description
        self._repo.add_alias(entity.id, match.label, source="WIKIDATA_LABEL", approved=False)
        for alias in match.aliases:
            self._repo.add_alias(entity.id, alias, source="WIKIDATA_ALIAS", approved=False)
        result = self._resolve_to(candidate, entity.id, "EXACT_WIKIDATA")
        return ResolutionResult(
            result.entity_id,
            result.status,
            result.reason,
            tuple(lookup.raw_responses),
        )

    def _resolve_to(
        self, candidate: TrendCandidate, entity_id: int, reason: str
    ) -> ResolutionResult:
        if not self._repo.link_candidate(entity_id, candidate.id, reason):
            return self._needs_review(candidate, "ENTITY_RELINK_CONFLICT")
        candidate.resolution_status = ResolutionStatus.RESOLVED
        candidate.status = CandidateStatus.ACTIVE
        self._session.flush()
        return ResolutionResult(entity_id, ResolutionStatus.RESOLVED, reason)

    def _needs_review(
        self, candidate: TrendCandidate, reason: str, lookup: WikidataLookup | None = None
    ) -> ResolutionResult:
        candidate.resolution_status = ResolutionStatus.NEEDS_REVIEW
        self._session.flush()
        return ResolutionResult(
            None,
            ResolutionStatus.NEEDS_REVIEW,
            reason,
            tuple(lookup.raw_responses) if lookup else (),
        )

    def _needs_review_with_raw(
        self,
        candidate: TrendCandidate,
        reason: str,
        raw_responses: tuple[WikidataRawResponse, ...],
    ) -> ResolutionResult:
        candidate.resolution_status = ResolutionStatus.NEEDS_REVIEW
        self._session.flush()
        return ResolutionResult(None, ResolutionStatus.NEEDS_REVIEW, reason, raw_responses)


def _is_exact(normalized_candidate: str, match) -> bool:
    names = {normalize_text(match.label), *(normalize_text(alias) for alias in match.aliases)}
    return normalized_candidate in names


def validate_live_cutoff(as_of: datetime, now: datetime) -> None:
    if as_of.tzinfo is None or as_of.utcoffset() is None or as_of.utcoffset() != timedelta(0):
        raise ValueError("as_of must be aware UTC")
    if as_of < now - timedelta(minutes=5):
        raise ValueError(
            "historical entity projection is required when as_of is older than five minutes"
        )
