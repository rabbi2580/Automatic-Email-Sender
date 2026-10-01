"""Grounded CV tailoring.

The tailored CV is assembled from the candidate's own profile entities. The only degrees of freedom are
*selection*, *ordering* and (validated) *rewording* — never new facts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.ai import TailorSelection
from app.services.parsing.skills import canonicalize, find_skills, similarity

PAGE_PROFILES = {
    1: {"skills": 16, "exp_bullets": 3, "proj_bullets": 2, "projects": 3, "achievements": 3, "extras": 2, "certs": 3},
    2: {"skills": 30, "exp_bullets": 6, "proj_bullets": 4, "projects": 6, "achievements": 6, "extras": 4, "certs": 6},
}
ROLE_TYPES = {
    "ai_ml_engineer": r"\b(ai|ml|machine learning|deep learning|nlp|computer vision|llm)\b",
    "data_scientist": r"\bdata scien",
    "data_analyst": r"\b(data|business|bi) analy",
    "backend_developer": r"\bback[- ]?end|\bapi\b|\bserver",
    "frontend_developer": r"\bfront[- ]?end|\bui\b|\breact\b",
    "software_engineer": r"\bsoftware|\bdeveloper|\bprogrammer|\bswe\b|\bfull[- ]?stack",
    "research_assistant": r"\bresearch",
    "devops_engineer": r"\bdevops|\bsre\b|\bcloud",
    "support_qa": r"\bsupport|\bqa\b|\btest",
}
ROLE_LABELS = {
    "ai_ml_engineer": "AI/ML Engineer CV", "data_scientist": "Data Scientist CV", "data_analyst": "Data Analyst CV",
    "backend_developer": "Backend Developer CV", "frontend_developer": "Frontend Developer CV", "software_engineer": "Software Engineer CV",
    "research_assistant": "Research Assistant CV", "devops_engineer": "DevOps Engineer CV", "support_qa": "Support / QA CV", "general": "General CV",
}


def classify_role_type(title: str) -> str:
    for key, rx in ROLE_TYPES.items():
        if re.search(rx, title, re.I):
            return key
    return "general"


def _numbers(s: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", s))


def rewrite_is_safe(original: str, rewrite: str, all_profile_text: str = "") -> bool:
    """A reworded bullet may not introduce skills or numbers that the original did not contain."""
    if not rewrite.strip() or len(rewrite) > 400:
        return False
    if _numbers(rewrite) - _numbers(original):
        return False
    new_skills = set(find_skills(rewrite)) - set(find_skills(original))
    return not new_skills


@dataclass
class BuildOptions:
    template: str = "classic"  # classic | modern | compact
    font: str = "serif"  # serif | sans
    pages: int = 1
    style: str = "conservative"  # conservative | modern
    language: str = "en"


def _job_keywords(job: dict) -> list[str]:
    seen: list[str] = []
    for s in [*job["required_skills"], *job["preferred_skills"], *job["tech_stack"]]:
        c = canonicalize(s)
        if c not in seen:
            seen.append(c)
    return seen


def _relevance(text: str, techs: list[str], keywords: set[str]) -> float:
    found = set(find_skills(text)) | {canonicalize(t) for t in techs}
    exact = len(found & keywords)
    fam = sum(0.5 for k in keywords if k not in found and similarity(k, found) == 0.5)
    toks = set(re.findall(r"[a-z]{4,}", text.lower()))
    return exact + fam + 0.05 * len(toks & keywords_lower(keywords))


def keywords_lower(keywords: set[str]) -> set[str]:
    return {k.lower() for k in keywords}


def default_summary(profile: dict, job: dict, matched: list[str]) -> str:
    """Fact-only summary assembled from education, experience kind/duration and matched skills."""
    edu = next((e for e in profile["educations"] if e["degree"]), None)
    lead = ""
    if edu:
        base = edu["degree"]
        lead = f"{base} graduate" if re.search(r"b\.?\s?sc|bachelor|m\.?\s?sc|master", base, re.I) else base
    elif profile["headline"]:
        lead = profile["headline"]
    yrs = profile["years_experience"]
    has_intern = any(e["kind"] == "internship" for e in profile["experiences"])
    exp = ""
    if yrs and yrs >= 1:
        exp = f"{yrs:g} years of professional experience"
    elif has_intern:
        exp = "internship experience"
    clauses = []
    if lead:
        clauses.append(lead + (f" with {exp}" if exp else ""))
    elif exp:
        clauses.append(exp[0].upper() + exp[1:])
    if matched:
        top = matched[:5]
        skills = ", ".join(top[:-1]) + (" and " if len(top) > 1 else "") + top[-1]
        clauses.append(f"hands-on experience with {skills}")
    text = "; ".join(clauses) if len(clauses) > 1 else (clauses[0] if clauses else "")
    if not text:
        return profile["summary"]
    return text[0].upper() + text[1:] + "."


def build_tailored_cv(profile: dict, job: dict, options: BuildOptions | None = None, selection: TailorSelection | None = None) -> dict:
    opts = options or BuildOptions()
    cfg = PAGE_PROFILES.get(opts.pages, PAGE_PROFILES[1])
    keywords = set(_job_keywords(job))
    prof_skill_by_canon = {canonicalize(s["canonical"] or s["name"]): s for s in profile["skills"]}

    # --- skills: job-relevant first (exact, then same-family), then the rest by category order
    cat_rank = {"language": 0, "framework": 1, "ai_ml": 2, "database": 3, "cloud": 4, "tool": 5, "technical": 6, "soft": 9}
    def skill_key(s):
        c = canonicalize(s["canonical"] or s["name"])
        sim = 0 if c in keywords else (1 if any(similarity(k, {c}) == 0.5 for k in keywords) else 2)
        return (sim, cat_rank.get(s["category"], 7), s["name"].lower())
    ordered = sorted(profile["skills"], key=skill_key)
    if selection and selection.skill_ids_order:  # LLM may reorder, only by existing ids
        by_id = {s["id"]: s for s in profile["skills"]}
        picked = [by_id[i] for i in selection.skill_ids_order if i in by_id]
        ordered = picked + [s for s in ordered if s not in picked]
    # soft skills only on 2-page CVs
    ordered = [s for s in ordered if s["category"] != "soft" or opts.pages == 2]
    skills = [{"id": s["id"], "name": s["name"], "category": s["category"]} for s in ordered[: cfg["skills"]]]
    matched = [s["name"] for s in skills if canonicalize(s["name"]) in keywords]

    # --- experience: keep reverse-chronological order (never reorder dates); choose most relevant bullets
    exp_out = []
    rewrites = (selection.bullet_rewrites if selection else {}) or {}
    for e in profile["experiences"]:
        bl = sorted(e["bullets"], key=lambda b: -_relevance(b, [], keywords))[: cfg["exp_bullets"]]
        # keep original order among chosen bullets for readability
        bl = [b for b in e["bullets"] if b in bl]
        if e["id"] in rewrites:
            cand = rewrites[e["id"]]
            if len(cand) == len(bl) and all(rewrite_is_safe(o, n) for o, n in zip(bl, cand)):
                bl = [n.strip() for n in cand]
        exp_out.append({"id": e["id"], "kind": e["kind"], "company": e["company"], "title": e["title"], "location": e["location"],
                        "start_date": e["start_date"], "end_date": e["end_date"], "is_current": e["is_current"], "bullets": bl})

    # --- projects: most relevant first
    def proj_score(p):
        return _relevance(" ".join([p["name"], p["description"], *p["bullets"]]), p["technologies"], keywords)
    projects = sorted(profile["projects"], key=lambda p: -proj_score(p))
    if selection and selection.project_ids_order:
        by_id = {p["id"]: p for p in profile["projects"]}
        picked = [by_id[i] for i in selection.project_ids_order if i in by_id]
        projects = picked + [p for p in projects if p not in picked]
    proj_out = []
    for p in projects[: cfg["projects"]]:
        bl = [b for b in p["bullets"]][: cfg["proj_bullets"]]
        if p["id"] in rewrites:
            cand = rewrites[p["id"]]
            if len(cand) == len(bl) and all(rewrite_is_safe(o, n) for o, n in zip(bl, cand)):
                bl = [n.strip() for n in cand]
        proj_out.append({"id": p["id"], "name": p["name"], "description": p["description"], "bullets": bl,
                         "technologies": p["technologies"], "url": p["url"], "kind": p["kind"]})

    summary = default_summary(profile, job, matched)
    if selection and selection.summary and _summary_is_safe(selection.summary, profile):
        summary = selection.summary.strip()

    links = profile["links"] or {}
    link_list = [v for k, v in links.items() if k != "other" and isinstance(v, str) and v] + [u for u in links.get("other", [])[:2]]
    cv = {
        "header": {"name": profile["full_name"], "email": profile["email"], "phone": profile["phone"], "location": profile["location"], "links": link_list},
        "headline": profile["headline"],
        "summary": summary,
        "skills": skills,
        "experience": exp_out,
        "education": [{"id": e["id"], "institution": e["institution"], "degree": e["degree"], "field": e["field"], "start_date": e["start_date"],
                       "end_date": e["end_date"], "grade": e["grade"], "details": e["details"][:2]} for e in profile["educations"]],
        "projects": proj_out,
        "certifications": profile["certifications"][: cfg["certs"]],
        "achievements": profile["achievements"][: cfg["achievements"]],
        "publications": profile["publications"][: cfg["extras"]],
        "languages": profile["languages"],
        "extracurriculars": profile["extracurriculars"][: cfg["extras"]],
        "meta": {"job_id": job["id"], "target_title": job["job_title"], "target_company": job["company_name"],
                 "role_type": classify_role_type(job["job_title"]), "keywords_matched": matched, "options": opts.__dict__},
    }
    return cv


def _summary_is_safe(summary: str, profile: dict) -> bool:
    if len(summary) > 600:
        return False
    prof_skills = {canonicalize(s["canonical"] or s["name"]) for s in profile["skills"]}
    if set(find_skills(summary)) - prof_skills:
        return False
    allowed_nums = _numbers(str(profile["years_experience"] or "")) | _numbers(" ".join(e["grade"] for e in profile["educations"]))
    allowed_nums |= _numbers(" ".join(e["start_date"] + e["end_date"] for e in profile["educations"] + profile["experiences"]))
    return not (_numbers(summary) - allowed_nums)


def shrink(cv: dict, level: int) -> dict:
    """Progressively trim content so a CV fits its page limit. Only removes items; never adds."""
    import copy

    out = copy.deepcopy(cv)
    if level >= 1:
        for e in out["experience"]:
            e["bullets"] = e["bullets"][: max(2, len(e["bullets"]) - 1)]
        out["projects"] = out["projects"][:3]
    if level >= 2:
        out["skills"] = out["skills"][:14]
        out["achievements"] = out["achievements"][:2]
        out["extracurriculars"] = []
        out["publications"] = out["publications"][:1]
        for p in out["projects"]:
            p["bullets"] = p["bullets"][:1]
    if level >= 3:
        out["projects"] = out["projects"][:2]
        out["certifications"] = out["certifications"][:2]
        for e in out["experience"]:
            e["bullets"] = e["bullets"][:2]
    if level >= 4:
        out["achievements"], out["publications"], out["languages"] = [], [], out["languages"][:3]
        out["summary"] = out["summary"][:240].rsplit(" ", 1)[0] + "." if len(out["summary"]) > 240 else out["summary"]
    return out
