from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.contracts import (
    UNKNOWN_CAUSE_MESSAGE,
    CheckedClaim,
    ClaimDraft,
    ClaimKind,
    EvidenceRecord,
    interest_claim_text,
    what_claim_text,
)
from app.models.enums import EvidenceStatus, Source
from app.models.tables import (
    CandidateObservation,
    EntityCandidate,
    EntityResolutionAttempt,
    EntityResolutionAttemptRawFetch,
    Evidence,
    RawFetch,
    SourceObservation,
    TrendEntity,
)

EVIDENCE_KIND_BY_CLAIM = {
    ClaimKind.WHAT: "WIKIDATA_ENTITY",
    ClaimKind.INTEREST: "TREND_SIGNAL",
    ClaimKind.CAUSE: "CAUSAL_EVENT",
}

APPROVED_SOURCE_HOSTS = {
    Source.GOOGLE_TRENDS: {"trends.google.com"},
    Source.WIKIMEDIA: {"wikimedia.org"},
    Source.WIKIDATA: {"wikidata.org", "www.wikidata.org"},
}


class EvidenceChecker:
    def check(
        self,
        claim: ClaimDraft,
        available_evidence: list[EvidenceRecord],
        *,
        entity_id: int,
        entity_name: str,
        as_of: datetime,
    ) -> CheckedClaim:
        if not claim.evidence_ids:
            return self._unsupported(claim, "EVIDENCE_REQUIRED")
        records = {record.id: record for record in available_evidence}
        selected = [records.get(evidence_id) for evidence_id in claim.evidence_ids]
        if any(record is None for record in selected):
            return self._unsupported(claim, "EVIDENCE_NOT_FOUND")
        evidence = [record for record in selected if record is not None]
        if any(record.entity_id != entity_id for record in evidence):
            return self._unsupported(claim, "ENTITY_MISMATCH")
        cutoff = _as_utc(as_of)
        if any(_as_utc(record.observed_at) > cutoff for record in evidence):
            return self._unsupported(claim, "FUTURE_EVIDENCE")
        if any(not _approved_source_url(record) for record in evidence):
            return self._unsupported(claim, "UNAPPROVED_SOURCE_URL")
        for record in evidence:
            source_timestamp = record.fact.get("source_timestamp")
            if isinstance(source_timestamp, str):
                try:
                    parsed_timestamp = datetime.fromisoformat(
                        source_timestamp.replace("Z", "+00:00")
                    )
                except ValueError:
                    return self._unsupported(claim, "INVALID_SOURCE_TIMESTAMP")
                if _as_utc(parsed_timestamp) > cutoff:
                    return self._unsupported(claim, "FUTURE_SOURCE_TIMESTAMP")
        if any(record.fact.get("contradicts_claim") is True for record in evidence):
            return CheckedClaim(
                draft=claim,
                status=EvidenceStatus.CONTRADICTED,
                reason="CONTRADICTING_EVIDENCE",
                publishable=False,
            )
        if claim.kind is ClaimKind.CAUSE and claim.text == UNKNOWN_CAUSE_MESSAGE:
            if any(record.kind == "CAUSAL_EVENT" for record in available_evidence):
                return self._unsupported(claim, "CAUSAL_EVIDENCE_NOT_SUMMARIZED")
            if not any(record.kind == "TREND_SIGNAL" for record in evidence):
                return self._unsupported(claim, "TREND_SIGNAL_REQUIRED")
            return CheckedClaim(
                draft=claim,
                status=EvidenceStatus.SUPPORTED,
                reason="NO_CAUSAL_EVIDENCE_AVAILABLE",
                publishable=True,
            )
        required_kind = EVIDENCE_KIND_BY_CLAIM[claim.kind]
        if not any(record.kind == required_kind for record in evidence):
            reason = (
                "CAUSAL_EVIDENCE_REQUIRED"
                if claim.kind is ClaimKind.CAUSE
                else f"{required_kind}_REQUIRED"
            )
            return self._unsupported(claim, reason)
        if not _claim_matches_evidence(claim, evidence, entity_name):
            return self._unsupported(claim, "CLAIM_EVIDENCE_MISMATCH")
        return CheckedClaim(
            draft=claim,
            status=EvidenceStatus.SUPPORTED,
            reason="MATCHED_TRUSTED_EVIDENCE",
            publishable=True,
        )

    @staticmethod
    def _unsupported(claim: ClaimDraft, reason: str) -> CheckedClaim:
        return CheckedClaim(
            draft=claim,
            status=EvidenceStatus.UNSUPPORTED,
            reason=reason,
            publishable=False,
        )


class EvidenceBuilder:
    def __init__(self, session: Session) -> None:
        self._session = session

    def build(self, entity: TrendEntity, as_of: datetime) -> list[Evidence]:
        cutoff = _as_utc(as_of)
        existing = list(
            self._session.scalars(
                select(Evidence)
                .where(Evidence.entity_id == entity.id, Evidence.observed_at <= cutoff)
                .order_by(Evidence.id)
            )
        )
        by_observation = {
            row.observation_id: row for row in existing if row.observation_id is not None
        }
        observations = self._session.scalars(
            select(SourceObservation)
            .join(
                CandidateObservation,
                CandidateObservation.observation_id == SourceObservation.id,
            )
            .join(
                EntityCandidate,
                EntityCandidate.candidate_id == CandidateObservation.candidate_id,
            )
            .where(
                EntityCandidate.entity_id == entity.id,
                SourceObservation.source_timestamp <= cutoff,
                SourceObservation.observed_at <= cutoff,
                SourceObservation.source != Source.WIKIDATA,
            )
            .order_by(SourceObservation.source_timestamp, SourceObservation.id)
        )
        for observation in observations:
            if observation.id in by_observation:
                continue
            row = Evidence(
                entity_id=entity.id,
                observation_id=observation.id,
                source=observation.source,
                kind="TREND_SIGNAL",
                fact={
                    "canonical_text": observation.canonical_text,
                    "metrics": observation.metrics,
                    "source_timestamp": _as_utc(observation.source_timestamp).isoformat(),
                },
                source_url=observation.source_url,
                observed_at=_as_utc(observation.observed_at),
            )
            self._session.add(row)
            existing.append(row)
        self._session.flush()
        if entity.wikidata_id and not any(row.kind == "WIKIDATA_ENTITY" for row in existing):
            provenance = self._session.execute(
                select(EntityResolutionAttempt.attempted_at, RawFetch.request_url)
                .join(
                    EntityResolutionAttemptRawFetch,
                    EntityResolutionAttemptRawFetch.attempt_id == EntityResolutionAttempt.id,
                )
                .join(RawFetch, RawFetch.id == EntityResolutionAttemptRawFetch.raw_fetch_id)
                .where(
                    EntityResolutionAttempt.entity_id == entity.id,
                    EntityResolutionAttempt.attempted_at <= cutoff,
                )
                .order_by(EntityResolutionAttempt.attempted_at.desc(), RawFetch.id.desc())
                .limit(1)
            ).first()
            if provenance is not None:
                attempted_at, request_url = provenance
                wikidata = Evidence(
                    entity_id=entity.id,
                    observation_id=None,
                    source=Source.WIKIDATA,
                    kind="WIKIDATA_ENTITY",
                    fact={
                        "wikidata_id": entity.wikidata_id,
                        "canonical_name": entity.canonical_name,
                        "description": entity.description,
                        "entity_types": entity.entity_types,
                    },
                    source_url=request_url,
                    observed_at=_as_utc(attempted_at),
                )
                self._session.add(wikidata)
                existing.append(wikidata)
                self._session.flush()
        return existing


def evidence_record(row: Evidence) -> EvidenceRecord:
    return EvidenceRecord(
        id=row.id,
        entity_id=row.entity_id,
        source=row.source,
        kind=row.kind,
        fact=row.fact,
        source_url=row.source_url,
        observed_at=_as_utc(row.observed_at),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _approved_source_url(record: EvidenceRecord) -> bool:
    parsed = urlsplit(record.source_url)
    return parsed.scheme == "https" and parsed.hostname in APPROVED_SOURCE_HOSTS[record.source]


def _claim_matches_evidence(
    claim: ClaimDraft, evidence: list[EvidenceRecord], entity_name: str
) -> bool:
    if claim.kind is ClaimKind.WHAT:
        return any(
            isinstance(record.fact.get("description"), str)
            and claim.text == what_claim_text(entity_name, record.fact["description"])
            for record in evidence
            if record.kind == "WIKIDATA_ENTITY"
        )
    if claim.kind is ClaimKind.INTEREST:
        sources = {record.source for record in evidence if record.kind == "TREND_SIGNAL"}
        return bool(sources) and claim.text == interest_claim_text(entity_name, sources)
    return any(
        record.fact.get("trusted_parser") is True
        and isinstance(record.fact.get("cause"), str)
        and claim.text == record.fact["cause"]
        for record in evidence
        if record.kind == "CAUSAL_EVENT"
    )
