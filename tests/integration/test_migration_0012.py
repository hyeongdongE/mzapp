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


def test_0012_upgrade_backfills_brief_and_round_trips() -> None:
    assert TEST_DATABASE_URL is not None
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.downgrade(config, "base")
    command.upgrade(config, "0011")
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM daily_briefs"))
        connection.execute(
            text(
                """
                INSERT INTO daily_briefs (
                    brief_date, version, status, window_start, window_end, generated_at,
                    raw_item_count, event_cluster_count, candidate_count, selected_count,
                    word_count, reading_time_seconds, generation_version
                ) VALUES (
                    DATE '2026-09-23', 1, 'PUBLISHED', NOW(), NOW(), NOW(),
                    0, 0, 0, 0, 0, 0, 'brief-v1'
                )
                """
            )
        )
    engine.dispose()

    command.upgrade(config, "0012")
    upgraded = create_engine(TEST_DATABASE_URL)
    with upgraded.connect() as connection:
        assert (
            connection.execute(text("SELECT pipeline_version FROM daily_briefs")).scalar_one()
            == "intelligence-pipeline-v1"
        )
        assert {
            "brief_review_sessions",
            "brief_review_reopens",
            "brief_review_activity_pulses",
            "brief_item_reviews",
            "brief_item_review_merge_memberships",
            "missing_event_reviews",
        } <= set(inspect(connection).get_table_names())
        inspector = inspect(connection)
        assert {
            value["name"] for value in inspector.get_unique_constraints("brief_review_sessions")
        } == {"uq_brief_review_session_brief_reviewer"}
        assert {
            value["name"]
            for value in inspector.get_unique_constraints("brief_review_activity_pulses")
        } == {"uq_brief_review_activity_event"}
        assert {
            value["name"]
            for value in inspector.get_check_constraints("brief_review_activity_pulses")
        } == {"ck_brief_review_activity_seconds"}
        review_foreign_keys = inspector.get_foreign_keys("brief_item_reviews")
        assert {value["referred_table"] for value in review_foreign_keys} == {
            "brief_review_sessions",
            "brief_items",
            "event_clusters",
        }
    upgraded.dispose()

    command.downgrade(config, "0011")
    downgraded = create_engine(TEST_DATABASE_URL)
    with downgraded.connect() as connection:
        assert "pipeline_version" not in {
            column["name"] for column in inspect(connection).get_columns("daily_briefs")
        }
        assert connection.execute(text("SELECT count(*) FROM daily_briefs")).scalar_one() == 1
    downgraded.dispose()
    command.upgrade(config, "head")
