"""pinned_offers: закреплённые доли офферов в потоках

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-24
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
        "pinned_offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stream_id", sa.Integer(), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("stream_id", "offer_id", name="uq_pinned_offers_stream_offer"),
    )
    op.create_index("ix_pinned_offers_stream_id", "pinned_offers", ["stream_id"])


def downgrade() -> None:
    op.drop_index("ix_pinned_offers_stream_id", table_name="pinned_offers")
    op.drop_table("pinned_offers")
