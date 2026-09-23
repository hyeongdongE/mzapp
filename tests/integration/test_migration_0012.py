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
        cluster_id = connection.execute(
            text(
                """
                INSERT INTO event_clusters (
                    public_id, canonical_title, first_seen_at, last_seen_at,
                    status, clustering_version
                ) VALUES (
                    'quality-migration-cluster', 'Migration event', NOW(), NOW(),
                    'ACTIVE', 'cluster-v1'
                ) RETURNING id
                """
            )
        ).scalar_one()
        connection.execute(
            text(
                """
                INSERT INTO event_assessments (
                    event_cluster_id, confidence, confidence_breakdown, importance,
                    importance_breakdown, assessment_version, assessed_at
                ) VALUES (
                    :cluster_id, 'STRONG', '{}'::json, 90,
                    '{}'::json, 'assessment-migration-v1', TIMESTAMPTZ '2026-09-23 13:00:00+00'
                )
                """
            ),
            {"cluster_id": cluster_id},
        )
        brief_id = connection.execute(
            text(
                """
                INSERT INTO daily_briefs (
                    brief_date, version, status, window_start, window_end, generated_at,
                    raw_item_count, event_cluster_count, candidate_count, selected_count,
                    word_count, reading_time_seconds, generation_version
                ) VALUES (
                    DATE '2026-09-23', 1, 'PUBLISHED', NOW(), NOW(),
                    TIMESTAMPTZ '2026-09-23 12:00:00+00',
                    0, 0, 0, 0, 0, 0, 'brief-v1'
                ) RETURNING id
                """
            )
        ).scalar_one()
        connection.execute(
            text(
                """
                INSERT INTO brief_items (
                    brief_id, event_cluster_id, position, headline, category,
                    what_happened, why_it_matters, fact_text, interpretation_text,
                    watch_text, source_links, importance
                ) VALUES (
                    :brief_id, :cluster_id, 1, 'Headline', 'IT', 'What', 'Why',
                    'Fact', 'Interpretation', 'Watch', '[]'::json, 90
                )
                """
            ),
            {"brief_id": brief_id, "cluster_id": cluster_id},
        )
    engine.dispose()

    command.upgrade(config, "0012")
    upgraded = create_engine(TEST_DATABASE_URL)
    with upgraded.connect() as connection:
        assert (
            connection.execute(text("SELECT pipeline_version FROM daily_briefs")).scalar_one()
            == "intelligence-pipeline-v1"
        )
        assert (
            connection.execute(text("SELECT assessment_version FROM brief_items")).scalar_one()
            == "assessment-migration-v1"
        )
        assessment_column = next(
            column
            for column in inspect(connection).get_columns("brief_items")
            if column["name"] == "assessment_version"
        )
        assert assessment_column["nullable"] is False
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
        assert "assessment_version" not in {
            column["name"] for column in inspect(connection).get_columns("brief_items")
        }
        assert connection.execute(text("SELECT count(*) FROM daily_briefs")).scalar_one() == 1
    downgraded.dispose()
    command.upgrade(config, "head")


def test_0012_rejects_ambiguous_legacy_assessment_provenance() -> None:
    assert TEST_DATABASE_URL is not None
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "0011")
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        cluster_id = connection.execute(
            text(
                """
                INSERT INTO event_clusters (
                    public_id, canonical_title, first_seen_at, last_seen_at,
                    status, clustering_version
                ) VALUES (
                    'ambiguous-migration-cluster', 'Ambiguous event', NOW(), NOW(),
                    'ACTIVE', 'cluster-v1'
                ) RETURNING id
                """
            )
        ).scalar_one()
        for version, assessed_at in (
            ("assessment-v1", "2026-09-23 11:00:00+00"),
            ("assessment-v2", "2026-09-23 13:00:00+00"),
        ):
            connection.execute(
                text(
                    """
                    INSERT INTO event_assessments (
                        event_cluster_id, confidence, confidence_breakdown, importance,
                        importance_breakdown, assessment_version, assessed_at
                    ) VALUES (
                        :cluster_id, 'STRONG', '{}'::json, 90, '{}'::json,
                        :version, CAST(:assessed_at AS timestamptz)
                    )
                    """
                ),
                {"cluster_id": cluster_id, "version": version, "assessed_at": assessed_at},
            )
        brief_id = connection.execute(
            text(
                """
                INSERT INTO daily_briefs (
                    brief_date, version, status, window_start, window_end, generated_at,
                    generation_version
                ) VALUES (
                    DATE '2026-09-23', 1, 'PUBLISHED', NOW(), NOW(), NOW(), 'brief-v1'
                ) RETURNING id
                """
            )
        ).scalar_one()
        connection.execute(
            text(
                """
                INSERT INTO brief_items (
                    brief_id, event_cluster_id, position, headline, category,
                    what_happened, why_it_matters, fact_text, interpretation_text,
                    watch_text, source_links, importance
                ) VALUES (
                    :brief_id, :cluster_id, 1, 'Headline', 'IT', 'What', 'Why',
                    'Fact', 'Interpretation', 'Watch', '[]'::json, 90
                )
                """
            ),
            {"brief_id": brief_id, "cluster_id": cluster_id},
        )
    engine.dispose()

    with pytest.raises(RuntimeError, match="ambiguous assessment provenance"):
        command.upgrade(config, "0012")
