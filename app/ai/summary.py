from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.contracts import (
    UNKNOWN_CAUSE_MESSAGE,
    ClaimDraft,
    ClaimKind,
    EvidenceRecord,
    SummaryContext,
    SummaryProvider,
    SummaryResult,
    interest_claim_text,
    what_claim_text,
)
from app.ai.evidence import EvidenceBuilder, EvidenceChecker, evidence_record
from app.models.enums import ResolutionStatus
from app.models.tables import (
    Claim,
    ClaimEvidence,
    ClaimSnapshot,
    SummaryCache,
    TrendEntity,
    TrendSnapshot,
)


class ProviderDisabled(RuntimeError):
    pass


class EvidenceOnlySummaryProvider:
    async def summarize(self, context: SummaryContext) -> SummaryResult:
        claims: list[ClaimDraft] = []
        wikidata = [row for row in context.evidence if row.kind == "WIKIDATA_ENTITY"]
        wikidata_name = wikidata[0].fact.get("canonical_name") if wikidata else None
        wikidata_description = wikidata[0].fact.get("description") if wikidata else None
        if isinstance(wikidata_name, str) and isinstance(wikidata_description, str):
            claims.append(
                ClaimDraft(
                    kind=ClaimKind.WHAT,
                    text=what_claim_text(wikidata_name, wikidata_description),
                    evidence_ids=[wikidata[0].id],
                )
            )
        signals = [row for row in context.evidence if row.kind == "TREND_SIGNAL"]
        if signals:
            claims.append(
                ClaimDraft(
                    kind=ClaimKind.INTEREST,
                    text=interest_claim_text(
                        context.canonical_name, {row.source for row in signals}
                    ),
                    evidence_ids=[row.id for row in signals],
                )
            )
        causes = [
            row
            for row in context.evidence
            if row.kind == "CAUSAL_EVENT"
            and row.fact.get("trusted_parser") is True
        ]
        if causes and isinstance(causes[0].fact.get("cause"), str):
            claims.append(
                ClaimDraft(
                    kind=ClaimKind.CAUSE,
                    text=causes[0].fact["cause"],
                    evidence_ids=[causes[0].id],
                )
            )
            why = causes[0].fact["cause"]
        else:
            why = UNKNOWN_CAUSE_MESSAGE
            if signals:
                claims.append(
                    ClaimDraft(
                        kind=ClaimKind.CAUSE,
                        text=UNKNOWN_CAUSE_MESSAGE,
                        evidence_ids=[row.id for row in signals],
                    )
                )
        return SummaryResult(claims=claims, why=why, requested_urls=[])


class DisabledLlmSummaryProvider:
    def __init__(
        self,
        *,
        transport: Callable[[SummaryContext], Awaitable[SummaryResult]] | None = None,
    ) -> None:
        self._transport = transport

    async def summarize(self, context: SummaryContext) -> SummaryResult:
        del context
        raise ProviderDisabled("LLM summary provider is disabled")


class SummaryService:
    def __init__(
        self,
        session: Session,
        *,
        provider: SummaryProvider | None = None,
        checker: EvidenceChecker | None = None,
    ) -> None:
        self._session = session
        self._provider = provider or EvidenceOnlySummaryProvider()
        self._checker = checker or EvidenceChecker()
        self._builder = EvidenceBuilder(session)

    async def generate_top(
        self,
        *,
        as_of: datetime,
        top_n: int,
        prompt_version: str,
        score_version: str,
    ) -> list[Claim]:
        if top_n <= 0:
            return []
        ranked = self._session.execute(
            select(TrendSnapshot, TrendEntity)
            .join(TrendEntity, TrendEntity.id == TrendSnapshot.entity_id)
            .where(
                TrendSnapshot.as_of == as_of,
                TrendSnapshot.score_version == score_version,
                TrendEntity.resolution_status == ResolutionStatus.RESOLVED,
            )
            .order_by(TrendSnapshot.total_score.desc(), TrendEntity.id)
            .limit(top_n)
        ).all()
        generated: list[Claim] = []
        for snapshot, entity in ranked:
            evidence_rows = self._builder.build(entity, as_of)
            evidence = [evidence_record(row) for row in evidence_rows]
            if not evidence:
                continue
            evidence_hash = _evidence_set_hash(evidence)
            cached = list(
                self._session.scalars(
                    select(Claim)
                    .where(
                        Claim.entity_id == entity.id,
                        Claim.evidence_set_hash == evidence_hash,
                        Claim.prompt_version == prompt_version,
                    )
                    .order_by(Claim.id)
                )
            )
            cache_row = self._session.scalar(
                select(SummaryCache).where(
                    SummaryCache.entity_id == entity.id,
                    SummaryCache.evidence_set_hash == evidence_hash,
                    SummaryCache.prompt_version == prompt_version,
                )
            )
            if cache_row is not None:
                if cache_row.claims_count != len(cached):
                    raise RuntimeError("summary cache claim count mismatch")
                for claim in cached:
                    self._link_snapshot(claim.id, snapshot.id)
                generated.extend(cached)
                continue
            if cached:
                self._persist_cache(
                    entity.id, prompt_version, evidence_hash, len(cached)
                )
                for claim in cached:
                    self._link_snapshot(claim.id, snapshot.id)
                generated.extend(cached)
                continue
            summary = await self._provider.summarize(
                SummaryContext(
                    entity_id=entity.id,
                    canonical_name=entity.canonical_name,
                    description=entity.description,
                    as_of=as_of,
                    evidence=evidence,
                )
            )
            evidence_by_id = {row.id: row for row in evidence_rows}
            for draft in summary.claims:
                checked = self._checker.check(
                    draft,
                    evidence,
                    entity_id=entity.id,
                    entity_name=entity.canonical_name,
                    entity_wikidata_id=entity.wikidata_id,
                    as_of=as_of,
                )
                claim, created = self._persist_claim(
                    Claim(
                        entity_id=entity.id,
                        kind=draft.kind.value,
                        text=draft.text,
                        status=checked.status,
                        reason=checked.reason,
                        publishable=checked.publishable,
                        prompt_version=prompt_version,
                        evidence_set_hash=evidence_hash,
                    )
                )
                if created:
                    self._session.add_all(
                        ClaimEvidence(claim_id=claim.id, evidence_id=evidence_id)
                        for evidence_id in dict.fromkeys(draft.evidence_ids)
                        if evidence_id in evidence_by_id
                    )
                    self._session.flush()
                self._link_snapshot(claim.id, snapshot.id)
                generated.append(claim)
            self._persist_cache(
                entity.id,
                prompt_version,
                evidence_hash,
                len(summary.claims),
            )
        self._session.flush()
        return generated

    def _persist_claim(self, proposed: Claim) -> tuple[Claim, bool]:
        try:
            with self._session.begin_nested():
                self._session.add(proposed)
                self._session.flush()
            return proposed, True
        except IntegrityError:
            existing = self._session.scalar(
                select(Claim).where(
                    Claim.entity_id == proposed.entity_id,
                    Claim.prompt_version == proposed.prompt_version,
                    Claim.evidence_set_hash == proposed.evidence_set_hash,
                    Claim.kind == proposed.kind,
                )
            )
            if existing is None:
                raise
            return existing, False

    def _link_snapshot(self, claim_id: int, snapshot_id: int) -> None:
        existing = self._session.scalar(
            select(ClaimSnapshot).where(
                ClaimSnapshot.claim_id == claim_id,
                ClaimSnapshot.snapshot_id == snapshot_id,
            )
        )
        if existing is not None:
            return
        try:
            with self._session.begin_nested():
                self._session.add(
                    ClaimSnapshot(claim_id=claim_id, snapshot_id=snapshot_id)
                )
                self._session.flush()
        except IntegrityError:
            existing = self._session.scalar(
                select(ClaimSnapshot).where(
                    ClaimSnapshot.claim_id == claim_id,
                    ClaimSnapshot.snapshot_id == snapshot_id,
                )
            )
            if existing is None:
                raise

    def _persist_cache(
        self,
        entity_id: int,
        prompt_version: str,
        evidence_set_hash: str,
        claims_count: int,
    ) -> SummaryCache:
        proposed = SummaryCache(
            entity_id=entity_id,
            prompt_version=prompt_version,
            evidence_set_hash=evidence_set_hash,
            claims_count=claims_count,
        )
        try:
            with self._session.begin_nested():
                self._session.add(proposed)
                self._session.flush()
            return proposed
        except IntegrityError as exc:
            existing = self._session.scalar(
                select(SummaryCache).where(
                    SummaryCache.entity_id == entity_id,
                    SummaryCache.prompt_version == prompt_version,
                    SummaryCache.evidence_set_hash == evidence_set_hash,
                )
            )
            if existing is None:
                raise
            if existing.claims_count != claims_count:
                raise RuntimeError("concurrent summary cache result mismatch") from exc
            return existing


def _evidence_set_hash(evidence: list[EvidenceRecord]) -> str:
    payload = [
        {
            "id": row.id,
            "entity_id": row.entity_id,
            "source": row.source.value,
            "kind": row.kind,
            "fact": row.fact,
            "source_url": row.source_url,
            "observed_at": row.observed_at.isoformat(),
        }
        for row in sorted(evidence, key=lambda item: item.id)
    ]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
