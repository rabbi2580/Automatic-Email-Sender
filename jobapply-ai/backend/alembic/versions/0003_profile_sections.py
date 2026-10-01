"""add strengths and references to candidate profiles

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-02 03:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    with op.batch_alter_table("profiles", schema=None) as batch_op:
        batch_op.add_column(sa.Column("strengths", json_type, nullable=False, server_default=sa.text("'[]'")))
        batch_op.add_column(sa.Column("reference_contacts", json_type, nullable=False, server_default=sa.text("'[]'")))


def downgrade() -> None:
    with op.batch_alter_table("profiles", schema=None) as batch_op:
        batch_op.drop_column("reference_contacts")
        batch_op.drop_column("strengths")