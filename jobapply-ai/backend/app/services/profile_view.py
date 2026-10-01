"""Convert ORM profiles/jobs into plain snapshot dicts and matching views. Snapshots carry stable entity ids."""
from __future__ import annotations

from app.models import Job, Profile
from app.services.matching.engine import CandidateView, JobView, LEVEL_RANK
from app.services.parsing.skills import canonicalize


def profile_snapshot(p: Profile) -> dict:
    return {
        "id": str(p.id),
        "full_name": p.full_name, "email": p.email, "phone": p.phone, "location": p.location, "headline": p.headline, "summary": p.summary,
        "links": p.links or {}, "years_experience": p.years_experience, "target_roles": p.target_roles or [],
        "preferred_locations": p.preferred_locations or [], "work_preference": p.work_preference,
        "languages": p.languages or [], "achievements": p.achievements or [], "publications": p.publications or [],
        "extracurriculars": p.extracurriculars or [],
        "skills": [{"id": str(s.id), "name": s.name, "canonical": s.canonical, "category": s.category} for s in p.skills],
        "experiences": [{"id": str(e.id), "kind": e.kind, "company": e.company, "title": e.title, "location": e.location, "start_date": e.start_date,
                         "end_date": e.end_date, "is_current": e.is_current, "bullets": list(e.bullets or []), "technologies": list(e.technologies or [])}
                        for e in p.experiences],
        "educations": [{"id": str(e.id), "institution": e.institution, "degree": e.degree, "field": e.field, "level": e.level,
                        "start_date": e.start_date, "end_date": e.end_date, "grade": e.grade, "details": list(e.details or [])} for e in p.educations],
        "projects": [{"id": str(x.id), "name": x.name, "description": x.description, "bullets": list(x.bullets or []),
                      "technologies": list(x.technologies or []), "url": x.url, "kind": x.kind} for x in p.projects],
        "certifications": [{"id": str(c.id), "name": c.name, "issuer": c.issuer, "date": c.date} for c in p.certifications],
    }


def candidate_view(snap: dict) -> CandidateView:
    skills = {canonicalize(s["canonical"] or s["name"]) for s in snap["skills"]}
    levels = [e["level"] for e in snap["educations"] if e.get("level")]
    top = max(levels, key=lambda l: LEVEL_RANK.get(l, 0)) if levels else ""
    exp_text = " ".join(" ".join(e["bullets"]) + " " + e["title"] for e in snap["experiences"])
    proj_text = " ".join(p["name"] + " " + p["description"] + " " + " ".join(p["bullets"]) for p in snap["projects"])
    return CandidateView(
        skills=skills, years_experience=snap["years_experience"], education_level=top,
        education_text=" ".join(f"{e['degree']} {e['field']} {e['institution']}" for e in snap["educations"]),
        experience_text=exp_text, project_text=proj_text, past_titles=[e["title"] for e in snap["experiences"] if e["title"]],
        headline=snap["headline"], target_roles=snap["target_roles"], location=snap["location"],
        preferred_locations=snap["preferred_locations"], work_preference=snap["work_preference"] or "any",
        has_experience_entries=bool(snap["experiences"]), has_projects=bool(snap["projects"]),
    )


def job_snapshot(j: Job) -> dict:
    return {
        "id": str(j.id), "company_name": j.company_name, "job_title": j.job_title, "department": j.department, "location": j.location,
        "employment_type": j.employment_type, "workplace_type": j.workplace_type, "salary": j.salary,
        "experience_required": j.experience_required or {}, "education_required": j.education_required or {},
        "required_skills": j.required_skills or [], "preferred_skills": j.preferred_skills or [], "tech_stack": j.tech_stack or [],
        "responsibilities": j.responsibilities or [], "deadline": j.deadline.isoformat() if j.deadline else None,
        "application_email": j.application_email, "application_url": j.application_url, "original_content": j.original_content,
    }


def job_view(snap: dict) -> JobView:
    exp, edu = snap["experience_required"], snap["education_required"]
    return JobView(
        title=snap["job_title"], required_skills=[canonicalize(s) for s in snap["required_skills"]],
        preferred_skills=[canonicalize(s) for s in snap["preferred_skills"]], tech_stack=[canonicalize(s) for s in snap["tech_stack"]],
        responsibilities=snap["responsibilities"], min_years=exp.get("min_years"), max_years=exp.get("max_years"),
        education_level=edu.get("level", ""), education_fields=edu.get("fields", []), location=snap["location"], workplace_type=snap["workplace_type"],
    )


def skill_universe(snap: dict) -> set[str]:
    """Every skill the candidate can truthfully claim: listed skills + skills evidenced anywhere in their own CV content."""
    from app.services.parsing.skills import find_skills

    have = {canonicalize(s["canonical"] or s["name"]) for s in snap["skills"]}
    texts = [snap.get("summary", ""), snap.get("headline", "")]
    for e in snap["experiences"]:
        texts += [e["title"], *e["bullets"], *e["technologies"]]
    for p in snap["projects"]:
        texts += [p["name"], p["description"], *p["bullets"], *p["technologies"]]
    for c in snap["certifications"]:
        texts.append(c["name"])
    for e in snap["educations"]:
        texts += [e["degree"], e["field"], *e["details"]]
    texts += snap.get("achievements", []) + snap.get("publications", []) + snap.get("extracurriculars", [])
    for t in texts:
        have |= set(find_skills(t, include_ambiguous_tokens=False))
    have |= {canonicalize(t) for e in snap["experiences"] for t in e["technologies"]}
    have |= {canonicalize(t) for p in snap["projects"] for t in p["technologies"]}
    return have
