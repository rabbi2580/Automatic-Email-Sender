"""Candidate profile (structured), resumes (original files), tailored CV versions."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONType, SoftDelete, Timestamps, UUIDPk, owner_fk, utcnow


class Profile(Base, UUIDPk, Timestamps):
    __tablename__ = "profiles"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    email: Mapped[str] = mapped_column(String(320), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    headline: Mapped[str] = mapped_column(String(300), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    links: Mapped[dict] = mapped_column(JSONType, default=dict)  # linkedin, github, portfolio, other[]
    years_experience: Mapped[float | None] = mapped_column(Float)
    target_roles: Mapped[list] = mapped_column(JSONType, default=list)
    preferred_locations: Mapped[list] = mapped_column(JSONType, default=list)
    work_preference: Mapped[str] = mapped_column(String(20), default="any")  # onsite | hybrid | remote | any
    salary_expectation: Mapped[str] = mapped_column(String(100), default="")
    work_authorization: Mapped[str] = mapped_column(String(200), default="")
    other_preferences: Mapped[str] = mapped_column(Text, default="")
    languages: Mapped[list] = mapped_column(JSONType, default=list)
    strengths: Mapped[list] = mapped_column(JSONType, default=list)
    achievements: Mapped[list] = mapped_column(JSONType, default=list)
    extracurriculars: Mapped[list] = mapped_column(JSONType, default=list)
    publications: Mapped[list] = mapped_column(JSONType, default=list)
    reference_contacts: Mapped[list] = mapped_column(JSONType, default=list)
    source_resume_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("resumes.id", ondelete="SET NULL"))
    user = relationship("User", back_populates="profile")
    skills = relationship("Skill", cascade="all, delete-orphan", back_populates="profile")
    experiences = relationship("Experience", cascade="all, delete-orphan", back_populates="profile", order_by="Experience.sort_order")
    educations = relationship("Education", cascade="all, delete-orphan", back_populates="profile", order_by="Education.sort_order")
    projects = relationship("Project", cascade="all, delete-orphan", back_populates="profile", order_by="Project.sort_order")
    certifications = relationship("Certification", cascade="all, delete-orphan", back_populates="profile")


class Skill(Base, UUIDPk):
    __tablename__ = "skills"
    user_id: Mapped[uuid.UUID] = owner_fk()
    profile_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    canonical: Mapped[str] = mapped_column(String(100), index=True)
    category: Mapped[str] = mapped_column(String(30), default="technical")  # language|framework|cloud|ai_ml|database|tool|soft|technical
    level: Mapped[str | None] = mapped_column(String(20))
    profile = relationship("Profile", back_populates="skills")


class Experience(Base, UUIDPk):
    __tablename__ = "experience"
    user_id: Mapped[uuid.UUID] = owner_fk()
    profile_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="work")  # work | internship | research | volunteer
    company: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    location: Mapped[str] = mapped_column(String(200), default="")
    start_date: Mapped[str] = mapped_column(String(20), default="")  # kept as text exactly as in CV (e.g. "Jun 2026")
    end_date: Mapped[str] = mapped_column(String(20), default="")  # "" + is_current for ongoing
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    bullets: Mapped[list] = mapped_column(JSONType, default=list)
    technologies: Mapped[list] = mapped_column(JSONType, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    profile = relationship("Profile", back_populates="experiences")


class Education(Base, UUIDPk):
    __tablename__ = "education"
    user_id: Mapped[uuid.UUID] = owner_fk()
    profile_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    institution: Mapped[str] = mapped_column(String(200))
    degree: Mapped[str] = mapped_column(String(200), default="")
    field: Mapped[str] = mapped_column(String(200), default="")
    level: Mapped[str] = mapped_column(String(20), default="")  # diploma | bachelor | master | phd | other
    start_date: Mapped[str] = mapped_column(String(20), default="")
    end_date: Mapped[str] = mapped_column(String(20), default="")
    grade: Mapped[str] = mapped_column(String(60), default="")
    details: Mapped[list] = mapped_column(JSONType, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    profile = relationship("Profile", back_populates="educations")


class Project(Base, UUIDPk):
    __tablename__ = "projects"
    user_id: Mapped[uuid.UUID] = owner_fk()
    profile_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    bullets: Mapped[list] = mapped_column(JSONType, default=list)
    technologies: Mapped[list] = mapped_column(JSONType, default=list)
    url: Mapped[str] = mapped_column(String(500), default="")
    kind: Mapped[str] = mapped_column(String(20), default="project")  # project | research
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    profile = relationship("Profile", back_populates="projects")


class Certification(Base, UUIDPk):
    __tablename__ = "certifications"
    user_id: Mapped[uuid.UUID] = owner_fk()
    profile_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    issuer: Mapped[str] = mapped_column(String(200), default="")
    date: Mapped[str] = mapped_column(String(20), default="")
    profile = relationship("Profile", back_populates="certifications")


class Resume(Base, UUIDPk, Timestamps, SoftDelete):
    """The user's ORIGINAL uploaded master CV. Never modified."""

    __tablename__ = "resumes"
    user_id: Mapped[uuid.UUID] = owner_fk()
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(300))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|processing|completed|failed|requires_review
    status_reason: Mapped[str | None] = mapped_column(String(500))
    is_master: Mapped[bool] = mapped_column(Boolean, default=True)
    label: Mapped[str] = mapped_column(String(100), default="Master CV")
    parse_quality: Mapped[dict] = mapped_column(JSONType, default=dict)
    correction_feedback: Mapped[list] = mapped_column(JSONType, default=list)


class ResumeVersion(Base, UUIDPk, Timestamps):
    """Generated, tailored CV versions (per role type or per application)."""

    __tablename__ = "resume_versions"
    user_id: Mapped[uuid.UUID] = owner_fk()
    resume_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("resumes.id", ondelete="SET NULL"))
    application_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    label: Mapped[str] = mapped_column(String(120), default="")
    role_type: Mapped[str] = mapped_column(String(60), default="")  # ai_ml_engineer, software_engineer, ...
    content: Mapped[dict] = mapped_column(JSONType)  # structured tailored CV (entity-id grounded)
    template: Mapped[str] = mapped_column(String(30), default="classic")
    options: Mapped[dict] = mapped_column(JSONType, default=dict)
    pdf_key: Mapped[str | None] = mapped_column(String(300))
    docx_key: Mapped[str | None] = mapped_column(String(300))
    tex_key: Mapped[str | None] = mapped_column(String(300))
    content_hash: Mapped[str] = mapped_column(String(64), default="")
