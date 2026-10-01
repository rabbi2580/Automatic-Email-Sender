"""Transparent, configurable candidate↔job matching.

Pure functions — no DB, no network. Every dimension returns a score in [0,1], the evidence behind it and a human reason.
Dimensions with no information in the job post are *excluded* and the remaining weights are renormalised, so a sparse
job post never silently drags the score down (and the UI says so).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.parsing.skills import family_of, similarity

DEFAULT_WEIGHTS = {"skills": 30, "experience": 20, "education": 10, "responsibilities": 15, "technology": 10, "role": 10, "location": 5}
DEFAULT_THRESHOLDS = {"strong": 90, "potential": 75, "weak": 60}
DIMENSION_LABELS = {
    "skills": "Skill match", "experience": "Experience match", "education": "Education match", "responsibilities": "Responsibility match",
    "technology": "Technology match", "role": "Role alignment", "location": "Location / work preference",
}
LEVEL_RANK = {"": 0, "secondary": 1, "diploma": 2, "bachelor": 3, "master": 4, "phd": 5}
STOP = set("the and for with that this from will have has are you your our their use using work working ability strong good knowledge experience "
           "understanding skills including etc such able must should team teams new more other into can also well per within across any all one two "
           "develop developing development build building maintain maintaining create creating support supporting ensure ensuring responsible "
           "related relevant plus based role job company candidate candidates years year".split())


@dataclass
class CandidateView:
    skills: set[str]
    years_experience: float | None
    education_level: str  # highest
    education_text: str  # degrees + fields text
    experience_text: str  # bullets + titles
    project_text: str
    past_titles: list[str]
    headline: str
    target_roles: list[str]
    location: str
    preferred_locations: list[str]
    work_preference: str = "any"
    has_experience_entries: bool = False
    has_projects: bool = False


@dataclass
class JobView:
    title: str
    required_skills: list[str]
    preferred_skills: list[str]
    tech_stack: list[str]
    responsibilities: list[str]
    min_years: float | None
    max_years: float | None
    education_level: str
    education_fields: list[str]
    location: str
    workplace_type: str


@dataclass
class DimensionResult:
    key: str
    label: str
    score: float | None  # None → excluded
    weight: float
    reason: str
    evidence: dict = field(default_factory=dict)


def normalise_weights(weights: dict | None) -> dict[str, float]:
    w = {k: float(max(0, (weights or {}).get(k, v))) for k, v in DEFAULT_WEIGHTS.items()}
    if sum(w.values()) <= 0:
        w = {k: float(v) for k, v in DEFAULT_WEIGHTS.items()}
    return w


def normalise_thresholds(t: dict | None) -> dict[str, float]:
    t = {k: float((t or {}).get(k, v)) for k, v in DEFAULT_THRESHOLDS.items()}
    if not (t["strong"] >= t["potential"] >= t["weak"] >= 0):
        return {k: float(v) for k, v in DEFAULT_THRESHOLDS.items()}
    return t


def classify(score: float, thresholds: dict | None = None) -> str:
    t = normalise_thresholds(thresholds)
    if score >= t["strong"]:
        return "strong"
    if score >= t["potential"]:
        return "potential"
    if score >= t["weak"]:
        return "weak"
    return "not_suitable"


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z+#.]{2,}", text.lower()) if w not in STOP}


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s", "ly"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


def _stems(text: str) -> set[str]:
    return {_stem(w) for w in _tokens(text)}


# ---- dimensions --------------------------------------------------------------------------------

def _skills_dim(c: CandidateView, j: JobView, w: float) -> DimensionResult:
    items = [(s, 1.0) for s in j.required_skills] + [(s, 0.5) for s in j.preferred_skills if s not in j.required_skills]
    if not items:
        return DimensionResult("skills", DIMENSION_LABELS["skills"], None, w, "The post lists no specific skills.")
    total = got = 0.0
    strong, partial, missing = [], [], []
    for skill, weight in items:
        sim = similarity(skill, c.skills)
        total += weight
        got += weight * sim
        if sim == 1.0:
            strong.append(skill)
        elif sim > 0:
            partial.append({"skill": skill, "via": sorted(family_of(skill) & c.skills)})
        else:
            missing.append({"skill": skill, "required": skill in j.required_skills})
    score = got / total
    return DimensionResult("skills", DIMENSION_LABELS["skills"], score, w,
                           f"{len(strong)} of {len(items)} listed skills matched exactly, {len(partial)} partially.",
                           {"strong": strong, "partial": partial, "missing": missing})


def _technology_dim(c: CandidateView, j: JobView, w: float) -> DimensionResult:
    stack = list(dict.fromkeys(j.tech_stack))
    if not stack:
        return DimensionResult("technology", DIMENSION_LABELS["technology"], None, w, "No technology stack was detected in the post.")
    sims = [similarity(t, c.skills) for t in stack]
    score = sum(sims) / len(sims)
    matched = [t for t, s in zip(stack, sims) if s == 1.0]
    return DimensionResult("technology", DIMENSION_LABELS["technology"], score, w,
                           f"{len(matched)} of {len(stack)} technologies in the post appear in your profile.",
                           {"matched": matched, "missing": [t for t, s in zip(stack, sims) if s == 0]})


def _experience_dim(c: CandidateView, j: JobView, w: float) -> DimensionResult:
    if j.min_years is None and j.max_years is None:
        return DimensionResult("experience", DIMENSION_LABELS["experience"], None, w, "The post does not state an experience requirement.")
    need = j.min_years or 0.0
    have = c.years_experience
    if need <= 0:
        return DimensionResult("experience", DIMENSION_LABELS["experience"], 1.0, w, "Entry-level role: no minimum experience required.")
    if have is None:
        return DimensionResult("experience", DIMENSION_LABELS["experience"], 0.25 if (c.has_experience_entries or c.has_projects) else 0.0, w,
                               f"Role asks for {need:g}+ years; your years of experience are not stated in your profile.", {"required": need, "have": None})
    if have >= need:
        score, reason = 1.0, f"Meets the minimum: {have:g} years vs {need:g} required."
        if j.max_years and have > j.max_years + 3:
            score, reason = 0.8, f"You have {have:g} years; the role targets up to {j.max_years:g} (may read as over-qualified)."
        return DimensionResult("experience", DIMENSION_LABELS["experience"], score, w, reason, {"required": need, "have": have})
    score = max(0.0, have / need)
    if have == 0 and c.has_projects and need <= 2:
        score = max(score, 0.25)
    return DimensionResult("experience", DIMENSION_LABELS["experience"], min(score, 0.95), w,
                           f"Below the stated minimum: {have:g} years vs {need:g} required.", {"required": need, "have": have})


def _education_dim(c: CandidateView, j: JobView, w: float) -> DimensionResult:
    if not j.education_level and not j.education_fields:
        return DimensionResult("education", DIMENSION_LABELS["education"], None, w, "The post does not state an education requirement.")
    have, need = LEVEL_RANK.get(c.education_level, 0), LEVEL_RANK.get(j.education_level, 0)
    if need == 0:
        level_score = 1.0
    elif have >= need:
        level_score = 1.0
    elif have == need - 1:
        level_score = 0.4
    else:
        level_score = 0.0
    field_note = ""
    if j.education_fields:
        edu_stems = _stems(c.education_text)
        hit = any(_stems(f) & edu_stems or f.lower() in c.education_text.lower() for f in j.education_fields)
        if hit:
            field_note = " Field of study matches."
        else:
            level_score = max(0.0, level_score - 0.25)
            field_note = " Field of study differs from those listed."
    reason = ("Meets the education requirement." if level_score >= 0.99 else "Education level is below or different from the requirement.") + field_note
    return DimensionResult("education", DIMENSION_LABELS["education"], level_score, w, reason,
                           {"required_level": j.education_level, "candidate_level": c.education_level})


def _responsibility_dim(c: CandidateView, j: JobView, w: float) -> DimensionResult:
    if not j.responsibilities:
        return DimensionResult("responsibilities", DIMENSION_LABELS["responsibilities"], None, w, "The post lists no responsibilities.")
    corpus = _stems(c.experience_text + " " + c.project_text + " " + c.headline) | {s.lower() for s in c.skills}
    per = []
    covered = 0
    for r in j.responsibilities:
        toks = _stems(r)
        if not toks:
            continue
        cov = len(toks & corpus) / len(toks)
        per.append(cov)
        covered += cov >= 0.4
    if not per:
        return DimensionResult("responsibilities", DIMENSION_LABELS["responsibilities"], None, w, "Responsibilities could not be analysed.")
    avg = sum(per) / len(per)
    score = min(1.0, avg / 0.5)  # 50 % keyword coverage counts as a full match
    return DimensionResult("responsibilities", DIMENSION_LABELS["responsibilities"], score, w,
                           f"{covered} of {len(per)} responsibilities relate to work or projects in your profile.", {"covered": covered, "total": len(per)})


SENIOR_RX = re.compile(r"\b(senior|sr\.?|lead|principal|staff|head|manager|director|architect)\b", re.I)
SYN = [(r"\bmachine learning\b|\bml\b|\bai\b|\bartificial intelligence\b", "ai_ml"), (r"\bdata scien\w+\b", "data_sci"), (r"\bsoftware\b|\bswe\b|\bdeveloper\b|\bprogrammer\b", "software"),
       (r"\bback[- ]?end\b", "backend"), (r"\bfront[- ]?end\b", "frontend"), (r"\bfull[- ]?stack\b", "fullstack"), (r"\banalyst\b|\banalytics\b", "analyst"),
       (r"\bresearch\w*\b", "research"), (r"\bdevops\b|\bsre\b|\bcloud\b", "devops"), (r"\bsupport\b|\bqa\b|\btest\w*\b", "support_qa"), (r"\bmobile\b|\bandroid\b|\bios\b", "mobile"),
       (r"\bengineer\w*\b", "engineer")]


def _role_tags(text: str) -> set[str]:
    return {tag for rx, tag in SYN if re.search(rx, text, re.I)}


def _role_dim(c: CandidateView, j: JobView, w: float) -> DimensionResult:
    sources = [*c.target_roles, *c.past_titles] + ([c.headline] if c.headline else [])
    if not j.title or not sources:
        return DimensionResult("role", DIMENSION_LABELS["role"], None, w, "Not enough role information to compare.")
    jt = _role_tags(j.title)
    best, best_src = 0.0, ""
    for src in sources:
        st = _role_tags(src)
        if not jt or not st:
            continue
        domain_j, domain_s = jt - {"engineer"}, st - {"engineer"}
        inter, union = len(domain_j & domain_s), len(domain_j | domain_s) or 1
        sc = inter / union if domain_j and domain_s else (0.4 if jt & st else 0.0)
        if sc > best:
            best, best_src = sc, src
    # target roles count more than incidental past titles
    reason = f"Job title '{j.title}' relates to '{best_src}'." if best >= 0.5 else f"Job title '{j.title}' differs from your target roles and past titles."
    ev = {"closest": best_src}
    if SENIOR_RX.search(j.title) and (c.years_experience or 0) < 3:
        best = max(0.0, best - 0.3)
        reason += " The title suggests a senior position."
        ev["seniority_gap"] = True
    return DimensionResult("role", DIMENSION_LABELS["role"], min(1.0, best), w, reason, ev)


def _location_dim(c: CandidateView, j: JobView, w: float) -> DimensionResult:
    if j.workplace_type == "remote":
        return DimensionResult("location", DIMENSION_LABELS["location"], 1.0, w, "Remote role.")
    if not j.location:
        return DimensionResult("location", DIMENSION_LABELS["location"], None, w, "The post does not state a location.")
    jl = _tokens(j.location)
    prefs = [c.location, *c.preferred_locations]
    if any(_tokens(p) & jl for p in prefs if p):
        score, reason = 1.0, f"Location '{j.location}' matches your location/preferences."
    elif not any(prefs):
        return DimensionResult("location", DIMENSION_LABELS["location"], None, w, "Your location preferences are not set.")
    else:
        score, reason = 0.3, f"Location '{j.location}' is outside your listed locations (relocation may be needed)."
    if c.work_preference == "remote" and j.workplace_type in ("onsite", "hybrid", ""):
        score = min(score, 0.3)
        reason += " You prefer remote work."
    return DimensionResult("location", DIMENSION_LABELS["location"], score, w, reason)


# ---- orchestration -----------------------------------------------------------------------------

def compute_match(c: CandidateView, j: JobView, weights: dict | None = None, thresholds: dict | None = None) -> dict:
    w = normalise_weights(weights)
    dims = [
        _skills_dim(c, j, w["skills"]), _experience_dim(c, j, w["experience"]), _education_dim(c, j, w["education"]),
        _responsibility_dim(c, j, w["responsibilities"]), _technology_dim(c, j, w["technology"]), _role_dim(c, j, w["role"]),
        _location_dim(c, j, w["location"]),
    ]
    active = [d for d in dims if d.score is not None and d.weight > 0]
    wsum = sum(d.weight for d in active)
    score = round(sum(d.score * d.weight for d in active) / wsum * 100, 1) if wsum else 0.0
    cls = classify(score, thresholds)

    skills_ev = next(d for d in dims if d.key == "skills").evidence
    tech_ev = next(d for d in dims if d.key == "technology").evidence
    strong = list(dict.fromkeys(skills_ev.get("strong", []) + tech_ev.get("matched", [])))
    partial = skills_ev.get("partial", [])
    missing = skills_ev.get("missing", [])
    concerns: list[str] = []
    for d in dims:
        if d.score is not None and d.score < 0.5 and d.key in ("experience", "education", "role", "location"):
            concerns.append(d.reason)
        if d.evidence.get("seniority_gap"):
            concerns.append("Seniority of the role may exceed your experience.")
    missing_req = [m["skill"] for m in missing if m.get("required")]
    if missing_req:
        concerns.append("Missing required skills: " + ", ".join(missing_req[:8]) + ".")

    lines = [f"Match: {score:g}% ({cls.replace('_', ' ')})"]
    if strong:
        lines.append("Strong matches: " + ", ".join(f"✓ {s}" for s in strong[:12]))
    if partial:
        lines.append("Partial matches: " + ", ".join(f"△ {p['skill']} (you have {', '.join(p['via'])})" for p in partial[:8]))
    if missing:
        lines.append("Missing / not evidenced: " + ", ".join(f"! {m['skill']}" for m in missing[:10]))
    for d in dims:
        mark = "–" if d.score is None else ("✓" if d.score >= 0.8 else "△" if d.score >= 0.5 else "!")
        lines.append(f"{mark} {d.label}: {d.reason}")
    excluded = [d.label for d in dims if d.score is None]
    if excluded:
        lines.append("Not scored (no data in the post): " + ", ".join(excluded) + ". Weights were re-distributed.")
    lines.append("This score is an AI-assisted estimate of fit, not a prediction of the employer's decision.")

    return {
        "score": score, "classification": cls,
        "dimensions": {d.key: {"label": d.label, "score": None if d.score is None else round(d.score, 3), "weight": d.weight,
                               "effective_weight": round(d.weight / wsum, 4) if (wsum and d.score is not None) else 0, "reason": d.reason, "evidence": d.evidence}
                       for d in dims},
        "strong_matches": strong, "partial_matches": partial, "missing": missing, "concerns": list(dict.fromkeys(concerns)),
        "explanation": "\n".join(lines), "weights_used": w, "thresholds_used": normalise_thresholds(thresholds),
    }
