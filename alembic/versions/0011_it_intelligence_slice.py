"""add SoloPilot IT intelligence first-slice schema

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-23 19:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_health",
        sa.Column("source", sa.String(length=64), primary_key=True),
        sa.Column(
            "collector_key",
            sa.String(length=240),
            primary_key=True,
            nullable=False,
            server_default="default",
        ),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_failure_at", sa.DateTime(timezone=True)),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(length=120)),
        sa.Column(
            "freshness_state", sa.String(length=32), nullable=False, server_default="UNKNOWN"
        ),
        sa.Column("covered_through", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "raw_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("raw_fetch_id", sa.Integer(), sa.ForeignKey("raw_fetches.id"), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=240), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("original_url", sa.Text()),
        sa.Column("author", sa.String(length=240)),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("normalized_title", sa.String(length=500), nullable=False),
        sa.Column("snippet", sa.Text()),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("normalizer_version", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "source",
            "external_id",
            "normalizer_version",
            name="uq_raw_item_source_external_version",
        ),
    )
    op.create_index("ix_raw_item_source_published", "raw_items", ["source", "published_at"])
    op.create_table(
        "event_clusters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(length=36), nullable=False, unique=True),
        sa.Column("canonical_title", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("clustering_version", sa.String(length=80), nullable=False),
        sa.Column("review_status", sa.String(length=64), nullable=False, server_default="PENDING"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_event_cluster_status_seen", "event_clusters", ["status", "last_seen_at"])
    op.create_table(
        "event_cluster_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "event_cluster_id", sa.Integer(), sa.ForeignKey("event_clusters.id"), nullable=False
        ),
        sa.Column("raw_item_id", sa.Integer(), sa.ForeignKey("raw_items.id"), nullable=False),
        sa.Column("assignment_method", sa.String(length=80), nullable=False),
        sa.Column("assignment_score", sa.Float()),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("human_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("raw_item_id", name="uq_event_cluster_raw_item"),
        sa.UniqueConstraint("event_cluster_id", "raw_item_id", name="uq_event_cluster_item"),
    )
    op.create_table(
        "intelligence_entities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("canonical_name", sa.String(length=500), nullable=False),
        sa.Column("normalized_name", sa.String(length=500), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_intelligence_entities_normalized_name",
        "intelligence_entities",
        ["normalized_name"],
    )
    op.create_table(
        "event_entity_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "event_cluster_id", sa.Integer(), sa.ForeignKey("event_clusters.id"), nullable=False
        ),
        sa.Column(
            "entity_id", sa.Integer(), sa.ForeignKey("intelligence_entities.id"), nullable=False
        ),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.UniqueConstraint("event_cluster_id", "entity_id", "role", name="uq_event_entity_role"),
    )
    op.create_table(
        "event_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "event_cluster_id", sa.Integer(), sa.ForeignKey("event_clusters.id"), nullable=False
        ),
        sa.Column("raw_item_id", sa.Integer(), sa.ForeignKey("raw_items.id"), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("fact", sa.JSON(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("publishable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("event_cluster_id", "raw_item_id", name="uq_event_evidence_item"),
    )
    op.create_index("ix_event_evidence_event_kind", "event_evidence", ["event_cluster_id", "kind"])
    op.create_table(
        "event_facts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "event_cluster_id", sa.Integer(), sa.ForeignKey("event_clusters.id"), nullable=False
        ),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("structured_value", sa.JSON(), nullable=False),
        sa.Column("publishable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("validator_version", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_event_fact_event_publishable", "event_facts", ["event_cluster_id", "publishable"]
    )
    op.create_table(
        "event_fact_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_fact_id", sa.Integer(), sa.ForeignKey("event_facts.id"), nullable=False),
        sa.Column(
            "event_evidence_id", sa.Integer(), sa.ForeignKey("event_evidence.id"), nullable=False
        ),
        sa.Column("support_type", sa.String(length=40), nullable=False),
        sa.Column("source_field", sa.String(length=120), nullable=False),
        sa.Column("validation_result", sa.String(length=40), nullable=False),
        sa.Column("validator_version", sa.String(length=80), nullable=False),
        sa.UniqueConstraint("event_fact_id", "event_evidence_id", name="uq_event_fact_evidence"),
    )
    op.create_table(
        "event_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "event_cluster_id", sa.Integer(), sa.ForeignKey("event_clusters.id"), nullable=False
        ),
        sa.Column("confidence", sa.String(length=64), nullable=False),
        sa.Column("confidence_breakdown", sa.JSON(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("importance_breakdown", sa.JSON(), nullable=False),
        sa.Column("assessment_version", sa.String(length=80), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "event_cluster_id", "assessment_version", name="uq_event_assessment_version"
        ),
    )
    op.create_table(
        "daily_briefs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("brief_date", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("today_in_one_line", sa.Text()),
        sa.Column("raw_item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("event_cluster_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("selected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reading_time_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generation_version", sa.String(length=80), nullable=False),
        sa.UniqueConstraint("brief_date", "version", name="uq_daily_brief_date_version"),
    )
    op.create_index("ix_daily_brief_date_status", "daily_briefs", ["brief_date", "status"])
    op.create_table(
        "brief_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("brief_id", sa.Integer(), sa.ForeignKey("daily_briefs.id"), nullable=False),
        sa.Column(
            "event_cluster_id", sa.Integer(), sa.ForeignKey("event_clusters.id"), nullable=False
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("headline", sa.String(length=500), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("what_happened", sa.Text(), nullable=False),
        sa.Column("why_it_matters", sa.Text(), nullable=False),
        sa.Column("fact_text", sa.Text(), nullable=False),
        sa.Column("interpretation_text", sa.Text(), nullable=False),
        sa.Column("watch_text", sa.Text(), nullable=False),
        sa.Column("source_links", sa.JSON(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.UniqueConstraint("brief_id", "position", name="uq_brief_item_position"),
        sa.UniqueConstraint("brief_id", "event_cluster_id", name="uq_brief_item_event"),
    )
    op.create_table(
        "brief_item_facts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("brief_item_id", sa.Integer(), sa.ForeignKey("brief_items.id"), nullable=False),
        sa.Column("event_fact_id", sa.Integer(), sa.ForeignKey("event_facts.id"), nullable=False),
        sa.Column(
            "event_evidence_id", sa.Integer(), sa.ForeignKey("event_evidence.id"), nullable=False
        ),
        sa.Column("fact_text_snapshot", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "brief_item_id",
            "event_fact_id",
            "event_evidence_id",
            name="uq_brief_item_fact_evidence",
        ),
    )


def downgrade() -> None:
    op.drop_table("brief_item_facts")
    op.drop_table("brief_items")
    op.drop_index("ix_daily_brief_date_status", table_name="daily_briefs")
    op.drop_table("daily_briefs")
    op.drop_table("event_assessments")
    op.drop_table("event_fact_evidence")
    op.drop_index("ix_event_fact_event_publishable", table_name="event_facts")
    op.drop_table("event_facts")
    op.drop_index("ix_event_evidence_event_kind", table_name="event_evidence")
    op.drop_table("event_evidence")
    op.drop_table("event_entity_links")
    op.drop_index("ix_intelligence_entities_normalized_name", table_name="intelligence_entities")
    op.drop_table("intelligence_entities")
    op.drop_table("event_cluster_items")
    op.drop_index("ix_event_cluster_status_seen", table_name="event_clusters")
    op.drop_table("event_clusters")
    op.drop_index("ix_raw_item_source_published", table_name="raw_items")
    op.drop_table("raw_items")
    op.drop_table("source_health")
