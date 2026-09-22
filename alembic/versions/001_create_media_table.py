"""Create media table

Revision ID: 001_create_media_table
Revises: None
Create Date: 2026-09-20 18:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001_create_media_table"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "media",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("imdb_id", sa.String(length=64), nullable=True),
        sa.Column("tmdb_id", sa.String(length=64), nullable=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("year", sa.String(length=16), nullable=True),
        sa.Column("poster", sa.Text(), nullable=True),
        sa.Column("backdrop", sa.Text(), nullable=True),
        sa.Column("overview", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("last_accessed_at", sa.Float(), nullable=False),
    )
    op.create_index("ix_media_type", "media", ["type"])
    op.create_index("ix_media_last_accessed_at", "media", ["last_accessed_at"])
    op.create_index("ix_media_imdb_id", "media", ["imdb_id"], unique=True)
    op.create_index("ix_media_tmdb_id", "media", ["tmdb_id"])


def downgrade() -> None:
    op.drop_index("ix_media_tmdb_id", table_name="media")
    op.drop_index("ix_media_imdb_id", table_name="media")
    op.drop_index("ix_media_last_accessed_at", table_name="media")
    op.drop_index("ix_media_type", table_name="media")
    op.drop_table("media")
