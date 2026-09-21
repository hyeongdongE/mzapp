"""add isolated anonymous user MVP schema

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-21 12:00:00
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(length: int = 64) -> sa.String:
    return sa.String(length=length)


def upgrade() -> None:
    op.add_column("reviews", sa.Column("previous_status", _enum(), nullable=True))
    op.add_column("reviews", sa.Column("resulting_status", _enum(), nullable=True))
    op.add_column("reviews", sa.Column("auto_pipeline_result", sa.Boolean(), nullable=True))
    op.add_column("reviews", sa.Column("human_override_reason", sa.Text(), nullable=True))

    op.create_table(
        "category_settings",
        sa.Column("category", _enum(), primary_key=True),
        sa.Column("status", _enum(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.String(length=160), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    categories = (
        "SPORTS",
        "ENTERTAINMENT",
        "FOOD",
        "GAME",
        "AI_TECH",
        "MEME_INTERNET",
        "FASHION_BEAUTY",
        "SHOPPING_PRODUCT",
    )
    settings = sa.table(
        "category_settings",
        sa.column("category", _enum()),
        sa.column("status", _enum()),
        sa.column("rationale", sa.Text()),
        sa.column("updated_by", sa.String(length=160)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        settings,
        [
            {
                "category": category,
                "status": "DISABLED",
                "rationale": "Insufficient LIVE evaluation evidence",
                "updated_by": "migration-0009",
                "updated_at": datetime.now(UTC),
            }
            for category in categories
        ],
    )

    op.create_table(
        "product_trend_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(length=36), nullable=False),
        sa.Column("data_mode", _enum(), nullable=False),
        sa.Column("fixture_key", sa.String(length=160), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("snapshot_id", sa.Integer(), nullable=True),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("category", _enum(), nullable=False),
        sa.Column("lifecycle", _enum(), nullable=False),
        sa.Column("what_text", sa.Text(), nullable=False),
        sa.Column("interest_text", sa.Text(), nullable=False),
        sa.Column("cause_text", sa.Text(), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trend_score", sa.Float(), nullable=False),
        sa.Column("auto_pipeline_result", sa.Boolean(), nullable=False),
        sa.Column("fixture_approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("suppressed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["trend_entities.id"]),
        sa.ForeignKeyConstraint(["snapshot_id"], ["trend_snapshots.id"]),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.UniqueConstraint("public_id", name="uq_product_card_public_id"),
        sa.UniqueConstraint("snapshot_id", name="uq_product_card_snapshot"),
        sa.UniqueConstraint("data_mode", "fixture_key", name="uq_product_card_fixture"),
        sa.CheckConstraint(
            "(data_mode = 'LIVE' AND entity_id IS NOT NULL AND snapshot_id IS NOT NULL "
            "AND pipeline_run_id IS NOT NULL AND fixture_key IS NULL) OR "
            "(data_mode <> 'LIVE' AND fixture_key IS NOT NULL)",
            name="ck_product_card_mode_provenance",
        ),
    )
    op.create_index("ix_product_trend_cards_public_id", "product_trend_cards", ["public_id"])
    op.create_index(
        "ix_product_card_mode_category_time",
        "product_trend_cards",
        ["data_mode", "category", "observed_at"],
    )

    op.create_table(
        "anonymous_users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("credential_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("data_mode", _enum(), nullable=False, server_default="LIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "user_interests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("category", _enum(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["anonymous_users.id"]),
        sa.UniqueConstraint("user_id", "category", name="uq_user_interest"),
        sa.CheckConstraint("category <> 'OTHER'", name="ck_user_interest_not_other"),
    )
    op.create_table(
        "notification_preferences",
        sa.Column("user_id", sa.String(length=36), primary_key=True),
        sa.Column("mode", _enum(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["anonymous_users.id"]),
    )
    op.create_table(
        "trend_interactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("first_impression_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_impression_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("impression_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("open_count", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["user_id"], ["anonymous_users.id"]),
        sa.ForeignKeyConstraint(["card_id"], ["product_trend_cards.id"]),
        sa.UniqueConstraint("user_id", "card_id", name="uq_trend_interaction"),
    )
    op.create_table(
        "trend_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("feedback_type", _enum(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["anonymous_users.id"]),
        sa.ForeignKeyConstraint(["card_id"], ["product_trend_cards.id"]),
        sa.UniqueConstraint("user_id", "card_id", name="uq_trend_feedback"),
    )
    op.create_table(
        "saved_trends",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["anonymous_users.id"]),
        sa.ForeignKeyConstraint(["card_id"], ["product_trend_cards.id"]),
        sa.UniqueConstraint("user_id", "card_id", name="uq_saved_trend"),
    )
    op.create_table(
        "product_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", _enum(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=True),
        sa.Column("category", _enum(), nullable=True),
        sa.Column("data_mode", _enum(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["anonymous_users.id"]),
        sa.ForeignKeyConstraint(["card_id"], ["product_trend_cards.id"]),
    )
    op.create_index(
        "ix_product_event_mode_time", "product_events", ["data_mode", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_product_event_mode_time", table_name="product_events")
    op.drop_table("product_events")
    op.drop_table("saved_trends")
    op.drop_table("trend_feedback")
    op.drop_table("trend_interactions")
    op.drop_table("notification_preferences")
    op.drop_table("user_interests")
    op.drop_table("anonymous_users")
    op.drop_index("ix_product_card_mode_category_time", table_name="product_trend_cards")
    op.drop_index("ix_product_trend_cards_public_id", table_name="product_trend_cards")
    op.drop_table("product_trend_cards")
    op.drop_table("category_settings")
    op.drop_column("reviews", "human_override_reason")
    op.drop_column("reviews", "auto_pipeline_result")
    op.drop_column("reviews", "resulting_status")
    op.drop_column("reviews", "previous_status")
