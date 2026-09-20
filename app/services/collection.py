from __future__ import annotations

import base64
import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.collectors.base import CollectionBatch, Collector, CollectorError
from app.models.enums import RunStatus
from app.models.tables import CollectionRun, RawFetch, RawPayload, SourceObservation
from app.repositories.collection import CollectionRepository


@dataclass(frozen=True)
class PersistResult:
    run_id: int
    payload_id: int
    inserted_observations: int


class CollectionService:
    def __init__(self, session: Session, *, now: Callable[[], datetime] | None = None) -> None:
        self._session = session
        self._repo = CollectionRepository(session)
        self._now = now or (lambda: datetime.now(UTC))

    async def run(self, collector: Collector, *, as_of: datetime, run_key: str) -> PersistResult:
        started_at = self._now().astimezone(UTC)
        try:
            batch = await collector.collect(as_of)
        except CollectorError as exc:
            self._session.rollback()
            self._record_failure(
                collector.source,
                run_key,
                started_at=started_at,
                completed_at=self._now().astimezone(UTC),
                error_code=exc.code,
            )
            self._session.commit()
            raise
        return self.persist(
            batch,
            run_key=run_key,
            started_at=started_at,
            completed_at=self._now().astimezone(UTC),
        )

    def persist(
        self,
        batch: CollectionBatch,
        *,
        run_key: str,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> PersistResult:
        run = self._repo.find_run(run_key)
        if run is None:
            run = self._repo.create_with_conflict_recovery(
                lambda: CollectionRun(
                    run_key=run_key,
                    source=batch.source,
                    started_at=started_at or batch.collected_at,
                    status=RunStatus.RUNNING,
                ),
                lambda: self._repo.find_run(run_key),
            )
            assert isinstance(run, CollectionRun)
        if run.source != batch.source:
            raise ValueError("collection run key cannot be reused across sources")

        payload_hash = hashlib.sha256(batch.raw_bytes).hexdigest()
        payload = self._repo.find_payload(batch.source, payload_hash)
        source_timestamp = max((item.source_timestamp for item in batch.items), default=None)
        if payload is None:
            payload = self._repo.create_with_conflict_recovery(
                lambda: RawPayload(
                    source=batch.source,
                    payload_hash=payload_hash,
                    raw_payload={
                        "content_encoding": "base64",
                        "content_type": "application/octet-stream",
                        "data": base64.b64encode(batch.raw_bytes).decode("ascii"),
                    },
                    collected_at=batch.collected_at,
                    source_timestamp=source_timestamp,
                    collector_version=batch.collector_version,
                    parser_version=batch.parser_version,
                ),
                lambda: self._repo.find_payload(batch.source, payload_hash),
            )
            assert isinstance(payload, RawPayload)

        fetch = self._repo.find_fetch(run.id)
        if fetch is None:
            fetch = self._repo.create_with_conflict_recovery(
                lambda: RawFetch(
                    run_id=run.id,
                    raw_payload_id=payload.id,
                    request_url=batch.request_url,
                    collected_at=batch.collected_at,
                    source_timestamp=source_timestamp,
                    collector_version=batch.collector_version,
                    parser_version=batch.parser_version,
                ),
                lambda: self._repo.find_fetch(run.id),
            )
            assert isinstance(fetch, RawFetch)
        if fetch.raw_payload_id != payload.id:
            raise ValueError("collection run key cannot be reused for a different payload")

        existing = self._repo.existing_source_item_ids(run.id)
        inserted = 0
        for item in batch.items:
            if item.source_item_id in existing:
                continue
            self._session.add(
                SourceObservation(
                    run_id=run.id,
                    raw_payload_id=payload.id,
                    source=batch.source,
                    source_item_id=item.source_item_id,
                    canonical_text=item.canonical_text,
                    source_timestamp=item.source_timestamp,
                    observed_at=item.observed_at,
                    source_url=item.source_url,
                    metrics=item.metrics,
                )
            )
            existing.add(item.source_item_id)
            inserted += 1
        run.status = RunStatus.SUCCEEDED
        run.completed_at = completed_at or batch.collected_at
        run.error_code = None
        self._session.flush()
        return PersistResult(run_id=run.id, payload_id=payload.id, inserted_observations=inserted)

    def _record_failure(
        self,
        source,
        run_key: str,
        *,
        started_at: datetime,
        completed_at: datetime,
        error_code: str,
    ) -> None:
        run = self._repo.find_run(run_key)
        if run is None:
            run = self._repo.create_with_conflict_recovery(
                lambda: CollectionRun(
                    run_key=run_key,
                    source=source,
                    started_at=started_at,
                    status=RunStatus.FAILED,
                ),
                lambda: self._repo.find_run(run_key),
            )
            assert isinstance(run, CollectionRun)
        elif run.source != source:
            raise ValueError("collection run key cannot be reused across sources")
        if run.status == RunStatus.SUCCEEDED:
            return
        run.status = RunStatus.FAILED
        run.completed_at = completed_at
        run.error_code = error_code
        self._session.flush()
