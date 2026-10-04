from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class ORM(BaseModel):
    model_config = {"from_attributes": True}


# ---- auth
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(default="", max_length=200)
    accept_terms: bool
    locale: Literal["en", "bn"] = "en"


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshIn(BaseModel):
    refresh_token: str


class VerifyEmailIn(BaseModel):
    token: str


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str = Field(min_length=10, max_length=128)


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)


class UserOut(ORM):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    email_verified: bool
    locale: str
    ai_training_opt_in: bool
    created_at: datetime


class UserPatch(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    locale: Literal["en", "bn"] | None = None


# ---- profile
class ProfilePatch(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    headline: str | None = None
    summary: str | None = None
    links: dict[str, Any] | None = None
    years_experience: float | None = Field(default=None, ge=0, le=60)
    target_roles: list[str] | None = None
    preferred_locations: list[str] | None = None
    work_preference: Literal["onsite", "hybrid", "remote", "any"] | None = None
    salary_expectation: str | None = None
    work_authorization: str | None = None
    other_preferences: str | None = None
    languages: list[str] | None = None


# ---- jobs
class JobTextIn(BaseModel):
    kind: Literal["text", "url", "email"] = "text"
    text: str | None = Field(default=None, max_length=60_000)
    url: str | None = Field(default=None, max_length=1000)
    split: bool = True  # split pasted blobs containing several posts


class JobBulkIn(BaseModel):
    items: list[JobTextIn] = Field(min_length=1, max_length=100)


class JobPatch(BaseModel):
    company_name: str | None = None
    job_title: str | None = None
    location: str | None = None
    employment_type: str | None = None
    workplace_type: str | None = None
    salary: str | None = None
    required_skills: list[str] | None = None
    preferred_skills: list[str] | None = None
    tech_stack: list[str] | None = None
    responsibilities: list[str] | None = None
    application_email: str | None = None
    application_url: str | None = None
    deadline: date | None = None
    min_years: float | None = None
    max_years: float | None = None
    education_level: str | None = None


class JobAnalyzeIn(BaseModel):
    job_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


# ---- applications
class GenerateIn(BaseModel):
    job_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    tone: Literal["professional", "concise", "technical", "research", "startup"] | None = None
    language: Literal["en", "bn"] | None = None
    template: Literal["classic", "modern", "compact"] | None = None
    font: Literal["serif", "sans"] | None = None
    pages: Literal[1, 2] | None = None
    include_cover_letter: bool | None = None


class RegenerateIn(BaseModel):
    tone: Literal["professional", "concise", "technical", "research", "startup"] | None = None
    language: Literal["en", "bn"] | None = None
    template: Literal["classic", "modern", "compact"] | None = None
    font: Literal["serif", "sans"] | None = None
    pages: Literal[1, 2] | None = None
    include_cover_letter: bool | None = None


class CoverLetterPatch(BaseModel):
    body: str = Field(min_length=20, max_length=8000)


class EmailPatch(BaseModel):
    to_address: str | None = Field(default=None, max_length=320)
    subject: str | None = Field(default=None, max_length=500)
    body: str | None = Field(default=None, max_length=10_000)
    attachment_doc_ids: list[uuid.UUID] | None = None
    email_account_id: uuid.UUID | None = None


class ApplicationPatch(BaseModel):
    status: str | None = None
    notes: str | None = Field(default=None, max_length=5000)
    reminder_at: datetime | None = None


class BulkApproveIn(BaseModel):
    application_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class SendPreviewIn(BaseModel):
    application_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    follow_up_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)


class SendIn(BaseModel):
    application_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    follow_up_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    confirmation_token: str
    confirm: bool


# ---- email accounts
class EmailConnectIn(BaseModel):
    provider: Literal["gmail", "outlook"]
    consent: bool
    tracking: bool = False


class SmtpConnectIn(BaseModel):
    address: EmailStr
    display_name: str = ""
    host: str = Field(min_length=3, max_length=255)
    port: int = Field(default=587, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=500)
    security: Literal["starttls", "ssl", "none"] = "starttls"
    consent: bool


class SettingsIn(BaseModel):
    weights: dict[str, float] | None = None
    thresholds: dict[str, float] | None = None
    tone: Literal["professional", "concise", "technical", "research", "startup"] | None = None
    language: Literal["en", "bn"] | None = None
    cv_template: Literal["classic", "modern", "compact"] | None = None
    cv_font: Literal["serif", "sans"] | None = None
    cv_pages: Literal[1, 2] | None = None
    cv_style: Literal["conservative", "modern"] | None = None
    include_cover_letter: bool | None = None
    reminder_days_before_deadline: int | None = Field(default=None, ge=0, le=30)
    mailbox_tracking: bool | None = None


    @field_validator("weights")
    @classmethod
    def _w(cls, v):
        if v is None:
            return v
        allowed = {"skills", "experience", "education", "responsibilities", "technology", "role", "location"}
        if set(v) - allowed:
            raise ValueError(f"Unknown weight keys: {sorted(set(v) - allowed)}")
        if any(x < 0 or x > 100 for x in v.values()):
            raise ValueError("Weights must be between 0 and 100")
        return v

    @field_validator("thresholds")
    @classmethod
    def _t(cls, v):
        if v is None:
            return v
        if set(v) - {"strong", "potential", "weak"}:
            raise ValueError("Thresholds keys: strong, potential, weak")
        s_, p_, w_ = (v.get(k) for k in ("strong", "potential", "weak"))
        vals = [x for x in (s_, p_, w_) if x is not None]
        if any(x < 0 or x > 100 for x in vals):
            raise ValueError("Thresholds must be between 0 and 100")
        if None not in (s_, p_, w_) and not (s_ >= p_ >= w_):
            raise ValueError("Thresholds must satisfy strong >= potential >= weak")
        return v


class FollowUpRuleIn(BaseModel):
    default_wait_days: int = Field(default=7, ge=1, le=90)
    max_followups: int = Field(default=2, ge=0, le=5)
    stop_on_reply: bool = True
    enabled: bool = True


class FollowUpPatch(BaseModel):
    subject: str | None = Field(default=None, max_length=500)
    body: str | None = Field(default=None, min_length=20, max_length=8000)


class DeleteAccountIn(BaseModel):
    password: str | None = None
    confirm: Literal["DELETE MY ACCOUNT"]


class TrainingOptIn(BaseModel):
    opt_in: bool
