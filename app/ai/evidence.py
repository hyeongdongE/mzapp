from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
from app.collectors.base import CollectorError
from app.collectors.wikidata import parse_wikidata_entity
from app.models.enums import EvidenceStatus, Source
from app.models.tables import (
    CandidateObservation,
    EntityCandidate,
    EntityResolutionAttempt,
    EntityResolutionAttemptRawFetch,
    Evidence,
    RawFetch,
    RawPayload,
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
        entity_wikidata_id: str | None = None,
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
        contradictory = [
            record
            for record in available_evidence
            if record.entity_id == entity_id
            and _as_utc(record.observed_at) <= cutoff
            and _approved_source_url(record)
            and record.fact.get("contradicts_claim") is True
        ]
        if contradictory:
            return CheckedClaim(
                draft=claim,
                status=EvidenceStatus.CONTRADICTED,
                reason="CONTRADICTING_EVIDENCE",
                publishable=False,
            )
        if any(_as_utc(record.observed_at) > cutoff for record in evidence):
            return self._unsupported(claim, "FUTURE_EVIDENCE")
        if any(not _approved_source_url(record) for record in evidence):
            return self._unsupported(claim, "UNAPPROVED_SOURCE_URL")
        for record in evidence:
            valid, reason = _valid_provenance(
                record,
                entity_name=entity_name,
                entity_wikidata_id=entity_wikidata_id,
                cutoff=cutoff,
            )
            if not valid:
                return self._unsupported(claim, reason)
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
        existing = [
            row
            for row in existing
            if self._has_valid_database_provenance(row, entity, cutoff)
        ]
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
            row = self._persist_evidence(
                row,
                select(Evidence).where(Evidence.observation_id == observation.id),
            )
            existing.append(row)
        self._session.flush()
        if entity.wikidata_id and not any(row.kind == "WIKIDATA_ENTITY" for row in existing):
            provenances = self._session.execute(
                select(EntityResolutionAttempt, RawFetch, RawPayload)
                .join(
                    EntityResolutionAttemptRawFetch,
                    EntityResolutionAttemptRawFetch.attempt_id == EntityResolutionAttempt.id,
                )
                .join(RawFetch, RawFetch.id == EntityResolutionAttemptRawFetch.raw_fetch_id)
                .join(RawPayload, RawPayload.id == RawFetch.raw_payload_id)
                .where(
                    EntityResolutionAttempt.entity_id == entity.id,
                    EntityResolutionAttempt.attempted_at <= cutoff,
                    RawFetch.collected_at <= cutoff,
                    RawPayload.collected_at <= cutoff,
                    RawPayload.source == Source.WIKIDATA,
                )
                .order_by(RawFetch.collected_at.desc(), RawFetch.id.desc())
            ).all()
            parsed_provenance = None
            for attempt, fetch, payload in provenances:
                raw_bytes = _raw_bytes(payload.raw_payload)
                if raw_bytes is None:
                    continue
                try:
                    match = parse_wikidata_entity(raw_bytes, entity.wikidata_id)
                except CollectorError:
                    continue
                if match is not None:
                    parsed_provenance = (attempt, fetch, match)
                    break
            if parsed_provenance is not None:
                attempt, fetch, match = parsed_provenance
                wikidata = Evidence(
                    entity_id=entity.id,
                    observation_id=None,
                    resolution_attempt_id=attempt.id,
                    raw_fetch_id=fetch.id,
                    source=Source.WIKIDATA,
                    kind="WIKIDATA_ENTITY",
                    fact={
                        "wikidata_id": match.entity_id,
                        "canonical_name": match.label,
                        "description": match.description,
                        "entity_types": list(match.instance_of),
                    },
                    source_url=fetch.request_url,
                    observed_at=_as_utc(fetch.collected_at),
                )
                wikidata = self._persist_evidence(
                    wikidata,
                    select(Evidence).where(
                        Evidence.entity_id == entity.id,
                        Evidence.raw_fetch_id == fetch.id,
                        Evidence.kind == "WIKIDATA_ENTITY",
                    ),
                )
                existing.append(wikidata)
                self._session.flush()
        return existing

    def _persist_evidence(self, proposed: Evidence, lookup) -> Evidence:
        try:
            with self._session.begin_nested():
                self._session.add(proposed)
                self._session.flush()
            return proposed
        except IntegrityError:
            existing = self._session.scalar(lookup)
            if existing is None:
                raise
            return existing

    def _has_valid_database_provenance(
        self, row: Evidence, entity: TrendEntity, cutoff: datetime
    ) -> bool:
        if row.kind == "TREND_SIGNAL":
            if row.observation_id is None:
                return False
            observation = self._session.get(SourceObservation, row.observation_id)
            if observation is None:
                return False
            linked = self._session.scalar(
                select(EntityCandidate.id)
                .join(
                    CandidateObservation,
                    CandidateObservation.candidate_id == EntityCandidate.candidate_id,
                )
                .where(
                    EntityCandidate.entity_id == entity.id,
                    CandidateObservation.observation_id == observation.id,
                )
                .limit(1)
            )
            return bool(
                linked is not None
                and observation.source == row.source
                and observation.source != Source.WIKIDATA
                and observation.source_url == row.source_url
                and _as_utc(observation.source_timestamp) <= cutoff
                and _as_utc(observation.observed_at) <= cutoff
                and _as_utc(row.observed_at) == _as_utc(observation.observed_at)
                and row.fact.get("canonical_text") == observation.canonical_text
                and row.fact.get("metrics") == observation.metrics
                and row.fact.get("source_timestamp")
                == _as_utc(observation.source_timestamp).isoformat()
            )
        if row.kind == "WIKIDATA_ENTITY":
            if row.resolution_attempt_id is None or row.raw_fetch_id is None:
                return False
            attempt = self._session.get(EntityResolutionAttempt, row.resolution_attempt_id)
            fetch = self._session.get(RawFetch, row.raw_fetch_id)
            if attempt is None or fetch is None or entity.wikidata_id is None:
                return False
            linked = self._session.scalar(
                select(EntityResolutionAttemptRawFetch.id).where(
                    EntityResolutionAttemptRawFetch.attempt_id == attempt.id,
                    EntityResolutionAttemptRawFetch.raw_fetch_id == fetch.id,
                )
            )
            payload = self._session.get(RawPayload, fetch.raw_payload_id)
            if linked is None or payload is None or payload.source != Source.WIKIDATA:
                return False
            raw_bytes = _raw_bytes(payload.raw_payload)
            if raw_bytes is None:
                return False
            try:
                match = parse_wikidata_entity(raw_bytes, entity.wikidata_id)
            except CollectorError:
                return False
            expected_fact = None
            if match is not None:
                expected_fact = {
                    "wikidata_id": match.entity_id,
                    "canonical_name": match.label,
                    "description": match.description,
                    "entity_types": list(match.instance_of),
                }
            return bool(
                attempt.entity_id == entity.id
                and _as_utc(attempt.attempted_at) <= cutoff
                and _as_utc(fetch.collected_at) <= cutoff
                and _as_utc(payload.collected_at) <= cutoff
                and _as_utc(row.observed_at) == _as_utc(fetch.collected_at)
                and row.source == Source.WIKIDATA
                and row.source_url == fetch.request_url
                and row.fact == expected_fact
            )
        return False


def evidence_record(row: Evidence) -> EvidenceRecord:
    return EvidenceRecord(
        id=row.id,
        entity_id=row.entity_id,
        observation_id=row.observation_id,
        resolution_attempt_id=row.resolution_attempt_id,
        raw_fetch_id=row.raw_fetch_id,
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


def _valid_provenance(
    record: EvidenceRecord,
    *,
    entity_name: str,
    entity_wikidata_id: str | None,
    cutoff: datetime,
) -> tuple[bool, str]:
    if record.kind == "TREND_SIGNAL":
        if (
            record.source not in {Source.GOOGLE_TRENDS, Source.WIKIMEDIA}
            or record.observation_id is None
            or record.resolution_attempt_id is not None
            or record.raw_fetch_id is not None
            or not isinstance(record.fact.get("canonical_text"), str)
            or not isinstance(record.fact.get("metrics"), dict)
        ):
            return False, "INVALID_EVIDENCE_PROVENANCE"
        source_timestamp = record.fact.get("source_timestamp")
        if not isinstance(source_timestamp, str):
            return False, "INVALID_EVIDENCE_PROVENANCE"
        try:
            parsed_timestamp = datetime.fromisoformat(
                source_timestamp.replace("Z", "+00:00")
            )
        except ValueError:
            return False, "INVALID_SOURCE_TIMESTAMP"
        if parsed_timestamp.tzinfo is None:
            return False, "INVALID_SOURCE_TIMESTAMP"
        if _as_utc(parsed_timestamp) > cutoff:
            return False, "FUTURE_SOURCE_TIMESTAMP"
        return True, ""
    if record.kind == "WIKIDATA_ENTITY":
        entity_types = record.fact.get("entity_types")
        if (
            record.source is not Source.WIKIDATA
            or record.observation_id is not None
            or record.resolution_attempt_id is None
            or record.raw_fetch_id is None
            or entity_wikidata_id is None
            or record.fact.get("wikidata_id") != entity_wikidata_id
            or record.fact.get("canonical_name") != entity_name
            or not isinstance(record.fact.get("description"), str)
            or not isinstance(entity_types, list)
            or not all(isinstance(value, str) for value in entity_types)
        ):
            return False, "INVALID_EVIDENCE_PROVENANCE"
        return True, ""
    if record.kind == "CAUSAL_EVENT":
        if (
            record.source not in {Source.GOOGLE_TRENDS, Source.WIKIMEDIA}
            or record.observation_id is None
            or record.resolution_attempt_id is not None
            or record.raw_fetch_id is not None
            or record.fact.get("trusted_parser") is not True
            or not isinstance(record.fact.get("cause"), str)
        ):
            return False, "INVALID_EVIDENCE_PROVENANCE"
        source_timestamp = record.fact.get("source_timestamp")
        if not isinstance(source_timestamp, str):
            return False, "INVALID_EVIDENCE_PROVENANCE"
        try:
            parsed_timestamp = datetime.fromisoformat(
                source_timestamp.replace("Z", "+00:00")
            )
        except ValueError:
            return False, "INVALID_SOURCE_TIMESTAMP"
        if parsed_timestamp.tzinfo is None:
            return False, "INVALID_SOURCE_TIMESTAMP"
        if _as_utc(parsed_timestamp) > cutoff:
            return False, "FUTURE_SOURCE_TIMESTAMP"
        return True, ""
    return False, "INVALID_EVIDENCE_PROVENANCE"


def _raw_bytes(payload: dict) -> bytes | None:
    if payload.get("content_encoding") != "base64":
        return None
    data = payload.get("data")
    if not isinstance(data, str):
        return None
    try:
        return base64.b64decode(data, validate=True)
    except (ValueError, binascii.Error):
        return None


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
