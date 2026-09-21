from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import DataMode, RunKind, RunStatus
from app.models.tables import (
    Claim,
    ClaimEvidence,
    ClaimSnapshot,
    Evidence,
    PipelineRun,
    ProductTrendCard,
    TrendEntity,
    TrendSnapshot,
)


class ProductCardService:
    """Build the user-facing projection without modifying replayable pipeline rows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def sync_live(self, as_of: datetime) -> int:
        rows = self._session.execute(
            select(TrendSnapshot, TrendEntity, PipelineRun)
            .join(TrendEntity, TrendEntity.id == TrendSnapshot.entity_id)
            .join(PipelineRun, PipelineRun.id == TrendSnapshot.pipeline_run_id)
            .where(
                TrendSnapshot.as_of == as_of,
                PipelineRun.kind == RunKind.LIVE,
                PipelineRun.status == RunStatus.SUCCEEDED,
            )
        ).all()
        synced = 0
        for snapshot, entity, run in rows:
            claims = list(
                self._session.scalars(
                    select(Claim)
                    .join(ClaimSnapshot, ClaimSnapshot.claim_id == Claim.id)
                    .where(
                        ClaimSnapshot.snapshot_id == snapshot.id,
                        Claim.publishable.is_(True),
                    )
                    .order_by(Claim.id)
                )
            )
            by_kind = {claim.kind: claim for claim in claims}
            if "WHAT" not in by_kind or "INTEREST" not in by_kind or entity.category is None:
                continue
            claim_ids = [claim.id for claim in claims]
            evidence_rows = list(
                self._session.scalars(
                    select(Evidence)
                    .join(ClaimEvidence, ClaimEvidence.evidence_id == Evidence.id)
                    .where(ClaimEvidence.claim_id.in_(claim_ids))
                    .order_by(Evidence.observed_at.desc(), Evidence.id)
                ).unique()
            )
            sources = []
            seen: set[tuple[str, str, datetime]] = set()
            for evidence in evidence_rows:
                key = (evidence.source.value, evidence.source_url, evidence.observed_at)
                if key in seen:
                    continue
                seen.add(key)
                sources.append(
                    {
                        "source": evidence.source.value,
                        "url": evidence.source_url,
                        "observedAt": evidence.observed_at.isoformat(),
                    }
                )
            existing = self._session.scalar(
                select(ProductTrendCard).where(ProductTrendCard.snapshot_id == snapshot.id)
            )
            values = {
                "entity_id": entity.id,
                "pipeline_run_id": run.id,
                "title": entity.canonical_name,
                "category": entity.category,
                "lifecycle": snapshot.lifecycle,
                "what_text": by_kind["WHAT"].text,
                "interest_text": by_kind["INTEREST"].text,
                "cause_text": by_kind.get("CAUSE").text if by_kind.get("CAUSE") else None,
                "sources": sources,
                "first_seen_at": snapshot.system_detected_at,
                "observed_at": snapshot.as_of,
                "trend_score": snapshot.total_score,
                "auto_pipeline_result": True,
            }
            if existing is None:
                self._session.add(
                    ProductTrendCard(
                        public_id=str(uuid4()),
                        data_mode=DataMode.LIVE,
                        snapshot_id=snapshot.id,
                        suppressed=False,
                        **values,
                    )
                )
            else:
                for name, value in values.items():
                    setattr(existing, name, value)
            synced += 1
        self._session.flush()
        return synced
