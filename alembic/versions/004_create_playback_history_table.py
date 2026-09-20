"""Create playback_history table

Revision ID: 004_create_playback_history_table
Revises: 003_create_cache_entries_table
Create Date: 2026-09-20 18:53:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_create_playback_history_table"
down_revision: Union[str, None] = "003_create_cache_entries_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "playback_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "media_item_id",
            sa.String(length=128),
            sa.ForeignKey("media_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "media_id",
            sa.String(length=128),
            sa.ForeignKey("media.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("poster", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("source_link", sa.Text(), nullable=True),
        sa.Column("infohash", sa.String(length=40), nullable=True),
        sa.Column("file_index", sa.Integer(), nullable=True),
        sa.Column("played_at", sa.Float(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("progress_seconds", sa.Float(), nullable=True),
    )
    op.create_index("ix_playback_history_media_item_id", "playback_history", ["media_item_id"])
    op.create_index("ix_playback_history_media_id", "playback_history", ["media_id"])
    op.create_index("ix_playback_history_played_at", "playback_history", ["played_at"])


def downgrade() -> None:
    op.drop_index("ix_playback_history_played_at", table_name="playback_history")
    op.drop_index("ix_playback_history_media_id", table_name="playback_history")
    op.drop_index("ix_playback_history_media_item_id", table_name="playback_history")
    op.drop_table("playback_history")
