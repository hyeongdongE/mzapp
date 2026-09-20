from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models.tables import TrendEntity
from app.repositories.entities import EntityRepository

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="TEST_DATABASE_URL is required for PostgreSQL concurrency verification",
)


def test_concurrent_wikidata_entity_get_or_create_recovers_unique_conflict() -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL)
    barrier = Barrier(2)

    def create_entity() -> int:
        with Session(engine) as session:
            repo = EntityRepository(session)
            assert repo.by_wikidata_id("Q_PHASE3_CONCURRENCY") is None
            barrier.wait()
            entity = repo.create_entity(
                canonical_name="concurrent entity",
                normalized_name="concurrent entity",
                wikidata_id="Q_PHASE3_CONCURRENCY",
                entity_type=None,
            )
            session.commit()
            return entity.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = list(executor.map(lambda _: create_entity(), range(2)))

    assert len(set(ids)) == 1
    with Session(engine) as session:
        count = session.scalar(
            select(func.count()).select_from(TrendEntity).where(
                TrendEntity.wikidata_id == "Q_PHASE3_CONCURRENCY"
            )
        )
        assert count == 1
    engine.dispose()
