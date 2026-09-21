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


def test_0008_quarantines_legacy_publishable_claim_without_snapshot_provenance() -> None:
    assert TEST_DATABASE_URL is not None
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "0005")
    engine = create_engine(TEST_DATABASE_URL)
    now = datetime(2026, 9, 21, tzinfo=UTC)
    with engine.begin() as connection:
        entity_id = connection.execute(
            text(
                """
                INSERT INTO trend_entities
                    (canonical_name, normalized_name, entity_type, description, wikidata_id,
                     resolution_status, entity_types, category, review_status, version,
                     created_at, updated_at)
                VALUES
                    ('legacy topic', 'legacy topic', NULL, 'mutable description', 'Q_LEGACY_AI',
                     'RESOLVED', CAST('[]' AS JSON), NULL, 'PENDING', 1, :now, :now)
                RETURNING id
                """
            ),
            {"now": now},
        ).scalar_one()
        evidence_id = connection.execute(
            text(
                """
                INSERT INTO evidence
                    (entity_id, observation_id, source, kind, fact, source_url,
                     observed_at, created_at)
                VALUES
                    (:entity_id, NULL, 'WIKIDATA', 'WIKIDATA_ENTITY',
                     CAST(:fact AS JSON), 'https://www.wikidata.org/wiki/Q_LEGACY_AI',
                     :now, :now)
                RETURNING id
                """
            ),
            {
                "entity_id": entity_id,
                "fact": (
                    '{"wikidata_id":"Q_LEGACY_AI","canonical_name":"legacy topic",'
                    '"description":"legacy description","entity_types":[]}'
                ),
                "now": now,
            },
        ).scalar_one()
        claim_id = connection.execute(
            text(
                """
                INSERT INTO claims
                    (entity_id, kind, text, status, reason, publishable,
                     prompt_version, evidence_set_hash, created_at)
                VALUES
                    (:entity_id, 'WHAT', 'legacy topic: legacy description', 'SUPPORTED',
                     'legacy unchecked', true, 'prompt-v1', :digest, :now)
                RETURNING id
                """
            ),
            {"entity_id": entity_id, "digest": "a" * 64, "now": now},
        ).scalar_one()
        connection.execute(
            text(
                """
                INSERT INTO claim_evidence (claim_id, evidence_id)
                VALUES (:claim_id, :evidence_id)
                """
            ),
            {"claim_id": claim_id, "evidence_id": evidence_id},
        )
    engine.dispose()

    command.upgrade(config, "0007")
    cache_engine = create_engine(TEST_DATABASE_URL)
    with cache_engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO summary_cache
                    (entity_id, prompt_version, evidence_set_hash, claims_count)
                VALUES (:entity_id, 'prompt-v1', :digest, 1)
                """
            ),
            {"entity_id": entity_id, "digest": "a" * 64},
        )
    cache_engine.dispose()

    command.upgrade(config, "head")

    verification = create_engine(TEST_DATABASE_URL)
    with verification.connect() as connection:
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "0009"
        claim = connection.execute(
            text(
                """
                SELECT status, publishable, reason
                FROM claims
                WHERE id = :claim_id
                """
            ),
            {"claim_id": claim_id},
        ).one()
        assert claim.status == "UNSUPPORTED"
        assert claim.publishable is False
        assert claim.reason == "LEGACY_PROVENANCE_UNVERIFIED"
        evidence = connection.execute(
            text(
                """
                SELECT resolution_attempt_id, raw_fetch_id
                FROM evidence
                WHERE id = :evidence_id
                """
            ),
            {"evidence_id": evidence_id},
        ).one()
        assert evidence.resolution_attempt_id is None
        assert evidence.raw_fetch_id is None
        assert connection.execute(
            text("SELECT count(*) FROM claim_snapshots WHERE claim_id = :claim_id"),
            {"claim_id": claim_id},
        ).scalar_one() == 0
        assert connection.execute(
            text(
                """
                SELECT count(*)
                FROM summary_cache
                WHERE entity_id = :entity_id
                  AND prompt_version = 'prompt-v1'
                  AND evidence_set_hash = :digest
                """
            ),
            {"entity_id": entity_id, "digest": "a" * 64},
        ).scalar_one() == 0
    verification.dispose()

    command.downgrade(config, "0007")
    command.upgrade(config, "head")
    after_reupgrade = create_engine(TEST_DATABASE_URL)
    with after_reupgrade.connect() as connection:
        claim = connection.execute(
            text("SELECT status, publishable, reason FROM claims WHERE id = :claim_id"),
            {"claim_id": claim_id},
        ).one()
        assert claim.status == "UNSUPPORTED"
        assert claim.publishable is False
        assert claim.reason == "LEGACY_PROVENANCE_UNVERIFIED"
    after_reupgrade.dispose()
