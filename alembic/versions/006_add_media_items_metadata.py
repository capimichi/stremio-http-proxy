"""Add overview, thumbnail, release_date to media_items table

Revision ID: 006_add_media_items_metadata
Revises: 005_create_task_entry_table
Create Date: 2026-09-22 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006_add_media_items_metadata"
down_revision: Union[str, None] = "005_create_task_entry_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("media_items", sa.Column("overview", sa.Text(), nullable=True))
    op.add_column("media_items", sa.Column("thumbnail", sa.Text(), nullable=True))
    op.add_column("media_items", sa.Column("release_date", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("media_items", "release_date")
    op.drop_column("media_items", "thumbnail")
    op.drop_column("media_items", "overview")
