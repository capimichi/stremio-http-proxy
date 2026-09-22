"""Create media_items table

Revision ID: 002_create_media_items_table
Revises: 001_create_media_table
Create Date: 2026-09-20 18:51:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_create_media_items_table"
down_revision: Union[str, None] = "001_create_media_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "media_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "media_id",
            sa.Integer(),
            sa.ForeignKey("media.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("season", sa.Integer(), nullable=True),
        sa.Column("episode", sa.Integer(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("last_accessed_at", sa.Float(), nullable=False),
        sa.UniqueConstraint("media_id", "season", "episode", name="uq_media_items_media_season_episode"),
    )
    op.create_index("ix_media_items_media_id", "media_items", ["media_id"])
    op.create_index("ix_media_items_last_accessed_at", "media_items", ["last_accessed_at"])


def downgrade() -> None:
    op.drop_index("ix_media_items_last_accessed_at", table_name="media_items")
    op.drop_index("ix_media_items_media_id", table_name="media_items")
    op.drop_table("media_items")
