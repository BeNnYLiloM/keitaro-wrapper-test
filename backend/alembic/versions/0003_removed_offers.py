"""removed_offers: удалённые из потоков офферы, которые можно восстановить

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-24
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "removed_offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stream_id", sa.Integer(), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("share", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("stream_id", "offer_id", name="uq_removed_offers_stream_offer"),
    )
    op.create_index("ix_removed_offers_stream_id", "removed_offers", ["stream_id"])


def downgrade() -> None:
    op.drop_index("ix_removed_offers_stream_id", table_name="removed_offers")
    op.drop_table("removed_offers")
