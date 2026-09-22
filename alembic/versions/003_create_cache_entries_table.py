"""Create cache_entries table

Revision ID: 003_create_cache_entries_table
Revises: 002_create_media_items_table
Create Date: 2026-09-20 18:52:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003_create_cache_entries_table"
down_revision: Union[str, None] = "002_create_media_items_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cache_entries",
        sa.Column("cache_key", sa.String(length=128), primary_key=True, nullable=False),
        sa.Column("infohash", sa.String(length=40), nullable=False),
        sa.Column("cache_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("source_link", sa.Text(), nullable=True),
        sa.Column("poster", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("tmp_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=True),
        sa.Column("last_accessed_at", sa.Float(), nullable=True),
        sa.Column("completed_at", sa.Float(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("downloaded_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("expected_bytes", sa.BigInteger(), nullable=True),
        sa.Column("progress_percent", sa.Float(), nullable=True),
        sa.Column("download_speed_bytes_per_second", sa.Float(), nullable=True),
        sa.Column("last_progress_at", sa.Float(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=True, server_default="100"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=True, server_default="3"),
        sa.Column("trigger", sa.String(length=32), nullable=True),
        sa.Column("content_type", sa.String(length=32), nullable=True),
        sa.Column(
            "media_item_id",
            sa.Integer(),
            sa.ForeignKey("media_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("available_at", sa.Float(), nullable=True),
        sa.Column("claimed_at", sa.Float(), nullable=True),
        sa.Column("claimed_by", sa.String(length=128), nullable=True),
        sa.Column("processing_expires_at", sa.Float(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.UniqueConstraint("infohash", "cache_index", name="uq_cache_entries_infohash_cache_index"),
    )
    op.create_index("ix_cache_entries_status", "cache_entries", ["status"])
    op.create_index("ix_cache_entries_last_accessed_at", "cache_entries", ["last_accessed_at"])
    op.create_index("ix_cache_entries_media_item_id", "cache_entries", ["media_item_id"])


def downgrade() -> None:
    op.drop_index("ix_cache_entries_media_item_id", table_name="cache_entries")
    op.drop_index("ix_cache_entries_last_accessed_at", table_name="cache_entries")
    op.drop_index("ix_cache_entries_status", table_name="cache_entries")
    op.drop_table("cache_entries")
