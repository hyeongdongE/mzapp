from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command
from app.config.settings import get_settings

TEST_DATABASE_URL = os.getenv("TEST_MIGRATION_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="TEST_MIGRATION_DATABASE_URL is required for migration verification",
)


def test_0005_fails_actionably_without_discarding_ambiguous_legacy_links() -> None:
    assert TEST_DATABASE_URL is not None
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "0004")
    engine = create_engine(TEST_DATABASE_URL)
    now = datetime(2026, 9, 21, tzinfo=UTC)
    with engine.begin() as connection:
        entity_ids = []
        for index in (1, 2):
            entity_ids.append(
                connection.execute(
                    text(
                        """
                        INSERT INTO trend_entities
                            (canonical_name, normalized_name, entity_type, description, wikidata_id,
                             resolution_status, entity_types, category, review_status, version,
                             created_at, updated_at)
                        VALUES
                            (:name, :name, NULL, NULL, :qid, 'RESOLVED', CAST('[]' AS JSON),
                             NULL, 'PENDING', 1, :now, :now)
                        RETURNING id
                        """
                    ),
                    {"name": f"entity {index}", "qid": f"Q_LEGACY_{index}", "now": now},
                ).scalar_one()
            )
        candidate_id = connection.execute(
            text(
                """
                INSERT INTO trend_candidates
                    (source, canonical_text, normalized_text, first_seen_at, last_seen_at,
                     status, resolution_status, normalizer_version)
                VALUES
                    ('GOOGLE_TRENDS', 'legacy', 'legacy', :now, :now,
                     'ACTIVE', 'RESOLVED', 'normalizer-v1')
                RETURNING id
                """
            ),
            {"now": now},
        ).scalar_one()
        for entity_id in entity_ids:
            connection.execute(
                text(
                    """
                    INSERT INTO entity_candidates
                        (entity_id, candidate_id, entity_version, match_reason)
                    VALUES (:entity_id, :candidate_id, 'entity-v1', 'legacy')
                    """
                ),
                {"entity_id": entity_id, "candidate_id": candidate_id},
            )
    engine.dispose()

    with pytest.raises(RuntimeError, match=rf"candidate_id={candidate_id}"):
        command.upgrade(config, "0005")

    verification = create_engine(TEST_DATABASE_URL)
    with verification.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == "0004"
        assert connection.execute(
            text("SELECT count(*) FROM entity_candidates WHERE candidate_id = :candidate_id"),
            {"candidate_id": candidate_id},
        ).scalar_one() == 2
    verification.dispose()
