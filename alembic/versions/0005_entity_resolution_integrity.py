"""enforce historical cutoff and entity resolution integrity

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-21 00:35:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "trend_candidates",
        sa.Column("generation", sa.Integer(), server_default="1", nullable=False),
    )
    op.drop_constraint("uq_candidate_source_text", "trend_candidates", type_="unique")
    op.create_unique_constraint(
        "uq_candidate_source_text_generation",
        "trend_candidates",
        ["source", "normalized_text", "generation"],
    )
    op.create_unique_constraint(
        "uq_entity_candidate_single_link", "entity_candidates", ["candidate_id"]
    )

    op.add_column(
        "entity_resolution_attempts", sa.Column("entity_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "entity_resolution_attempts",
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_resolution_attempt_entity",
        "entity_resolution_attempts",
        "trend_entities",
        ["entity_id"],
        ["id"],
    )
    op.execute(
        sa.text(
            """
            UPDATE entity_resolution_attempts AS attempt
            SET as_of = run.as_of
            FROM pipeline_runs AS run
            WHERE run.id = attempt.pipeline_run_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE entity_resolution_attempts AS attempt
            SET entity_id = link.entity_id
            FROM entity_candidates AS link
            WHERE link.candidate_id = attempt.candidate_id
              AND attempt.status = 'RESOLVED'
            """
        )
    )
    op.alter_column("entity_resolution_attempts", "as_of", nullable=False)

    op.create_table(
        "entity_resolution_attempt_raw_fetches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("raw_fetch_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["attempt_id"], ["entity_resolution_attempts.id"]),
        sa.ForeignKeyConstraint(["raw_fetch_id"], ["raw_fetches.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "attempt_id", "raw_fetch_id", name="uq_resolution_attempt_raw_fetch"
        ),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                INSERT INTO entity_resolution_attempt_raw_fetches (attempt_id, raw_fetch_id)
                SELECT attempt.id, value::integer
                FROM entity_resolution_attempts AS attempt,
                     json_array_elements_text(attempt.raw_fetch_ids) AS value
                """
            )
        )


def downgrade() -> None:
    op.drop_table("entity_resolution_attempt_raw_fetches")
    op.drop_constraint(
        "fk_resolution_attempt_entity", "entity_resolution_attempts", type_="foreignkey"
    )
    op.drop_column("entity_resolution_attempts", "as_of")
    op.drop_column("entity_resolution_attempts", "entity_id")
    op.drop_constraint(
        "uq_entity_candidate_single_link", "entity_candidates", type_="unique"
    )
    op.drop_constraint(
        "uq_candidate_source_text_generation", "trend_candidates", type_="unique"
    )
    op.create_unique_constraint(
        "uq_candidate_source_text", "trend_candidates", ["source", "normalized_text"]
    )
    op.drop_column("trend_candidates", "generation")
