from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.collectors.wikidata import WikidataLookup, WikidataMatch
from app.models.enums import CandidateStatus, ResolutionStatus, Source
from app.models.tables import EntityAlias, EntityCandidate, TrendCandidate, TrendEntity
from app.pipeline.entity import EntityResolver
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


def test_concurrent_resolvers_recover_alias_race_and_keep_links_consistent() -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL)
    as_of = datetime.now(UTC)
    with Session(engine) as session:
        entity = EntityRepository(session).create_entity(
            canonical_name="race target",
            normalized_name="race target",
            wikidata_id="Q_PHASE3_ALIAS_RACE",
            entity_type=None,
        )
        candidates = [
            TrendCandidate(
                source=source,
                canonical_text="race alias",
                normalized_text="race alias",
                first_seen_at=as_of,
                last_seen_at=as_of,
                status=CandidateStatus.NEW,
                resolution_status=ResolutionStatus.NEEDS_REVIEW,
                normalizer_version="normalizer-v1",
                generation=1,
            )
            for source in (Source.GOOGLE_TRENDS, Source.WIKIMEDIA)
        ]
        session.add_all(candidates)
        session.commit()
        entity_id = entity.id
        candidate_ids = [candidate.id for candidate in candidates]

    barrier = Barrier(2)

    class ConcurrentWikidata:
        async def lookup(self, _query: str) -> WikidataLookup:
            barrier.wait(timeout=10)
            return WikidataLookup(
                matches=[
                    WikidataMatch(
                        "Q_PHASE3_ALIAS_RACE",
                        "race alias",
                        ("shared alias",),
                        None,
                        (),
                    )
                ],
                raw_responses=[],
            )

    def resolve(candidate_id: int) -> int | None:
        with Session(engine) as session:
            candidate = session.get(TrendCandidate, candidate_id)
            assert candidate is not None
            result = asyncio.run(
                EntityResolver(
                    session, ConcurrentWikidata(), now=lambda: as_of
                ).resolve(candidate, as_of)
            )
            session.commit()
            return result.entity_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        resolved_ids = list(executor.map(resolve, candidate_ids))

    assert resolved_ids == [entity_id, entity_id]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(EntityAlias)) == 2
        assert session.scalar(select(func.count()).select_from(EntityCandidate)) == 2
    engine.dispose()
