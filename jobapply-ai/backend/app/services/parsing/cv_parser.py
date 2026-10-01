"""Heuristic (rule-based) CV → ProfileExtraction. Deterministic fallback for the LLM extraction agent.

Everything returned is copied/normalised from the CV text; nothing is invented.
"""
from __future__ import annotations

import re
from datetime import date

from app.schemas.ai import (
    CertificationItem, EducationItem, ExperienceItem, ProfileExtraction, ProjectItem, SkillItem,
)
from app.services.parsing.skills import canonicalize, category_of, find_skills

SECTION_ALIASES = {
    "contact": ["personal information contact information", "personal information", "contact information", "contact details"],
    "summary": ["summary", "professional summary", "professional summary career objective", "profile", "objective", "career objective", "about me", "about"],
    "education": ["education", "academic background", "academic qualifications", "educational qualification", "educational qualifications", "academics"],
    "experience": ["experience", "work experience", "professional experience", "employment", "employment history", "work history"],
    "internship": ["internship", "internships", "internship experience"],
    "volunteer_experience": ["volunteer experience", "volunteering experience"],
    "projects": ["projects", "academic projects", "personal projects", "selected projects", "key projects", "project experience"],
    "research": ["research", "research experience", "research projects"],
    "publications": ["publications", "papers", "research papers", "selected publications", "research publications"],
    "skills": ["skills", "technical skills", "key skills", "core competencies", "skills & tools", "skills and tools", "technologies", "tech stack", "technical expertise"],
    "certifications": ["certifications", "certificates", "licenses & certifications", "courses", "training", "licenses and certifications",
                       "certifications courses", "certifications & professional training", "certifications and professional training"],
    "achievements": ["achievements", "awards", "honors", "honours", "achievements awards", "awards & achievements", "awards and honors", "accomplishments", "scholarships"],
    "languages": ["languages", "language proficiency"],
    "extracurricular": ["extracurricular", "extracurricular activities", "extra curricular activities", "extra-curricular activities",
                        "activities", "volunteer", "volunteering", "leadership", "co-curricular activities"],
    "strengths": ["strengths & interests", "strengths and interests", "strengths interests", "strengths", "interests"],
    "references": ["references"],
}
_HEADER_LOOKUP = {a: sec for sec, al in SECTION_ALIASES.items() for a in al}

BULLET_RE = re.compile(r"^\s*([•·▪■◦●\-–—*>]|\d+[.)])\s+")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)(\+?\d[\d\s().\-]{8,16}\d)(?!\d)")
URL_RE = re.compile(r"(?:https?://|www\.)[^\s,;|)>\]]+|(?:linkedin\.com|github\.com|gitlab\.com|kaggle\.com|huggingface\.co)/[^\s,;|)>\]]+", re.I)
_MON = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_DATE = rf"(?:{_MON}\.?\s*,?\s*\d{{4}}|\d{{1,2}}/\d{{4}}|\d{{4}})"
DATE_RANGE_RE = re.compile(rf"({_DATE})\s*(?:[-–—]|to|until)\s*({_DATE}|Present|Current|Now|Ongoing|Today)", re.I)
SINGLE_DATE_RE = re.compile(rf"\b({_DATE})\b", re.I)
GRADE_RE = re.compile(r"\b(?:CGPA|GPA|CPI|Grade|Percentage|Score)\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?(?:\s*/\s*[0-9]+(?:\.[0-9]+)?)?\s*%?)", re.I)
TITLE_WORDS = re.compile(
    r"\b(engineer|developer|intern|internship|analyst|scientist|manager|assistant|researcher|officer|consultant|lead|designer|architect|"
    r"specialist|executive|trainee|associate|administrator|coordinator|director|programmer|tester|technician|instructor|tutor|fellow|founder|co-founder)\b", re.I)
INSTITUTION_RE = re.compile(r"\b(university|college|institute|school|academy|polytechnic|iut|aiub|buet|bracu|nsu|iub|cuet|kuet|ruet|madrasa)\b", re.I)
DEGREE_RE = re.compile(
    r"\b(b\.?\s?sc\.?|m\.?\s?sc\.?|b\.?\s?tech|m\.?\s?tech|b\.?\s?e\.?|m\.?\s?s\.?|b\.?\s?a\.?|m\.?\s?a\.?|bba|mba|ph\.?d|bachelor(?:'s)?|master(?:'s)?|"
    r"doctorate|diploma|hsc|ssc|higher secondary|secondary school|a[- ]levels?|o[- ]levels?|associate degree)\b", re.I)
LEVELS = [
    (re.compile(r"ph\.?d|doctorate", re.I), "phd"),
    (re.compile(r"\bm\.?\s?sc|master|\bm\.?\s?tech|\bmba\b|\bm\.?\s?s\b", re.I), "master"),
    (re.compile(r"\bb\.?\s?sc|bachelor|\bb\.?\s?tech|\bbba\b|\bb\.?\s?e\b|\bb\.?\s?a\b", re.I), "bachelor"),
    (re.compile(r"diploma", re.I), "diploma"),
    (re.compile(r"hsc|ssc|higher secondary|secondary|a[- ]level|o[- ]level", re.I), "secondary"),
]


def _normalize_cv_text(text: str) -> str:
    if not text:
        return text
    replacements = {
        "â€“": "-",
        "â€”": "-",
        "–": "-",
        "—": "-",
        "−": "-",
        "‒": "-",
        "―": "-",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text


def _is_bullet(line: str) -> bool:
    return bool(BULLET_RE.match(line))


def _strip_bullet(line: str) -> str:
    return BULLET_RE.sub("", line, count=1).strip()


def detect_header(line: str) -> str | None:
    s = line.strip().strip(":").strip()
    if not s or len(s) > 45 or _is_bullet(line):
        return None
    key = re.sub(r"[^a-z&\- ]", "", s.lower()).strip()
    key = re.sub(r"\s+", " ", key)
    return _HEADER_LOOKUP.get(key)


def split_sections(text: str) -> tuple[list[str], dict[str, list[str]]]:
    header: list[str] = []
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.split("\n"):
        line = raw.rstrip()
        sec = detect_header(line)
        if sec:
            current = sec
            sections.setdefault(sec, [])
            continue
        if current is None:
            header.append(line)
        else:
            sections[current].append(line)
    return header, sections


def _parse_range(s: str) -> tuple[str, str, bool, str]:
    """Return (start, end, is_current, remaining_text)."""
    m = DATE_RANGE_RE.search(s)
    if m:
        end = m.group(2)
        cur = bool(re.fullmatch(r"present|current|now|ongoing|today", end.strip(), re.I))
        rest = (s[: m.start()] + " " + s[m.end():]).strip()
        return m.group(1).strip(), ("" if cur else end.strip()), cur, rest
    m = SINGLE_DATE_RE.search(s)
    if m and len(s) < 60 + len(m.group(0)):
        rest = (s[: m.start()] + " " + s[m.end():]).strip()
        return "", m.group(1).strip(), False, rest
    return "", "", False, s


def _clean_piece(p: str) -> str:
    p = re.sub(r"\s+", " ", p).strip(" |,;–—-•·")
    # strip only *unbalanced* brackets so "AIUB (Dhaka)" survives but "(Native" / "Name)" are repaired
    while p.startswith("(") and p.count("(") > p.count(")"):
        p = p[1:].strip()
    while p.endswith(")") and p.count(")") > p.count("("):
        p = p[:-1].strip()
    if p.count("(") > p.count(")"):
        p += ")"
    return p.strip(" []")


def _split_header_pieces(s: str) -> list[str]:
    parts = re.split(r"\s+[|•·]\s+|\s+[–—]\s+|\s+-\s+|\s+@\s+|\s+at\s+|\t+|,\s+(?=[A-Z])", s)
    return [p for p in (_clean_piece(x) for x in parts) if p]


def _group_entries(lines: list[str]) -> list[dict]:
    entries: list[dict] = []
    cur: dict = {"head": [], "bullets": []}

    def push():
        nonlocal cur
        if cur["head"] or cur["bullets"]:
            entries.append(cur)
        cur = {"head": [], "bullets": []}

    for raw in lines:
        line = raw.strip()
        if not line:
            if cur["bullets"]:
                push()
            continue
        if _is_bullet(raw):
            cur["bullets"].append(_strip_bullet(raw))
        elif cur["bullets"] and (line[0].islower() or not DATE_RANGE_RE.search(line) and not TITLE_WORDS.search(line) and len(line) > 60):
            cur["bullets"][-1] += " " + line  # wrapped bullet continuation
        elif cur["bullets"]:
            push()
            cur["head"].append(line)
        elif len(cur["head"]) >= 3:
            push()
            cur["head"].append(line)
        else:
            cur["head"].append(line)
    push()
    return entries


def _is_experience_heading(line: str) -> bool:
    text = _strip_bullet(line)
    if not text or _is_bullet(line) or len(text) > 140 or URL_RE.search(text) or EMAIL_RE.search(text):
        return False
    if not TITLE_WORDS.search(text):
        return False
    return bool(DATE_RANGE_RE.search(text) or re.search(r"[|,@]|\bat\b", text, re.I)) or (
        len(text.split()) <= 6 and not re.search(r"[.!?]", text)
    )


def _parse_experience(lines: list[str], default_kind: str = "work") -> list[ExperienceItem]:
    entries: list[dict] = []
    current: dict | None = None

    def push() -> None:
        nonlocal current
        if current:
            entries.append(current)
        current = None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if _is_experience_heading(raw):
            push()
            current = {"head": [line], "bullets": []}
        elif current:
            if DATE_RANGE_RE.search(line) and not any(DATE_RANGE_RE.search(part) for part in current["head"]):
                current["head"].append(line)
            else:
                current["bullets"].append(_strip_bullet(raw))
    push()

    out: list[ExperienceItem] = []
    for entry in entries:
        head = " | ".join(entry["head"])
        start, end, cur, rest = _parse_range(head)
        pieces = _split_header_pieces(rest)
        title = company = location = ""
        for piece in pieces:
            if not title and TITLE_WORDS.search(piece):
                title = piece
            elif not company:
                company = piece
            elif not location:
                location = piece
        if not title and pieces:
            title = pieces[0]
            company = pieces[1] if len(pieces) > 1 else company
        if not (title or company):
            continue
        kind = "internship" if re.search(r"intern", f"{title} {company}", re.I) else default_kind
        text = " ".join(entry["bullets"] + [head])
        out.append(ExperienceItem(kind=kind, company=company, title=title, location=location, start_date=start, end_date=end,
                                  is_current=cur, bullets=entry["bullets"], technologies=find_skills(text)))
    return out


def _level_of(text: str) -> str:
    for rx, lvl in LEVELS:
        if rx.search(text):
            return lvl
    return ""


def _parse_education(lines: list[str]) -> list[EducationItem]:
    out: list[EducationItem] = []
    for e in _group_entries(lines):
        block = " | ".join(e["head"] + e["bullets"])
        if not block.strip():
            continue
        start, end, _cur, _ = _parse_range(block)
        gm = GRADE_RE.search(block)
        inst = ""
        degree = ""
        for ln in e["head"]:
            for piece in _split_header_pieces(ln) + [ln]:
                if not inst and INSTITUTION_RE.search(piece):
                    inst = _clean_piece(DATE_RANGE_RE.sub("", piece))
                if not degree and DEGREE_RE.search(piece):
                    degree = _clean_piece(GRADE_RE.sub("", DATE_RANGE_RE.sub("", piece)))
        if not inst and e["head"]:
            inst = _clean_piece(DATE_RANGE_RE.sub("", e["head"][0]))
        if not (inst or degree):
            continue
        fld = ""
        fm = re.search(r"\b(?:in|of)\s+([A-Z][A-Za-z&,\- ]{3,60}?)(?:\s*[|,(\-–—]|$)", degree)
        if fm:
            fld = _clean_piece(fm.group(1))
        out.append(EducationItem(institution=inst, degree=degree, field=fld, level=_level_of(degree + " " + block), start_date=start,
                                 end_date=end, grade=(gm.group(1).strip() if gm else ""),
                                 details=[b for b in e["bullets"] if not GRADE_RE.fullmatch(b)]))
    return out


_PROJECT_CATEGORY_LABELS = {
    "database management", "data science & machine learning", "tools", "web development", "programming", "embedded system",
}


def _is_strength_statement(line: str) -> bool:
    text = _strip_bullet(line).strip().lower()
    return text.startswith(("strong ", "eager to learn", "enjoy working", "passionate about", "creative problem-solving"))


def _is_project_heading(line: str) -> bool:
    text = re.sub(r"^\s*#{1,6}\s*", "", line).strip()
    key = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    if (not text or key in _PROJECT_CATEGORY_LABELS or _is_strength_statement(text)
            or URL_RE.search(text) or EMAIL_RE.search(text) or DATE_RANGE_RE.search(text)
            or re.search(r"[.!?]$", text)):
        return False
    return bool(re.search(r"[-–—]", text)) and len(text.split()) >= 3 and len(text) <= 140 and text.count(",") <= 1


def _is_project_category_line(line: str) -> bool:
    key = re.sub(r"[^a-z0-9]+", " ", line.lower()).strip()
    return key in _PROJECT_CATEGORY_LABELS


def _parse_projects(lines: list[str], kind: str = "project") -> list[ProjectItem]:
    out: list[ProjectItem] = []
    if any(re.match(r"^\s*#{1,6}\s+", line) for line in lines):
        entries: list[dict] = []
        current: dict | None = None
        for line in lines:
            heading = re.match(r"^\s*#{1,6}\s+(.+?)\s*$", line)
            if heading:
                if current:
                    entries.append(current)
                current = {"head": [heading.group(1)], "bullets": []}
            elif current and line.strip():
                current["head"].append(line.strip())
        if current:
            entries.append(current)
    else:
        entries = []
        current = None
        for line in lines:
            if _is_project_heading(line):
                if current:
                    entries.append(current)
                current = {"head": [line.strip()], "bullets": []}
            elif current and line.strip():
                current["head"].append(line.strip())
        if current:
            entries.append(current)

    for e in entries:
        if not e["head"] and not e["bullets"]:
            continue
        head = e["head"][0] if e["head"] else (e["bullets"].pop(0) if e["bullets"] else "")
        _s, _e, _c, rest = _parse_range(head)
        rest = re.sub(r"^\s*#{1,6}\s*", "", rest)
        name = _clean_piece(rest)
        detail_lines = []
        skip_category_values = False
        for line in e["head"][1:] + e["bullets"]:
            if _is_project_category_line(line):
                skip_category_values = True
                continue
            if skip_category_values:
                skip_category_values = False
                continue
            if URL_RE.search(line) or _is_strength_statement(line):
                continue
            detail_lines.append(line)
        desc = " ".join(detail_lines)
        if ":" in rest and len(rest.split(":")[0]) < 80:
            name, tail = rest.split(":", 1)
            desc = " ".join([tail.strip(), desc]).strip()
        name = _clean_piece(name)
        name_key = re.sub(r"[^a-z0-9 ]", " ", name.lower()).strip()
        if not name or name_key in _PROJECT_CATEGORY_LABELS or _is_strength_statement(name):
            continue
        txt = " ".join([head, *detail_lines])
        urls = URL_RE.findall(txt)
        out.append(ProjectItem(name=name, description=desc.strip(), bullets=e["bullets"], technologies=find_skills(txt),
                               url=urls[0] if urls else "", kind=kind))
    return out


def _parse_skills(lines: list[str]) -> list[SkillItem]:
    seen: dict[str, SkillItem] = {}
    for ln in lines:
        body = _strip_bullet(ln)
        label_cat = None
        if ":" in body and len(body.split(":")[0]) < 40:
            label, body = body.split(":", 1)
            l = label.lower()
            label_cat = ("language" if "language" in l else "ai_ml" if re.search(r"ai|ml|machine|data", l) else
                         "cloud" if re.search(r"cloud|devops", l) else "database" if "database" in l else
                         "soft" if "soft" in l else None)
        for tok in re.split(r"[,;|•·/]\s*|\s{2,}", body):
            tok = _clean_piece(tok)
            if not tok or len(tok) > 40:
                continue
            canon = canonicalize(tok)
            cat = category_of(canon)
            if cat == "technical" and label_cat:
                cat = label_cat
            if cat == "technical" and tok.lower() not in {s.lower() for s in find_skills(tok)} and len(tok.split()) > 4:
                continue
            seen.setdefault(canon.lower(), SkillItem(name=canon, category=cat))
    return list(seen.values())


def _years_from_experiences(exps: list[ExperienceItem], today: date) -> float | None:
    months: set[int] = set()
    for e in exps:
        if e.kind not in ("work", "internship"):
            continue
        s = _to_ym(e.start_date, today)
        en = today.year * 12 + today.month if e.is_current else _to_ym(e.end_date, today)
        if s and en and en >= s:
            months.update(range(s, en + 1))
    if not months:
        return None
    return round(len(months) / 12, 1)


def _to_ym(s: str, today: date) -> int | None:
    if not s:
        return None
    m = re.search(rf"({_MON})\.?\s*,?\s*(\d{{4}})", s, re.I)
    if m:
        mon = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"].index(m.group(1)[:3].lower()) + 1
        return int(m.group(2)) * 12 + mon
    m = re.search(r"(\d{1,2})/(\d{4})", s)
    if m:
        return int(m.group(2)) * 12 + int(m.group(1))
    m = re.search(r"(\d{4})", s)
    return int(m.group(1)) * 12 + 6 if m else None


def _name_from_header(header: list[str], email: str) -> str:
    for ln in header[:8]:
        s = ln.strip()
        if not s or EMAIL_RE.search(s) or URL_RE.search(s) or re.search(r"\d{4,}", s):
            continue
        words = s.replace(",", " ").split()
        if 1 < len(words) <= 5 and all(re.fullmatch(r"[A-Za-z.'\-]+", w) for w in words):
            return " ".join(w.capitalize() if w.isupper() else w for w in words)
    if email:
        local = email.split("@")[0]
        parts = [p for p in re.split(r"[._\-0-9]+", local) if p]
        if len(parts) >= 2:
            return " ".join(p.capitalize() for p in parts)
    return ""


def parse_cv_text(text: str, today: date | None = None) -> ProfileExtraction:
    text = _normalize_cv_text(text)
    today = today or date.today()
    header, sections = split_sections(text)
    personal = header + sections.get("contact", [])
    head_text = "\n".join(personal[:15])
    em = EMAIL_RE.search(head_text) or EMAIL_RE.search(text)
    email = em.group(0) if em else ""
    phone = ""
    for m in PHONE_RE.finditer(head_text or text):
        digits = re.sub(r"\D", "", m.group(1))
        looks_like_year_range = bool(re.fullmatch(r"(19|20)\d{2}\D+(19|20)\d{2}", m.group(1).strip()))
        if 9 <= len(digits) <= 15 and not looks_like_year_range:
            phone = m.group(1).strip()
            break
    links: dict = {"other": []}
    for u in URL_RE.findall(text):
        u = u.rstrip(".")
        low = u.lower()
        if "linkedin.com" in low:
            links.setdefault("linkedin", u)
        elif "github.com" in low:
            links.setdefault("github", u)
        elif u not in links["other"]:
            links["other"].append(u)
    # a leading item in "other" is the best portfolio guess only if user did not label it; keep as other.
    location = ""
    for ln in personal[:10]:
        m = re.search(r"(?:Address|Location)\s*[:\-]\s*(.+)", ln, re.I)
        if m:
            location = m.group(1).split("|")[0].strip()
            break
        for piece in re.split(r"\s*[|•·]\s*", ln.strip()):
            if re.fullmatch(r"[A-Z][A-Za-z.\- ]+(?:,\s*[A-Z][A-Za-z.\- ]+){1,2}", piece) and not EMAIL_RE.search(piece):
                location = piece
                break
        if location:
            break

    work = _parse_experience(sections.get("experience", []))
    work += _parse_experience(sections.get("internship", []), default_kind="internship")
    work += _parse_experience(sections.get("volunteer_experience", []), default_kind="volunteer")
    research_lines = sections.get("research", [])
    research = _parse_projects(research_lines, kind="research") if research_lines else []
    project_lines = sections.get("projects", [])
    embedded_strengths = [_strip_bullet(line) for line in project_lines if _is_strength_statement(line)]
    project_lines = [line for line in project_lines if not _is_strength_statement(line)]
    projects = _parse_projects(project_lines) + research
    educations = _parse_education(sections.get("education", []))

    skills_map: dict[str, SkillItem] = {s.name.lower(): s for s in _parse_skills(sections.get("skills", []))}
    # Skills evidenced elsewhere in the CV (experience / projects) are still truthful: they appear in the CV.
    body_text = "\n".join(l for sec in ("experience", "projects", "research", "summary") for l in sections.get(sec, []))
    for name in find_skills(body_text):
        skills_map.setdefault(name.lower(), SkillItem(name=name, category=category_of(name)))

    certs: list[CertificationItem] = []
    for ln in sections.get("certifications", []):
        s = _strip_bullet(ln)
        if len(s) < 3:
            continue
        _a, _b, _c, rest = _parse_range(s)
        pieces = _split_header_pieces(rest)
        if pieces:
            certs.append(CertificationItem(name=pieces[0], issuer=pieces[1] if len(pieces) > 1 else "", date=_b or _a))

    def plain(sec: str) -> list[str]:
        return [x for x in (_strip_bullet(l) for l in sections.get(sec, [])) if x]

    languages: list[str] = []
    for l in plain("languages"):
        languages.extend(_clean_piece(x) for x in re.split(r"[,;]", l) if _clean_piece(x))

    summary = " ".join(l.strip() for l in sections.get("summary", []) if l.strip())
    headline = ""
    for ln in header[1:6]:
        s = ln.strip()
        if s and TITLE_WORDS.search(s) and not EMAIL_RE.search(s) and len(s) < 100:
            headline = s
            break

    return ProfileExtraction(
        full_name=_name_from_header(personal, email), email=email, phone=phone, location=location, headline=headline, summary=summary,
        links={k: v for k, v in links.items() if v}, years_experience=_years_from_experiences(work, today),
        skills=list(skills_map.values()), experiences=work, educations=educations, projects=projects, certifications=certs,
        languages=languages, strengths=list(dict.fromkeys(plain("strengths") + embedded_strengths)),
        achievements=plain("achievements"), publications=plain("publications"),
        extracurriculars=plain("extracurricular"), references=plain("references"),
    )
