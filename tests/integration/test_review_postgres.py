from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models.enums import (
    CandidateStatus,
    ResolutionStatus,
    ReviewAction,
    ReviewStatus,
    Source,
)
from app.models.tables import EntityAlias, EntityCandidate, TrendCandidate, TrendEntity
from app.services.reviews import ReviewCommand, ReviewService

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="TEST_DATABASE_URL is required for PostgreSQL review verification",
)
NOW = datetime(2026, 9, 21, 3, tzinfo=UTC)


def test_postgres_merge_is_atomic_and_deduplicates_aliases() -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL)
    with Session(engine) as session:
        source = TrendEntity(
            canonical_name="postgres review source",
            normalized_name="postgres review source",
            wikidata_id="Q_REVIEW_PG_SOURCE",
            resolution_status=ResolutionStatus.RESOLVED,
            entity_types=[],
            review_status=ReviewStatus.PENDING,
            version=1,
        )
        target = TrendEntity(
            canonical_name="postgres review target",
            normalized_name="postgres review target",
            wikidata_id="Q_REVIEW_PG_TARGET",
            resolution_status=ResolutionStatus.RESOLVED,
            entity_types=[],
            review_status=ReviewStatus.PENDING,
            version=2,
        )
        candidate = TrendCandidate(
            source=Source.GOOGLE_TRENDS,
            canonical_text="postgres review candidate",
            normalized_text="postgres review candidate",
            first_seen_at=NOW,
            last_seen_at=NOW,
            status=CandidateStatus.ACTIVE,
            resolution_status=ResolutionStatus.RESOLVED,
            normalizer_version="normalizer-v1",
            generation=1,
        )
        session.add_all([source, target, candidate])
        session.flush()
        session.add_all(
            [
                EntityCandidate(
                    entity_id=source.id,
                    candidate_id=candidate.id,
                    entity_version="entity-v1",
                    match_reason="TEST_FIXTURE",
                ),
                EntityAlias(
                    entity_id=source.id,
                    alias="postgres shared alias",
                    normalized_alias="postgres shared alias",
                    language="en",
                    source="WIKIDATA_ALIAS",
                    approved=True,
                ),
                EntityAlias(
                    entity_id=target.id,
                    alias="postgres shared alias",
                    normalized_alias="postgres shared alias",
                    language="en",
                    source="WIKIDATA_ALIAS",
                    approved=True,
                ),
            ]
        )
        session.flush()

        review = ReviewService(session).apply(
            ReviewCommand(
                entity_id=source.id,
                action=ReviewAction.MERGE,
                expected_version=1,
                actor="postgres-test",
                target_entity_id=target.id,
            ),
            NOW,
        )
        session.flush()

        assert review.action is ReviewAction.MERGE
        assert session.scalar(
            select(EntityCandidate.entity_id).where(
                EntityCandidate.candidate_id == candidate.id
            )
        ) == target.id
        assert session.scalar(
            select(func.count())
            .select_from(EntityAlias)
            .where(EntityAlias.entity_id == target.id)
        ) == 1
        assert source.review_status is ReviewStatus.REJECTED
        assert target.version == 3
        session.rollback()
    engine.dispose()
