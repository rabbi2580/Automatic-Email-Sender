"""Identity, subscription, usage, audit."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONType, SoftDelete, Timestamps, UUIDPk, owner_fk, utcnow


class User(Base, UUIDPk, Timestamps, SoftDelete):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    role: Mapped[str] = mapped_column(String(20), default="user")  # user | admin
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    locale: Mapped[str] = mapped_column(String(10), default="en")
    ai_training_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_terms_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_ai_disclosure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    flagged_reason: Mapped[str | None] = mapped_column(String(255))
    settings: Mapped[dict] = mapped_column(JSONType, default=dict)  # weights, thresholds, tone, template...
    verification_token_hash: Mapped[str | None] = mapped_column(String(64))
    password_reset_token_hash: Mapped[str | None] = mapped_column(String(64))
    password_reset_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    profile = relationship("Profile", uselist=False, back_populates="user", cascade="all, delete-orphan")


class RefreshToken(Base, UUIDPk):
    __tablename__ = "refresh_tokens"
    user_id: Mapped[uuid.UUID] = owner_fk()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    family_id: Mapped[str] = mapped_column(String(36), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Subscription(Base, UUIDPk, Timestamps):
    __tablename__ = "subscriptions"
    user_id: Mapped[uuid.UUID] = owner_fk()
    plan: Mapped[str] = mapped_column(String(30), default="free")  # free | pro | business
    status: Mapped[str] = mapped_column(String(20), default="active")
    provider: Mapped[str | None] = mapped_column(String(30))
    provider_ref: Mapped[str | None] = mapped_column(String(120))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("user_id", name="uq_subscription_user"),)


class PlanLimit(Base, UUIDPk, Timestamps):
    """Configurable per-plan limits (never hard-coded)."""

    __tablename__ = "plan_limits"
    plan: Mapped[str] = mapped_column(String(30), index=True)
    metric: Mapped[str] = mapped_column(String(40))  # resumes | job_analyses | ai_generations | emails_sent | cv_versions
    period: Mapped[str] = mapped_column(String(10), default="month")  # month | total
    limit_value: Mapped[int] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint("plan", "metric", name="uq_plan_metric"),)


class UsageRecord(Base, UUIDPk):
    __tablename__ = "usage_records"
    user_id: Mapped[uuid.UUID] = owner_fk()
    metric: Mapped[str] = mapped_column(String(40), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    est_cost_usd_micros: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AuditLog(Base, UUIDPk):
    __tablename__ = "audit_logs"
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
    meta: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Notification(Base, UUIDPk):
    __tablename__ = "notifications"
    user_id: Mapped[uuid.UUID] = owner_fk()
    kind: Mapped[str] = mapped_column(String(40))  # deadline | reminder | qc_blocked | job_failed | sent
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FeatureFlag(Base, UUIDPk, Timestamps):
    __tablename__ = "feature_flags"
    key: Mapped[str] = mapped_column(String(60), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(String(255), default="")


class AIRequestLog(Base, UUIDPk):
    """Metadata only — never prompt/response content."""

    __tablename__ = "ai_request_logs"
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    task: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(80), default="")
    input_chars: Mapped[int] = mapped_column(Integer, default=0)
    output_chars: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    __table_args__ = (Index("ix_ai_logs_task_created", "task", "created_at"),)


class AICache(Base):
    __tablename__ = "ai_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256(task+model+input)
    task: Mapped[str] = mapped_column(String(40))
    value: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
