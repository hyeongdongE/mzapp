"""add immutable product-card provenance to review audit

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-21 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("reviews", sa.Column("product_card_id", sa.Integer(), nullable=True))
    op.add_column("reviews", sa.Column("snapshot_id", sa.Integer(), nullable=True))
    op.add_column(
        "reviews", sa.Column("category_at_review", sa.String(length=64), nullable=True)
    )
    op.create_foreign_key(
        "fk_reviews_product_card_id",
        "reviews",
        "product_trend_cards",
        ["product_card_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_reviews_snapshot_id",
        "reviews",
        "trend_snapshots",
        ["snapshot_id"],
        ["id"],
    )
    op.create_index(
        "ix_reviews_product_card_time", "reviews", ["product_card_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_reviews_product_card_time", table_name="reviews")
    op.drop_constraint("fk_reviews_snapshot_id", "reviews", type_="foreignkey")
    op.drop_constraint("fk_reviews_product_card_id", "reviews", type_="foreignkey")
    op.drop_column("reviews", "category_at_review")
    op.drop_column("reviews", "snapshot_id")
    op.drop_column("reviews", "product_card_id")
