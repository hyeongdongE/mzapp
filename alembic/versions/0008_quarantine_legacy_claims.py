"""quarantine claims without replayable snapshot provenance

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-21 02:05:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            DELETE FROM summary_cache cache
            WHERE EXISTS (
                SELECT 1
                FROM claims claim
                WHERE claim.entity_id = cache.entity_id
                  AND claim.prompt_version = cache.prompt_version
                  AND claim.evidence_set_hash = cache.evidence_set_hash
                  AND NOT EXISTS (
                      SELECT 1 FROM claim_snapshots link WHERE link.claim_id = claim.id
                  )
            )
            """
        )
    )
    op.get_bind().execute(
        sa.text(
            """
            UPDATE claims claim
            SET status = 'UNSUPPORTED',
                publishable = false,
                reason = 'LEGACY_PROVENANCE_UNVERIFIED'
            WHERE NOT EXISTS (
                SELECT 1 FROM claim_snapshots link WHERE link.claim_id = claim.id
            )
            """
        )
    )


def downgrade() -> None:
    # Quarantined publication state cannot be reconstructed safely.
    pass
