"""initial: campaigns, offers_cache, operations_log

Revision ID: 0001
Revises:
Create Date: 2026-11-24
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("keitaro_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("alias", sa.String(length=64), nullable=True),
        sa.Column("geo", sa.JSON(), nullable=False),
        sa.Column("initial_offer_id", sa.Integer(), nullable=False),
        sa.Column("google_stream_id", sa.Integer(), nullable=True),
        sa.Column("offers_stream_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_campaigns_keitaro_id", "campaigns", ["keitaro_id"], unique=True)

    op.create_table(
        "offers_cache",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("country", sa.JSON(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_offers_cache_name", "offers_cache", ["name"])

    op.create_table(
        "operations_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=True),
        sa.Column("stream_id", sa.Integer(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_operations_log_campaign_id", "operations_log", ["campaign_id"])
    op.create_index("ix_operations_log_created_at", "operations_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_operations_log_created_at", table_name="operations_log")
    op.drop_index("ix_operations_log_campaign_id", table_name="operations_log")
    op.drop_table("operations_log")
    op.drop_index("ix_offers_cache_name", table_name="offers_cache")
    op.drop_table("offers_cache")
    op.drop_index("ix_campaigns_keitaro_id", table_name="campaigns")
    op.drop_table("campaigns")
