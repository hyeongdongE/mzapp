"""add exact evidence provenance and idempotency keys

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-21 01:25:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    duplicate_observation_id = op.get_bind().execute(
        sa.text(
            """
            SELECT observation_id
            FROM evidence
            WHERE observation_id IS NOT NULL
            GROUP BY observation_id
            HAVING count(*) > 1
            ORDER BY observation_id
            LIMIT 1
            """
        )
    ).scalar_one_or_none()
    if duplicate_observation_id is not None:
        raise RuntimeError(
            "migration 0006 found duplicate evidence for "
            f"observation_id={duplicate_observation_id}; reconcile those evidence rows and rerun"
        )

    op.add_column("evidence", sa.Column("resolution_attempt_id", sa.Integer()))
    op.add_column("evidence", sa.Column("raw_fetch_id", sa.Integer()))
    op.create_foreign_key(
        "fk_evidence_resolution_attempt",
        "evidence",
        "entity_resolution_attempts",
        ["resolution_attempt_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_evidence_raw_fetch",
        "evidence",
        "raw_fetches",
        ["raw_fetch_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_evidence_observation", "evidence", ["observation_id"]
    )
    op.create_unique_constraint(
        "uq_evidence_entity_raw_kind",
        "evidence",
        ["entity_id", "raw_fetch_id", "kind"],
    )
def downgrade() -> None:
    op.drop_constraint("uq_evidence_entity_raw_kind", "evidence", type_="unique")
    op.drop_constraint("uq_evidence_observation", "evidence", type_="unique")
    op.drop_constraint("fk_evidence_raw_fetch", "evidence", type_="foreignkey")
    op.drop_constraint("fk_evidence_resolution_attempt", "evidence", type_="foreignkey")
    op.drop_column("evidence", "raw_fetch_id")
    op.drop_column("evidence", "resolution_attempt_id")
