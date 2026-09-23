"""add Daily Brief quality review storage

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-23 23:55:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "daily_briefs",
        sa.Column(
            "pipeline_version",
            sa.String(length=80),
            nullable=False,
            server_default="intelligence-pipeline-v1",
        ),
    )
    op.alter_column("daily_briefs", "pipeline_version", server_default=None)
    op.add_column(
        "brief_items",
        sa.Column("assessment_version", sa.String(length=80), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE brief_items AS item
            SET assessment_version = (
                SELECT assessment.assessment_version
                FROM event_assessments AS assessment
                WHERE assessment.event_cluster_id = item.event_cluster_id
                  AND (
                      SELECT count(*)
                      FROM event_assessments AS candidates
                      WHERE candidates.event_cluster_id = item.event_cluster_id
                  ) = 1
            )
            """
        )
    )
    missing_snapshot_count = op.get_bind().execute(
        sa.text("SELECT count(*) FROM brief_items WHERE assessment_version IS NULL")
    ).scalar_one()
    if missing_snapshot_count:
        raise RuntimeError(
            "cannot migrate brief_items with missing or ambiguous assessment provenance"
        )
    op.alter_column(
        "brief_items",
        "assessment_version",
        existing_type=sa.String(length=80),
        nullable=False,
    )
    op.create_table(
        "brief_review_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "brief_id",
            sa.Integer(),
            sa.ForeignKey("daily_briefs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reviewer", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("completion_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "missing_events_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("overall_notes", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("brief_id", "reviewer", name="uq_brief_review_session_brief_reviewer"),
    )
    op.create_table(
        "brief_review_reopens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("brief_review_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor", sa.String(length=160), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_completion_revision", sa.Integer(), nullable=False),
    )
    op.create_table(
        "brief_review_activity_pulses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("brief_review_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_event_id", sa.String(length=160), nullable=False),
        sa.Column("active_seconds", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "active_seconds >= 1 AND active_seconds <= 30",
            name="ck_brief_review_activity_seconds",
        ),
        sa.UniqueConstraint("session_id", "client_event_id", name="uq_brief_review_activity_event"),
    )
    op.create_table(
        "brief_item_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("brief_review_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "brief_item_id",
            sa.Integer(),
            sa.ForeignKey("brief_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("usefulness", sa.String(length=64), nullable=False),
        sa.Column("event_selection", sa.String(length=64), nullable=False),
        sa.Column("fact_correctness", sa.String(length=64), nullable=False),
        sa.Column("interpretation_quality", sa.String(length=64), nullable=False),
        sa.Column("watch_usefulness", sa.String(length=64), nullable=False),
        sa.Column("verbosity", sa.String(length=64), nullable=False),
        sa.Column("evidence_set_usefulness", sa.String(length=64), nullable=False),
        sa.Column("incorrect_merge_verdict", sa.String(length=64), nullable=False),
        sa.Column("duplicate_escape_verdict", sa.String(length=64), nullable=False),
        sa.Column(
            "duplicate_of_brief_item_id",
            sa.Integer(),
            sa.ForeignKey("brief_items.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "duplicate_of_event_cluster_id",
            sa.Integer(),
            sa.ForeignKey("event_clusters.id", ondelete="RESTRICT"),
        ),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "session_id", "brief_item_id", name="uq_brief_item_review_session_item"
        ),
    )
    op.create_table(
        "brief_item_review_merge_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "brief_item_review_id",
            sa.Integer(),
            sa.ForeignKey("brief_item_reviews.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_cluster_item_id",
            sa.Integer(),
            sa.ForeignKey("event_cluster_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text()),
        sa.UniqueConstraint(
            "brief_item_review_id",
            "event_cluster_item_id",
            name="uq_brief_item_review_merge_membership",
        ),
    )
    op.create_table(
        "missing_event_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("brief_review_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("canonical_title", sa.String(length=500), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("discovered_from", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "session_id", "canonical_url", name="uq_missing_event_review_session_url"
        ),
    )


def downgrade() -> None:
    op.drop_table("missing_event_reviews")
    op.drop_table("brief_item_review_merge_memberships")
    op.drop_table("brief_item_reviews")
    op.drop_table("brief_review_activity_pulses")
    op.drop_table("brief_review_reopens")
    op.drop_table("brief_review_sessions")
    op.drop_column("brief_items", "assessment_version")
    op.drop_column("daily_briefs", "pipeline_version")
