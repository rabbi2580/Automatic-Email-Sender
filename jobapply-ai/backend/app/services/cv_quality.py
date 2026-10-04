from __future__ import annotations

from app.models import Job, Profile


def ats_score(profile: Profile, job: Job) -> tuple[float, dict]:
    skills = {str(x).lower() for x in (profile.skills or [])}
    # Profile.skills is normally a relationship; accept simple names for tests/fallbacks.
    skills = {getattr(x, "canonical", getattr(x, "name", x)).lower() for x in (profile.skills or [])}
    required = {str(x).lower() for x in (job.required_skills or [])}
    preferred = {str(x).lower() for x in (job.preferred_skills or [])}
    matched = sorted(required & skills)
    missing = sorted(required - skills)
    preferred_hit = sorted(preferred & skills)
    sections = {"name": bool(profile.full_name), "email": bool(profile.email), "summary": bool(profile.summary), "experience": bool(profile.experiences), "education": bool(profile.educations), "skills": bool(skills)}
    section_score = sum(sections.values()) / len(sections) * 100
    skill_score = (len(matched) / len(required) * 100) if required else 100.0
    score = round(skill_score * 0.65 + section_score * 0.25 + min(10, len(preferred_hit) * 2), 1)
    return score, {"matched_keywords": matched, "missing_keywords": missing, "preferred_matches": preferred_hit, "sections": sections,
                   "tips": (["Add a professional summary."] if not profile.summary else []) + (["Add education details."] if not profile.educations else []) + ([f"Consider adding: {', '.join(missing[:8])}"] if missing else [])}
