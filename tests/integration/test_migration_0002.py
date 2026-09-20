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


def test_0002_selects_latest_payload_for_legacy_multi_payload_run() -> None:
    assert TEST_DATABASE_URL is not None
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "0001")
    engine = create_engine(TEST_DATABASE_URL)
    first_seen = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
    second_seen = datetime(2026, 9, 20, 11, 0, tzinfo=UTC)
    with engine.begin() as connection:
        run_id = connection.execute(
            text(
                """
                INSERT INTO collection_runs
                    (run_key, source, started_at, completed_at, status, error_code)
                VALUES
                    ('legacy:multi', 'GOOGLE_TRENDS', :started, :completed, 'SUCCEEDED', NULL)
                RETURNING id
                """
            ),
            {"started": first_seen, "completed": second_seen},
        ).scalar_one()
        payload_ids = []
        for index, collected_at in enumerate((first_seen, second_seen), start=1):
            payload_ids.append(
                connection.execute(
                    text(
                        """
                        INSERT INTO raw_payloads
                            (source, payload_hash, raw_payload, collected_at, source_timestamp,
                             collector_version, parser_version)
                        VALUES
                            ('GOOGLE_TRENDS', :hash, CAST(:payload AS JSON), :collected,
                             :collected, 'collector-v1', :parser)
                        RETURNING id
                        """
                    ),
                    {
                        "hash": str(index) * 64,
                        "payload": '{"data":"value"}',
                        "collected": collected_at,
                        "parser": f"parser-v{index}",
                    },
                ).scalar_one()
            )
        for index, (payload_id, observed_at) in enumerate(
            zip(payload_ids, (first_seen, second_seen), strict=True), start=1
        ):
            connection.execute(
                text(
                    """
                    INSERT INTO source_observations
                        (run_id, raw_payload_id, source, source_item_id, canonical_text,
                         source_timestamp, observed_at, source_url, metrics)
                    VALUES
                        (:run_id, :payload_id, 'GOOGLE_TRENDS', :item_id, :canonical,
                         :observed, :observed,
                         'https://trends.google.com/trending/rss?geo=KR', CAST('{}' AS JSON))
                    """
                ),
                {
                    "run_id": run_id,
                    "payload_id": payload_id,
                    "item_id": f"legacy:{index}",
                    "canonical": f"legacy {index}",
                    "observed": observed_at,
                },
            )
    engine.dispose()

    command.upgrade(config, "head")

    verification = create_engine(TEST_DATABASE_URL)
    with verification.connect() as connection:
        fetch = connection.execute(
            text("SELECT raw_payload_id, parser_version FROM raw_fetches WHERE run_id = :run_id"),
            {"run_id": run_id},
        ).one()
        assert fetch.raw_payload_id == payload_ids[1]
        assert fetch.parser_version == "parser-v2"
    verification.dispose()
