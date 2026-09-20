"""add entity resolution provenance and alias trust metadata

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-21 00:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "trend_entities",
        sa.Column("entity_types", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )
    op.add_column(
        "entity_aliases",
        sa.Column(
            "source",
            sa.String(length=40),
            server_default="WIKIDATA_ALIAS",
            nullable=False,
        ),
    )
    op.add_column(
        "entity_aliases",
        sa.Column("approved", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_unique_constraint(
        "uq_trend_entities_wikidata_id", "trend_entities", ["wikidata_id"]
    )
    op.create_table(
        "entity_resolution_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=160), nullable=False),
        sa.Column("raw_fetch_ids", sa.JSON(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["trend_candidates.id"]),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_resolution_attempt_run_candidate",
        "entity_resolution_attempts",
        ["pipeline_run_id", "candidate_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_resolution_attempt_run_candidate", table_name="entity_resolution_attempts"
    )
    op.drop_table("entity_resolution_attempts")
    op.drop_constraint(
        "uq_trend_entities_wikidata_id", "trend_entities", type_="unique"
    )
    op.drop_column("entity_aliases", "approved")
    op.drop_column("entity_aliases", "source")
    op.drop_column("trend_entities", "entity_types")
