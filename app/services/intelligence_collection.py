from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.base import Collector, CollectorError, IncompleteCoverage
from app.intelligence.normalization import normalize_source_item
from app.models.enums import Source
from app.models.tables import RawItem, SourceHealth
from app.services.collection import CollectionService


@dataclass(frozen=True)
class IntelligencePersistResult:
    run_id: int
    fetch_id: int
    inserted_raw_items: int


class IntelligenceCollectionService:
    def __init__(
        self, session: Session, *, now: Callable[[], datetime] | None = None
    ) -> None:
        self._session = session
        self._now = now or (lambda: datetime.now(UTC))
        self._provenance = CollectionService(session, now=self._now)

    async def run(
        self, collector: Collector, *, as_of: datetime, run_key: str
    ) -> IntelligencePersistResult:
        completed = self._provenance.completed_result(collector.source, run_key)
        if completed is not None:
            return IntelligencePersistResult(
                run_id=completed.run_id,
                fetch_id=completed.fetch_id,
                inserted_raw_items=0,
            )
        started_at = self._now().astimezone(UTC)
        collector_key = str(getattr(collector, "collection_key", "default"))
        try:
            batch = await collector.collect(as_of)
            if not batch.coverage_complete:
                raise IncompleteCoverage("collector coverage is incomplete")
        except CollectorError as exc:
            completed_at = self._now().astimezone(UTC)
            self._provenance.record_failure(
                collector.source,
                run_key,
                started_at=started_at,
                completed_at=completed_at,
                error_code=exc.code,
            )
            self._record_failure(collector.source, collector_key, completed_at, exc.code)
            self._session.flush()
            raise
        persisted = self._provenance.persist(
            batch,
            run_key=run_key,
            started_at=started_at,
            completed_at=self._now().astimezone(UTC),
        )
        inserted = self._persist_raw_items(
            batch.source, batch.items, persisted.fetch_id, normalizer_version="it-normalizer-v1"
        )
        self._record_success(
            batch.source,
            collector_key,
            self._now().astimezone(UTC),
            batch.collected_at,
        )
        self._session.flush()
        return IntelligencePersistResult(
            run_id=persisted.run_id,
            fetch_id=persisted.fetch_id,
            inserted_raw_items=inserted,
        )

    def _persist_raw_items(
        self, source: Source, items, raw_fetch_id: int, *, normalizer_version: str
    ) -> int:
        inserted = 0
        for source_item in items:
            normalized = normalize_source_item(source, source_item, raw_fetch_id=raw_fetch_id)
            exists = self._session.scalar(
                select(RawItem.id).where(
                    RawItem.source == source,
                    RawItem.external_id == normalized.external_id,
                    RawItem.normalizer_version == normalizer_version,
                )
            )
            if exists is not None:
                continue
            values = dict(normalized.__dict__)
            metadata = values.pop("metadata")
            self._session.add(
                RawItem(
                    **values,
                    item_metadata=metadata,
                    normalizer_version=normalizer_version,
                )
            )
            inserted += 1
        return inserted

    def _health(self, source: Source, collector_key: str) -> SourceHealth:
        health = self._session.get(SourceHealth, (source, collector_key))
        if health is None:
            health = SourceHealth(
                source=source,
                collector_key=collector_key,
                consecutive_failures=0,
                freshness_state="UNKNOWN",
            )
            self._session.add(health)
        return health

    def _record_success(
        self, source: Source, collector_key: str, at: datetime, covered_through: datetime
    ) -> None:
        health = self._health(source, collector_key)
        health.last_attempt_at = at
        health.last_success_at = at
        health.consecutive_failures = 0
        health.last_error_code = None
        health.freshness_state = "FRESH"
        health.covered_through = covered_through.astimezone(UTC)

    def _record_failure(
        self, source: Source, collector_key: str, at: datetime, error_code: str
    ) -> None:
        health = self._health(source, collector_key)
        health.last_attempt_at = at
        health.last_failure_at = at
        health.consecutive_failures += 1
        health.last_error_code = error_code
        health.freshness_state = "FAILED"
