"""Jobs, sources, companies, matches."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONType, SoftDelete, Timestamps, UUIDPk, owner_fk, utcnow


class Company(Base, UUIDPk, Timestamps):
    """Per-user company record with provenance for every field."""

    __tablename__ = "companies"
    user_id: Mapped[uuid.UUID] = owner_fk()
    name: Mapped[str] = mapped_column(String(200))
    normalized_name: Mapped[str] = mapped_column(String(200), index=True)
    website: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    industry: Mapped[str] = mapped_column(String(120), default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    size: Mapped[str] = mapped_column(String(60), default="")
    # {"website": {"value": "...", "source": "job_post|public_source|ai_inference", "url": "..."}}
    provenance: Mapped[dict] = mapped_column(JSONType, default=dict)
    __table_args__ = (UniqueConstraint("user_id", "normalized_name", name="uq_company_user_name"),)


class JobSource(Base, UUIDPk):
    """How a job entered the system (raw intake record)."""

    __tablename__ = "job_sources"
    user_id: Mapped[uuid.UUID] = owner_fk()
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    kind: Mapped[str] = mapped_column(String(20))  # text | url | email | image | pdf | docx
    raw_text: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(String(1000), default="")
    file_key: Mapped[str | None] = mapped_column(String(300))
    filename: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Job(Base, UUIDPk, Timestamps, SoftDelete):
    __tablename__ = "jobs"
    user_id: Mapped[uuid.UUID] = owner_fk()
    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("job_sources.id", ondelete="SET NULL"))
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("companies.id", ondelete="SET NULL"))
    company_name: Mapped[str] = mapped_column(String(200), default="")
    job_title: Mapped[str] = mapped_column(String(300), default="")
    department: Mapped[str] = mapped_column(String(200), default="")
    location: Mapped[str] = mapped_column(String(300), default="")
    employment_type: Mapped[str] = mapped_column(String(30), default="")  # full_time|part_time|contract|internship|...
    workplace_type: Mapped[str] = mapped_column(String(20), default="")  # onsite|hybrid|remote
    salary: Mapped[str] = mapped_column(String(200), default="")
    experience_required: Mapped[dict] = mapped_column(JSONType, default=dict)  # {"min_years":1,"max_years":3,"text":""}
    education_required: Mapped[dict] = mapped_column(JSONType, default=dict)  # {"level":"bachelor","fields":[],"text":""}
    required_skills: Mapped[list] = mapped_column(JSONType, default=list)
    preferred_skills: Mapped[list] = mapped_column(JSONType, default=list)
    responsibilities: Mapped[list] = mapped_column(JSONType, default=list)
    benefits: Mapped[list] = mapped_column(JSONType, default=list)
    tech_stack: Mapped[list] = mapped_column(JSONType, default=list)
    deadline: Mapped[date | None] = mapped_column(Date, index=True)
    application_email: Mapped[str] = mapped_column(String(320), default="")
    application_url: Mapped[str] = mapped_column(String(1000), default="")
    source: Mapped[str] = mapped_column(String(30), default="")
    source_url: Mapped[str] = mapped_column(String(1000), default="")
    original_content: Mapped[str] = mapped_column(Text, default="")
    extracted_information: Mapped[dict] = mapped_column(JSONType, default=dict)  # field confidences, warnings, provenance
    content_hash: Mapped[str] = mapped_column(String(64), index=True, default="")
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|processing|completed|failed|requires_review
    status_reason: Mapped[str | None] = mapped_column(String(500))
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    duplicate_score: Mapped[float | None] = mapped_column(Float)
    ats_score: Mapped[float | None] = mapped_column(Float)
    ats_report: Mapped[dict] = mapped_column(JSONType, default=dict)
    __table_args__ = (Index("ix_jobs_user_deadline", "user_id", "deadline"), Index("ix_jobs_user_created", "user_id", "created_at"))


class JobMatch(Base, UUIDPk, Timestamps):
    __tablename__ = "job_matches"
    user_id: Mapped[uuid.UUID] = owner_fk()
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    profile_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("profiles.id", ondelete="CASCADE"))
    score: Mapped[float] = mapped_column(Float)
    classification: Mapped[str] = mapped_column(String(20))  # strong|potential|weak|not_suitable
    dimensions: Mapped[dict] = mapped_column(JSONType, default=dict)  # per-dimension score/weight/evidence
    strong_matches: Mapped[list] = mapped_column(JSONType, default=list)
    partial_matches: Mapped[list] = mapped_column(JSONType, default=list)
    missing: Mapped[list] = mapped_column(JSONType, default=list)
    concerns: Mapped[list] = mapped_column(JSONType, default=list)
    explanation: Mapped[str] = mapped_column(Text, default="")
    weights_used: Mapped[dict] = mapped_column(JSONType, default=dict)
    thresholds_used: Mapped[dict] = mapped_column(JSONType, default=dict)
    __table_args__ = (UniqueConstraint("job_id", "profile_id", name="uq_match_job_profile"),)
