from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TypeVar

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import RunStatus, Source
from app.models.tables import CollectionRun, RawFetch, RawPayload, SourceObservation

T = TypeVar("T")


class CollectionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_run(self, run_key: str) -> CollectionRun | None:
        return self.session.scalar(select(CollectionRun).where(CollectionRun.run_key == run_key))

    def find_payload(self, source: Source, payload_hash: str) -> RawPayload | None:
        return self.session.scalar(
            select(RawPayload).where(
                RawPayload.source == source, RawPayload.payload_hash == payload_hash
            )
        )

    def create_with_conflict_recovery(
        self, factory: Callable[[], T], lookup: Callable[[], T | None]
    ) -> T:
        try:
            with self.session.begin_nested():
                value = factory()
                self.session.add(value)
                self.session.flush()
            return value
        except IntegrityError:
            value = lookup()
            if value is None:
                raise
            return value

    def find_fetch(self, run_id: int) -> RawFetch | None:
        return self.session.scalar(select(RawFetch).where(RawFetch.run_id == run_id))

    def mark_failed_unless_succeeded(
        self,
        *,
        run_key: str,
        source: Source,
        completed_at: datetime,
        error_code: str,
    ) -> bool:
        result = self.session.execute(
            update(CollectionRun)
            .where(
                CollectionRun.run_key == run_key,
                CollectionRun.source == source,
                CollectionRun.status != RunStatus.SUCCEEDED,
            )
            .values(
                status=RunStatus.FAILED,
                completed_at=completed_at,
                error_code=error_code,
            )
            .execution_options(synchronize_session=False)
        )
        return bool(result.rowcount)

    def existing_source_item_ids(self, run_id: int) -> set[str]:
        return set(
            self.session.scalars(
                select(SourceObservation.source_item_id).where(SourceObservation.run_id == run_id)
            )
        )

    def existing_source_item_ids_for_source(self, source: Source) -> set[str]:
        return set(
            self.session.scalars(
                select(SourceObservation.source_item_id).where(
                    SourceObservation.source == source
                )
            )
        )
