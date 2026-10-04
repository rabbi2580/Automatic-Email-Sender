"""add mailbox metadata tracking and grounded follow-up drafts

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("email_accounts") as b:
        b.add_column(sa.Column("tracking_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("last_tracking_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("tracking_error", sa.String(500), nullable=True))
    op.create_table("incoming_messages",
        sa.Column("user_id", sa.Uuid(), nullable=False), sa.Column("email_account_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True), sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("external_id", sa.String(300), nullable=False), sa.Column("thread_id", sa.String(300), nullable=False),
        sa.Column("from_address", sa.String(320), nullable=False), sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True), sa.Column("classification", sa.String(30), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=False), sa.Column("auto_updated", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["email_account_id"], ["email_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("user_id", "provider", "external_id", name="uq_incoming_user_provider_external"))
    op.create_index("ix_incoming_messages_email_account_id", "incoming_messages", ["email_account_id"])
    op.create_index("ix_incoming_messages_application_id", "incoming_messages", ["application_id"])
    op.create_index("ix_incoming_messages_created_at", "incoming_messages", ["created_at"])
    op.create_table("follow_up_rules",
        sa.Column("user_id", sa.Uuid(), nullable=False), sa.Column("default_wait_days", sa.Integer(), nullable=False),
        sa.Column("max_followups", sa.Integer(), nullable=False), sa.Column("stop_on_reply", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_follow_up_rule_user"))
    op.create_index("ix_follow_up_rules_user_id", "follow_up_rules", ["user_id"])
    op.create_table("follow_up_drafts",
        sa.Column("user_id", sa.Uuid(), nullable=False), sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("to_address", sa.String(320), nullable=False), sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False), sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True), sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_message_id", sa.String(300), nullable=True), sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("needs_input", sa.Boolean(), nullable=False), sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("idempotency_key"))
    op.create_index("ix_follow_up_drafts_user_id", "follow_up_drafts", ["user_id"])
    op.create_index("ix_follow_up_drafts_application_id", "follow_up_drafts", ["application_id"])


def downgrade() -> None:
    op.drop_table("follow_up_drafts")
    op.drop_table("follow_up_rules")
    op.drop_table("incoming_messages")
    with op.batch_alter_table("email_accounts") as b:
        b.drop_column("tracking_error"); b.drop_column("last_tracking_at"); b.drop_column("tracking_enabled")
