"""roadmap confidence, ATS, reminders, interview and calendar data

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("notifications") as b:
        b.add_column(sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("resumes") as b:
        b.add_column(sa.Column("parse_quality", sa.JSON(), nullable=False, server_default="{}"))
        b.add_column(sa.Column("correction_feedback", sa.JSON(), nullable=False, server_default="[]"))
    with op.batch_alter_table("jobs") as b:
        b.add_column(sa.Column("ats_score", sa.Float(), nullable=True))
        b.add_column(sa.Column("ats_report", sa.JSON(), nullable=False, server_default="{}"))
    op.create_table("interview_preps", sa.Column("user_id", sa.Uuid(), nullable=False), sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("questions", sa.JSON(), nullable=False), sa.Column("notes", sa.Text(), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("application_id"))
    op.create_table("calendar_events", sa.Column("user_id", sa.Uuid(), nullable=False), sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(20), nullable=False), sa.Column("external_id", sa.String(300)), sa.Column("title", sa.String(300), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False), sa.Column("ends_at", sa.DateTime(timezone=True)), sa.Column("location", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("id", sa.Uuid(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"))


def downgrade() -> None:
    op.drop_table("calendar_events"); op.drop_table("interview_preps")
    with op.batch_alter_table("jobs") as b: b.drop_column("ats_report"); b.drop_column("ats_score")
    with op.batch_alter_table("resumes") as b: b.drop_column("correction_feedback"); b.drop_column("parse_quality")
    with op.batch_alter_table("notifications") as b: b.drop_column("dismissed_at"); b.drop_column("snoozed_until")
