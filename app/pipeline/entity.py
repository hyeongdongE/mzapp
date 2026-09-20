from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

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
    def __init__(self, session: Session, wikidata: WikidataClient) -> None:
        self._session = session
        self._wikidata = wikidata
        self._repo = EntityRepository(session)

    async def resolve(self, candidate: TrendCandidate, _as_of: datetime) -> ResolutionResult:
        if candidate.status in {CandidateStatus.REJECTED, CandidateStatus.MERGED}:
            return self._needs_review(candidate, "INACTIVE_CANDIDATE")
        stored = self._repo.entities_by_alias(candidate.normalized_text)
        if len(stored) == 1:
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
        self._repo.link_candidate(entity_id, candidate.id, reason)
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
