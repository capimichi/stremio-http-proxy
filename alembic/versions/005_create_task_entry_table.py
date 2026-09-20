"""Create task_entry table

Revision ID: 005_create_task_entry_table
Revises: 004_create_playback_history_table
Create Date: 2026-09-20 18:54:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005_create_task_entry_table"
down_revision: Union[str, None] = "004_create_playback_history_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "task_entry",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("arguments", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("scheduled_at", sa.Float(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.Column("claimed_by", sa.String(length=128), nullable=True),
        sa.Column("claimed_at", sa.Float(), nullable=True),
        sa.Column("processing_expires_at", sa.Float(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.create_index("ix_task_entry_status_scheduled", "task_entry", ["status", "scheduled_at"])
    op.create_index("ix_task_entry_name_status", "task_entry", ["name", "status"])


def downgrade() -> None:
    op.drop_index("ix_task_entry_name_status", table_name="task_entry")
    op.drop_index("ix_task_entry_status_scheduled", table_name="task_entry")
    op.drop_table("task_entry")
