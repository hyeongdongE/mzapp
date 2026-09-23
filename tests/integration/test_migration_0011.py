from __future__ import annotations

import os

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.config.settings import get_settings

TEST_DATABASE_URL = os.getenv("TEST_MIGRATION_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="TEST_MIGRATION_DATABASE_URL is required for migration verification",
)


def test_0011_upgrade_downgrade_preserves_existing_schema() -> None:
    assert TEST_DATABASE_URL is not None
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    command.downgrade(config, "0010")

    engine = create_engine(TEST_DATABASE_URL)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "0010"
        tables = set(inspect(connection).get_table_names())
        assert "product_trend_cards" in tables
        assert "raw_items" not in tables
    engine.dispose()

    command.upgrade(config, "0011")
    upgraded = create_engine(TEST_DATABASE_URL)
    with upgraded.connect() as connection:
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "0011"
        tables = set(inspect(connection).get_table_names())
        assert {
            "source_health",
            "raw_items",
            "event_clusters",
            "event_fact_evidence",
            "daily_briefs",
            "brief_item_facts",
        } <= tables
        assert "product_trend_cards" in tables
    upgraded.dispose()

    command.downgrade(config, "0010")
    downgraded = create_engine(TEST_DATABASE_URL)
    with downgraded.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        assert "raw_items" not in tables
        assert "product_trend_cards" in tables
    downgraded.dispose()

    command.upgrade(config, "head")
