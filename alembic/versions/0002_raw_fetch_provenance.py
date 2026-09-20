"""add per-run raw fetch provenance

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-20 23:55:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "raw_fetches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("raw_payload_id", sa.Integer(), nullable=False),
        sa.Column("request_url", sa.Text(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collector_version", sa.String(length=80), nullable=False),
        sa.Column("parser_version", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(["raw_payload_id"], ["raw_payloads.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["collection_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    op.execute(
        sa.text(
            """
            WITH ranked_fetches AS (
                SELECT
                    observation.run_id,
                    observation.raw_payload_id,
                    CASE
                        WHEN observation.source = 'GOOGLE_TRENDS'
                        THEN 'https://trends.google.com/trending/rss?geo=KR'
                        ELSE observation.source_url
                    END AS request_url,
                    payload.collected_at,
                    payload.source_timestamp,
                    payload.collector_version,
                    payload.parser_version,
                    ROW_NUMBER() OVER (
                        PARTITION BY observation.run_id
                        ORDER BY observation.observed_at DESC, observation.id DESC
                    ) AS fetch_rank
                FROM source_observations AS observation
                JOIN raw_payloads AS payload ON payload.id = observation.raw_payload_id
            )
            INSERT INTO raw_fetches (
                run_id,
                raw_payload_id,
                request_url,
                collected_at,
                source_timestamp,
                collector_version,
                parser_version
            )
            SELECT
                run_id,
                raw_payload_id,
                request_url,
                collected_at,
                source_timestamp,
                collector_version,
                parser_version
            FROM ranked_fetches
            WHERE fetch_rank = 1
            """
        )
    )


def downgrade() -> None:
    op.drop_table("raw_fetches")
