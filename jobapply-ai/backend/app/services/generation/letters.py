"""Cover letter, application email and short-message generation.

Deterministic, fact-grounded templates are always available. When an LLM is configured it drafts the letter from the same facts,
and the output is accepted only if it passes validation (no placeholders, no unsupported skills/numbers, correct company/title).
"""
from __future__ import annotations

import json
import re

from app.schemas.ai import CoverLetterOut, EmailOut
from app.services.ai.safety import wrap_untrusted
from app.services.ai.service import AIService
from app.services.generation.cv_builder import _relevance, _job_keywords
from app.services.parsing.skills import canonicalize, find_skills
from app.services.profile_view import skill_universe

TONES = ("professional", "concise", "technical", "research", "startup")

FRAMES = {
    "en": {
        "greeting": "Dear Hiring Manager,",
        "open": {
            "professional": "I am writing to apply for the {title} position at {company}.",
            "concise": "I am applying for the {title} role at {company}.",
            "technical": "I am applying for the {title} role at {company}, where my hands-on engineering background applies directly.",
            "research": "I am applying for the {title} position at {company} and would like to contribute my research and analytical training.",
            "startup": "I'm excited to apply for the {title} role at {company}.",
        },
        "edu": "My education includes {degree} at {institution}.",
        "exp": "My work at {company} as {title} included: {bullet}",
        "proj": "One relevant project is {name}{desc}. {bullet}",
        "skills": "The role calls for {need}; my background covers {have}.",
        "grow": "I am also keen to develop further in {missing}.",
        "close": {
            "professional": "Thank you for considering my application. I would welcome the opportunity to discuss how I can contribute to {company}.",
            "concise": "Thank you for your time. I would be glad to discuss the role further.",
            "technical": "I would welcome a technical conversation about how my work could support {company}'s team.",
            "research": "I would be glad to discuss how my research experience could support {company}.",
            "startup": "I'd love to chat about how I can help {company} move fast and ship.",
        },
        "sign": "Sincerely,",
    },
    "bn": {
        "greeting": "প্রিয় নিয়োগ কর্তৃপক্ষ,",
        "open": {k: "আমি {company}-এ {title} পদের জন্য আবেদন করছি." for k in TONES},
        "edu": "আমার শিক্ষাগত যোগ্যতা: {degree}, {institution}।",
        "exp": "{company}-এ {title} হিসেবে আমার কাজের মধ্যে ছিল: {bullet}",
        "proj": "একটি প্রাসঙ্গিক প্রজেক্ট হলো {name}{desc}। {bullet}",
        "skills": "এই পদের জন্য প্রয়োজন {need}; আমার অভিজ্ঞতায় রয়েছে {have}।",
        "grow": "আমি {missing} বিষয়ে আরও দক্ষতা অর্জনে আগ্রহী।",
        "close": {k: "আমার আবেদন বিবেচনার জন্য ধন্যবাদ। {company}-এ কীভাবে অবদান রাখতে পারি তা নিয়ে আলোচনার সুযোগ পেলে কৃতজ্ঞ থাকব।" for k in TONES},
        "sign": "বিনীত,",
    },
}
PLACEHOLDER_RX = re.compile(r"(\[[^\]\n]{1,60}\]|\{[^}\n]{1,60}\}|<[^>\n]{1,60}>|\b(lorem ipsum|your name|company name|job title|insert|xxx+|tbd|todo)\b)", re.I)


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _bullet_sentence(b: str) -> str:
    b = b.strip().rstrip(".")
    return b[0].upper() + b[1:] + "." if b else ""


def _lower_first_if_verb(b: str) -> str:
    b = b.strip()
    first = b.split(" ", 1)[0]
    if re.fullmatch(r"[A-Z][a-z]+(?:ed|ing)", first):
        return b[0].lower() + b[1:]
    return b


def analyze_fit(profile: dict, job: dict) -> dict:
    keywords = set(_job_keywords(job))
    have = {canonicalize(s["canonical"] or s["name"]) for s in profile["skills"]}
    req = [canonicalize(s) for s in job["required_skills"]]
    matched = [s for s in req if s in have] or [s for s in _job_keywords(job) if s in have]
    missing = [s for s in req if s not in have]
    exps = sorted(profile["experiences"], key=lambda e: -_relevance(" ".join(e["bullets"] + [e["title"]]), e["technologies"], keywords))
    projs = sorted(profile["projects"], key=lambda p: -_relevance(" ".join([p["name"], p["description"], *p["bullets"]]), p["technologies"], keywords))
    return {"matched": matched, "missing": missing, "experience": exps[0] if exps else None, "project": projs[0] if projs else None,
            "projects": projs[:2]}


def deterministic_cover_letter(profile: dict, job: dict, tone: str = "professional", language: str = "en") -> dict:
    f = FRAMES.get(language, FRAMES["en"])
    tone = tone if tone in TONES else "professional"
    fit = analyze_fit(profile, job)
    company, title = job["company_name"] or "your organization", job["job_title"] or "advertised"
    paras = [f["open"][tone].format(company=company, title=title)]
    edu = next((e for e in profile["educations"] if e["degree"]), None)
    if edu and tone != "concise":
        paras[0] += " " + f["edu"].format(degree=edu["degree"], institution=edu["institution"] or "my university")
    e = fit["experience"]
    if e and e["bullets"]:
        paras.append(f["exp"].format(company=e["company"], title=e["title"], bullet=_lower_first_if_verb(e["bullets"][0]).rstrip(".") + "."))
    projs = fit["projects"] if tone == "research" else fit["projects"][:1]
    for p in projs:
        if p and (p["bullets"] or p["description"]):
            desc = f" ({p['description']})" if p["description"] else ""
            paras.append(f["proj"].format(name=p["name"], desc=desc, bullet=_bullet_sentence(p["bullets"][0]) if p["bullets"] else "").strip())
    if fit["matched"]:
        need = _join(job["required_skills"][:4]) or _join(fit["matched"][:4])
        txt = f["skills"].format(need=need, have=_join(fit["matched"][:6]))
        if fit["missing"] and tone in ("professional", "startup", "technical"):
            txt += " " + f["grow"].format(missing=_join(fit["missing"][:2]))
        paras.append(txt)
    if tone == "concise":
        paras = paras[:3]
    closing = f["close"][tone].format(company=company) + f"\n\n{f['sign']}\n{profile['full_name']}"
    refs = [x["id"] for x in [fit["experience"], *fit["projects"]] if x]
    return {"greeting": f["greeting"], "paragraphs": paras, "closing": closing, "referenced_entity_ids": refs}


def letter_text(letter: dict) -> str:
    return "\n\n".join([letter.get("greeting", ""), *letter.get("paragraphs", []), letter.get("closing", "")]).strip()


def validate_letter(letter: dict, profile: dict, job: dict) -> list[str]:
    """Return a list of problems (empty == OK). Used both to accept LLM output and by QC."""
    text = letter_text(letter)
    problems: list[str] = []
    if PLACEHOLDER_RX.search(text):
        problems.append("Contains a placeholder (e.g. [Company], <name>, TODO).")
    comp = job.get("company_name", "")
    if comp and comp.lower().split()[0] not in text.lower():
        problems.append(f"Does not mention the company '{comp}'.")
    title = job.get("job_title", "")
    if title:
        key = [w for w in re.findall(r"[a-z]{4,}", title.lower()) if w not in {"junior", "senior", "intern"}]
        if key and not any(w in text.lower() for w in key):
            problems.append(f"Does not reference the position '{title}'.")
    have = skill_universe(profile)
    job_skills = {canonicalize(s) for s in [*job["required_skills"], *job["preferred_skills"], *job["tech_stack"]]}
    claimed = set(find_skills(text))
    # skills that appear in the letter but only as the *job's* requirement are allowed in the "need" clause
    unsupported = sorted(s for s in claimed if s not in have and s not in job_skills)
    if unsupported:
        problems.append("Mentions skills not found in your profile: " + ", ".join(unsupported))
    yrs = profile.get("years_experience") or 0
    for m in re.finditer(r"(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)", text, re.I):
        if float(m.group(1)) > yrs + 0.5:
            problems.append(f"Claims {m.group(1)} years of experience but your profile shows {yrs:g}.")
    return problems


def generate_cover_letter(ai: AIService, profile: dict, job: dict, tone: str, language: str) -> tuple[dict, str, list[str]]:
    """Returns (letter, source, validation_problems_of_llm_attempt)."""
    det = lambda: CoverLetterOut(**deterministic_cover_letter(profile, job, tone, language))  # noqa: E731
    if not ai.llm_enabled:
        return det().model_dump(), "heuristic", []
    facts = {"candidate": {"name": profile["full_name"], "skills": [s["name"] for s in profile["skills"]], "years_experience": profile["years_experience"],
                           "education": [{"id": e["id"], "degree": e["degree"], "institution": e["institution"]} for e in profile["educations"]],
                           "experience": [{"id": e["id"], "title": e["title"], "company": e["company"], "bullets": e["bullets"]} for e in profile["experiences"]],
                           "projects": [{"id": p["id"], "name": p["name"], "description": p["description"], "bullets": p["bullets"]} for p in profile["projects"]]}}
    prompt = (f"Write a cover letter in language '{language}', tone '{tone}', 3-4 short paragraphs, specific and non-generic. Use ONLY these facts:\n"
              f"{json.dumps(facts, ensure_ascii=False)}\n\nTarget job (data):\n" +
              wrap_untrusted("job", f"Company: {job['company_name']}\nTitle: {job['job_title']}\nRequired: {', '.join(job['required_skills'])}\n"
                                    f"Responsibilities: {'; '.join(job['responsibilities'][:8])}", 4000) +
              "\nReturn greeting, paragraphs[], closing (sign with the candidate's name) and referenced_entity_ids[].")
    result, src = ai.structured(task="cover_letter", user_prompt=prompt, schema=CoverLetterOut, tier="strong", fallback=det)
    letter = result.model_dump()
    if src != "heuristic":
        problems = validate_letter(letter, profile, job)
        if problems:
            return det().model_dump(), "heuristic", problems
    return letter, src, []


def generate_email(profile: dict, job: dict, tone: str, language: str, include_cover_letter: bool, matched: list[str]) -> dict:
    name, title, company = profile["full_name"], job["job_title"] or "advertised position", job["company_name"] or "your organization"
    if language == "bn":
        subject = f"{title} পদের জন্য আবেদন – {name}"
        lines = ["প্রিয় নিয়োগ কর্তৃপক্ষ,", "", f"{company}-এ {title} পদের জন্য আমার সিভি" + (" ও কভার লেটার" if include_cover_letter else "") + " সংযুক্ত করলাম।"]
        if matched:
            lines += ["", "আমার প্রাসঙ্গিক দক্ষতা: " + ", ".join(matched[:6]) + "।"]
        lines += ["", "আপনার সময়ের জন্য ধন্যবাদ।", "", "বিনীত,", name]
    else:
        subject = f"Application for {title} – {name}"
        lines = ["Dear Hiring Manager,", "", f"Please find attached my CV{' and cover letter' if include_cover_letter else ''} for the {title} position at {company}."]
        if matched:
            lines += ["", f"My background includes {_join(matched[:6])}, which relates directly to the role."]
        lines += ["", "Thank you for your time and consideration. I would be glad to provide any further information.", "", "Best regards,", name]
    contact = [x for x in [profile.get("phone"), (profile.get("links") or {}).get("linkedin")] if x]
    lines += contact
    short = (f"Hello, I recently applied for the {title} role at {company}. I have experience with {_join(matched[:4])}. I'd appreciate the chance to connect."
             if matched else f"Hello, I recently applied for the {title} role at {company} and would appreciate the chance to connect.")
    return {"subject": subject, "body": "\n".join(lines), "linkedin_message": short}
