from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.collectors.base import CollectionBatch, Collector, CollectorError
from app.models.enums import RunStatus
from app.models.tables import CollectionRun, RawPayload, SourceObservation
from app.repositories.collection import CollectionRepository


@dataclass(frozen=True)
class PersistResult:
    run_id: int
    payload_id: int
    inserted_observations: int


class CollectionService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = CollectionRepository(session)

    async def run(self, collector: Collector, *, as_of: datetime, run_key: str) -> PersistResult:
        try:
            batch = await collector.collect(as_of)
        except CollectorError as exc:
            self._record_failure(collector.source, run_key, as_of, exc.code)
            raise
        return self.persist(batch, run_key=run_key)

    def persist(self, batch: CollectionBatch, *, run_key: str) -> PersistResult:
        run = self._repo.find_run(run_key)
        if run is None:
            run = CollectionRun(
                run_key=run_key,
                source=batch.source,
                started_at=batch.collected_at,
                status=RunStatus.RUNNING,
            )
            self._session.add(run)
            self._session.flush()
        elif run.source != batch.source:
            raise ValueError("collection run key cannot be reused across sources")

        payload_hash = hashlib.sha256(batch.raw_bytes).hexdigest()
        payload = self._repo.find_payload(batch.source, payload_hash)
        if payload is None:
            source_timestamp = max(
                (item.source_timestamp for item in batch.items), default=batch.collected_at
            )
            payload = RawPayload(
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
            )
            self._session.add(payload)
            self._session.flush()

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
        run.completed_at = batch.collected_at
        run.error_code = None
        self._session.flush()
        return PersistResult(run_id=run.id, payload_id=payload.id, inserted_observations=inserted)

    def _record_failure(self, source, run_key: str, as_of: datetime, error_code: str) -> None:
        run = self._repo.find_run(run_key)
        if run is None:
            run = CollectionRun(
                run_key=run_key,
                source=source,
                started_at=as_of,
                status=RunStatus.FAILED,
            )
            self._session.add(run)
        run.status = RunStatus.FAILED
        run.completed_at = as_of
        run.error_code = error_code
        self._session.flush()
