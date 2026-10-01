"""Applications, generated documents, emails, email accounts, integrations, events."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, SoftDelete, Timestamps, UUIDPk, owner_fk, utcnow

APPLICATION_STATUSES = [
    "saved", "analyzing", "matched", "cv_generated", "awaiting_review", "approved", "sent",
    "application_confirmed", "interview", "rejected", "offer", "withdrawn",
]


class Application(Base, UUIDPk, Timestamps, SoftDelete):
    __tablename__ = "applications"
    user_id: Mapped[uuid.UUID] = owner_fk()
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    match_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("job_matches.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(30), default="saved", index=True)
    generation_status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|processing|completed|failed|requires_review
    generation_reason: Mapped[str | None] = mapped_column(String(500))
    tone: Mapped[str] = mapped_column(String(20), default="professional")
    language: Mapped[str] = mapped_column(String(10), default="en")
    qc_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    qc_report: Mapped[dict] = mapped_column(JSONType, default=dict)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    channel: Mapped[str] = mapped_column(String(30), default="")  # email | url_assisted
    notes: Mapped[str] = mapped_column(Text, default="")
    reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64), default="")  # hash of what was approved/previewed
    linkedin_message: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_application_user_job"), Index("ix_app_user_status", "user_id", "status"))


class ApplicationDocument(Base, UUIDPk, Timestamps):
    __tablename__ = "application_documents"
    user_id: Mapped[uuid.UUID] = owner_fk()
    application_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # cv_pdf | cv_docx | cv_tex | cover_letter_pdf | cover_letter_docx
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    storage_key: Mapped[str] = mapped_column(String(300))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    resume_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("resume_versions.id", ondelete="SET NULL"))


class CoverLetter(Base, UUIDPk, Timestamps):
    __tablename__ = "cover_letters"
    user_id: Mapped[uuid.UUID] = owner_fk()
    application_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("applications.id", ondelete="CASCADE"), unique=True)
    tone: Mapped[str] = mapped_column(String(20), default="professional")
    language: Mapped[str] = mapped_column(String(10), default="en")
    body: Mapped[str] = mapped_column(Text, default="")
    grounding: Mapped[dict] = mapped_column(JSONType, default=dict)  # entity ids referenced
    edited_by_user: Mapped[bool] = mapped_column(Boolean, default=False)


class EmailAccount(Base, UUIDPk, Timestamps, SoftDelete):
    """Connected sending account. Tokens/passwords are Fernet-encrypted."""

    __tablename__ = "email_accounts"
    user_id: Mapped[uuid.UUID] = owner_fk()
    provider: Mapped[str] = mapped_column(String(20))  # gmail | outlook | smtp
    address: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(200), default="")
    encrypted_credentials: Mapped[str] = mapped_column(Text)  # JSON blob, encrypted
    scopes: Mapped[list] = mapped_column(JSONType, default=list)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | needs_reauth | revoked
    consent_given_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("user_id", "provider", "address", name="uq_email_account"),)


class Integration(Base, UUIDPk, Timestamps):
    """Generic integration registry (job boards, calendar, etc.). Email accounts have their own table."""

    __tablename__ = "integrations"
    user_id: Mapped[uuid.UUID] = owner_fk()
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="active")
    config: Mapped[dict] = mapped_column(JSONType, default=dict)


class ApplicationEmail(Base, UUIDPk, Timestamps):
    __tablename__ = "application_emails"
    user_id: Mapped[uuid.UUID] = owner_fk()
    application_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    email_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("email_accounts.id", ondelete="SET NULL"))
    to_address: Mapped[str] = mapped_column(String(320), default="")
    subject: Mapped[str] = mapped_column(String(500), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    attachment_doc_ids: Mapped[list] = mapped_column(JSONType, default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|queued|sending|sent|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500))
    provider_message_id: Mapped[str | None] = mapped_column(String(300))
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    edited_by_user: Mapped[bool] = mapped_column(Boolean, default=False)


class ApplicationEvent(Base, UUIDPk):
    """Append-only timeline: status changes, sends, notes."""

    __tablename__ = "application_events"
    user_id: Mapped[uuid.UUID] = owner_fk()
    application_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str | None] = mapped_column(String(30))
    detail: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SendLog(Base, UUIDPk):
    __tablename__ = "send_logs"
    user_id: Mapped[uuid.UUID] = owner_fk()
    application_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    provider: Mapped[str] = mapped_column(String(20))
    recipient: Mapped[str] = mapped_column(String(320))
    success: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
