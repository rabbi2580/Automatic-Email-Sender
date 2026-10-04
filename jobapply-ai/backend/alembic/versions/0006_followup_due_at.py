"""add follow-up due time

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("follow_up_drafts", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_follow_up_drafts_due_at", "follow_up_drafts", ["due_at"])


def downgrade() -> None:
    op.drop_index("ix_follow_up_drafts_due_at", table_name="follow_up_drafts")
    op.drop_column("follow_up_drafts", "due_at")
