from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import Source
from app.models.tables import CollectionRun, RawPayload, SourceObservation


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

    def existing_source_item_ids(self, run_id: int) -> set[str]:
        return set(
            self.session.scalars(
                select(SourceObservation.source_item_id).where(SourceObservation.run_id == run_id)
            )
        )
