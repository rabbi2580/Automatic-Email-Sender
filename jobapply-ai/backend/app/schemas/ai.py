"""Pydantic schemas for structured AI outputs. Every LLM response is validated against these."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _str(v):
    return "" if v is None else str(v).strip()


class _Lenient(BaseModel):
    model_config = {"extra": "ignore", "str_strip_whitespace": True}


class SkillItem(_Lenient):
    name: str
    category: str = "technical"


class ExperienceItem(_Lenient):
    kind: Literal["work", "internship", "research", "volunteer"] = "work"
    company: str = ""
    title: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    is_current: bool = False
    bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)

    @field_validator("company", "title", "location", "start_date", "end_date", mode="before")
    @classmethod
    def _s(cls, v):
        return _str(v)


class EducationItem(_Lenient):
    institution: str = ""
    degree: str = ""
    field: str = ""
    level: str = ""
    start_date: str = ""
    end_date: str = ""
    grade: str = ""
    details: list[str] = Field(default_factory=list)

    @field_validator("institution", "degree", "field", "level", "start_date", "end_date", "grade", mode="before")
    @classmethod
    def _s(cls, v):
        return _str(v)


class ProjectItem(_Lenient):
    name: str = ""
    description: str = ""
    bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    url: str = ""
    kind: Literal["project", "research"] = "project"

    @field_validator("name", "description", "url", mode="before")
    @classmethod
    def _s(cls, v):
        return _str(v)


class CertificationItem(_Lenient):
    name: str
    issuer: str = ""
    date: str = ""


class ProfileExtraction(_Lenient):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    headline: str = ""
    summary: str = ""
    links: dict[str, str | list[str]] = Field(default_factory=dict)
    years_experience: float | None = None
    target_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    work_preference: Literal["onsite", "hybrid", "remote", "any"] = "any"
    salary_expectation: str = ""
    work_authorization: str = ""
    other_preferences: str = ""
    skills: list[SkillItem] = Field(default_factory=list)
    experiences: list[ExperienceItem] = Field(default_factory=list)
    educations: list[EducationItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    certifications: list[CertificationItem] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    publications: list[str] = Field(default_factory=list)
    extracurriculars: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)

    @field_validator("full_name", "email", "phone", "location", "headline", "summary", mode="before")
    @classmethod
    def _s(cls, v):
        return _str(v)

    @field_validator("salary_expectation", "work_authorization", "other_preferences", mode="before")
    @classmethod
    def _s_more(cls, v):
        return _str(v)


class JobExtraction(_Lenient):
    company: str = ""
    job_title: str = ""
    department: str = ""
    location: str = ""
    employment_type: str = ""
    workplace_type: str = ""
    salary: str = ""
    min_years: float | None = None
    max_years: float | None = None
    experience_text: str = ""
    education_level: str = ""
    education_fields: list[str] = Field(default_factory=list)
    education_text: str = ""
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    deadline: date | None = None
    application_email: str = ""
    application_url: str = ""
    is_job_posting: bool = True
    warnings: list[str] = Field(default_factory=list)

    @field_validator("company", "job_title", "department", "location", "employment_type", "workplace_type", "salary",
                     "experience_text", "education_level", "education_text", "application_email", "application_url", mode="before")
    @classmethod
    def _s(cls, v):
        return _str(v)

    @field_validator("deadline", mode="before")
    @classmethod
    def _d(cls, v):
        if v in (None, "", "null", "none", "N/A"):
            return None
        return v


class TailorSelection(_Lenient):
    """LLM output for CV tailoring — references profile entities by id only."""

    summary: str = ""
    skill_ids_order: list[str] = Field(default_factory=list)
    experience_ids_order: list[str] = Field(default_factory=list)
    project_ids_order: list[str] = Field(default_factory=list)
    bullet_rewrites: dict[str, list[str]] = Field(default_factory=dict)  # entity_id -> reworded bullets (same facts)


class CoverLetterOut(_Lenient):
    greeting: str = ""
    paragraphs: list[str] = Field(default_factory=list)
    closing: str = ""
    referenced_entity_ids: list[str] = Field(default_factory=list)


class EmailOut(_Lenient):
    subject: str
    body: str
    linkedin_message: str = ""
