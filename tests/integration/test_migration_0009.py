from __future__ import annotations

import os

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


def test_0009_upgrade_downgrade_seeds_disabled_categories_and_review_provenance() -> None:
    assert TEST_DATABASE_URL is not None
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "0008")
    command.upgrade(config, "0009")

    engine = create_engine(TEST_DATABASE_URL)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "0009"
        categories = connection.execute(
            text("SELECT category, status FROM category_settings ORDER BY category")
        ).all()
        assert len(categories) == 8
        assert {row.status for row in categories} == {"DISABLED"}
        review_columns = {
            row.column_name
            for row in connection.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'reviews'
                    """
                )
            )
        }
        assert {
            "previous_status",
            "resulting_status",
            "auto_pipeline_result",
            "human_override_reason",
            "product_card_id",
            "snapshot_id",
            "category_at_review",
        } <= review_columns
        constraints = {
            row.conname
            for row in connection.execute(
                text(
                    """
                    SELECT conname
                    FROM pg_constraint
                    WHERE conrelid = 'product_trend_cards'::regclass
                    """
                )
            )
        }
        assert "ck_product_card_mode_provenance" in constraints
    engine.dispose()

    command.downgrade(config, "0008")
    downgraded = create_engine(TEST_DATABASE_URL)
    with downgraded.connect() as connection:
        assert connection.execute(
            text("SELECT to_regclass('product_trend_cards')")
        ).scalar_one() is None
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "0008"
    downgraded.dispose()

    command.upgrade(config, "0009")
    reupgraded = create_engine(TEST_DATABASE_URL)
    with reupgraded.connect() as connection:
        assert connection.execute(
            text("SELECT count(*) FROM category_settings WHERE status = 'DISABLED'")
        ).scalar_one() == 8
    reupgraded.dispose()
