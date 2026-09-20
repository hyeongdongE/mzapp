"""add summary cache and snapshot provenance

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-21 01:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    duplicate_claim = op.get_bind().execute(
        sa.text(
            """
            SELECT entity_id
            FROM claims
            GROUP BY entity_id, prompt_version, evidence_set_hash, kind
            HAVING count(*) > 1
            ORDER BY entity_id
            LIMIT 1
            """
        )
    ).scalar_one_or_none()
    if duplicate_claim is not None:
        raise RuntimeError(
            "migration 0007 found duplicate cached claims for "
            f"entity_id={duplicate_claim}; reconcile those claim rows and rerun"
        )

    op.create_unique_constraint(
        "uq_claim_cache_kind",
        "claims",
        ["entity_id", "prompt_version", "evidence_set_hash", "kind"],
    )
    op.create_table(
        "claim_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("claim_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"]),
        sa.ForeignKeyConstraint(["snapshot_id"], ["trend_snapshots.id"]),
        sa.UniqueConstraint("claim_id", "snapshot_id", name="uq_claim_snapshot"),
    )
    op.create_table(
        "summary_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column("evidence_set_hash", sa.String(length=64), nullable=False),
        sa.Column("claims_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["trend_entities.id"]),
        sa.UniqueConstraint(
            "entity_id",
            "prompt_version",
            "evidence_set_hash",
            name="uq_summary_cache_key",
        ),
    )


def downgrade() -> None:
    op.drop_table("summary_cache")
    op.drop_table("claim_snapshots")
    op.drop_constraint("uq_claim_cache_kind", "claims", type_="unique")
