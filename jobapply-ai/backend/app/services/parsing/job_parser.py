"""Heuristic job-post → JobExtraction. Works on messy copy/pasted circulars. Never invents values."""
from __future__ import annotations

import re
from datetime import date

from app.schemas.ai import JobExtraction
from app.services.parsing.deadlines import extract_deadline
from app.services.parsing.skills import find_skills

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+|www\.[^\s<>\"')\]]+", re.I)
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐⭕‍️\U0001F000-\U0001F2FF]+")
SEPARATOR_RE = re.compile(r"^\s*(?:[-=*_#~]{3,}|(?:job|position|vacancy|circular|post)\s*(?:no\.?|number|#)?\s*\d+\s*[:.)-]?.{0,60})\s*$", re.I)

SECTION_ALIASES = {
    "responsibilities": ["responsibilities", "key responsibilities", "job responsibilities", "duties", "what you will do", "what you'll do", "role and responsibilities", "your role", "job description", "roles and responsibilities", "main duties", "the role"],
    "requirements": ["requirements", "job requirements", "qualifications", "required qualifications", "minimum qualifications", "what you need", "what we are looking for", "what we're looking for", "who you are", "must have", "skills required", "requirement", "educational requirements", "experience requirements", "additional requirements", "technical skills", "skills", "key skills", "eligibility"],
    "preferred": ["preferred", "preferred qualifications", "nice to have", "good to have", "bonus", "plus points", "desirable", "preferred skills", "advantage"],
    "benefits": ["benefits", "what we offer", "perks", "compensation & benefits", "compensation and benefits", "why join us", "salary & benefits", "other benefits"],
    "apply": ["how to apply", "application process", "to apply", "apply now", "apply", "application instructions"],
    "about": ["about us", "about the company", "company overview", "about", "who we are"],
}
_HEAD = {a: k for k, v in SECTION_ALIASES.items() for a in v}
BULLET_RE = re.compile(r"^\s*([•·▪■◦●\-–—*>✓✔➢➤→]|\d+[.)])\s+")
TITLE_WORDS = (
    r"engineer|developer|scientist|analyst|manager|intern|internship|officer|executive|consultant|specialist|architect|designer|administrator|"
    r"lead|trainee|assistant|associate|researcher|programmer|tester|qa|devops|sre|director|coordinator|technician|instructor|lecturer|professor|"
    r"data|machine learning|ai|ml|software|backend|frontend|full[- ]?stack|mobile|android|ios"
)
TITLE_RE = re.compile(rf"\b(?:{TITLE_WORDS})\b", re.I)
JOB_CUES = re.compile(r"\b(hiring|vacanc|position|apply|job|career|recruit|opening|requirements?|responsibilit|qualification|candidate|resume|cv|send your)\b", re.I)


def _norm_lines(text: str) -> list[str]:
    text = EMOJI_RE.sub(" ", text.replace("\r", ""))
    return [re.sub(r"[ \t]+", " ", l).rstrip() for l in text.split("\n")]


def split_multiple_jobs(text: str) -> list[str]:
    """Split a pasted blob that contains several job posts on explicit separators."""
    lines = text.replace("\r", "").split("\n")
    chunks: list[list[str]] = [[]]
    for ln in lines:
        if SEPARATOR_RE.match(ln):
            is_numbered = bool(re.match(r"^\s*(job|position|vacancy|circular|post)", ln, re.I))
            if chunks[-1] and any(x.strip() for x in chunks[-1]):
                chunks.append([])
            if is_numbered and re.search(r"[A-Za-z]{4,}", re.sub(r"(?i)job|position|vacancy|circular|post|number|no", "", ln)):
                chunks[-1].append(ln)  # keep numbered heading text if it carries a title
            continue
        chunks[-1].append(ln)
    out = ["\n".join(c).strip() for c in chunks if sum(len(x.strip()) for x in c) > 40]
    return out or [text.strip()]


def _label(lines: list[str], names: list[str]) -> str:
    rx = re.compile(rf"^\s*(?:{'|'.join(map(re.escape, names))})\s*[:\-–—]\s*(.+?)\s*$", re.I)
    for ln in lines:
        m = rx.match(ln)
        if m and m.group(1).strip():
            return m.group(1).strip(" .*")
    return ""


def _sections(lines: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    head: list[str] = []
    secs: dict[str, list[str]] = {}
    cur: str | None = None
    for ln in lines:
        s = ln.strip()
        key = re.sub(r"[^a-z&' ]", "", s.lower()).strip()
        inline = None
        if ":" in s and not BULLET_RE.match(ln):
            lab, _, rest = s.partition(":")
            k2 = re.sub(r"[^a-z&' ]", "", lab.lower()).strip()
            if k2 in _HEAD and len(lab) < 40 and _HEAD[k2] in ("responsibilities", "requirements", "preferred", "benefits"):
                cur = _HEAD[k2]
                secs.setdefault(cur, [])
                if rest.strip():
                    secs[cur].append(rest.strip())
                continue
        if key in _HEAD and len(s) < 45 and not BULLET_RE.match(ln):
            cur = _HEAD[key]
            secs.setdefault(cur, [])
            continue
        if cur is None:
            head.append(ln)
        else:
            secs[cur].append(ln)
    return head, secs


def _items(lines: list[str]) -> list[str]:
    out: list[str] = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if BULLET_RE.match(ln):
            out.append(BULLET_RE.sub("", ln, count=1).strip())
        elif out and (s[0].islower() or s[0] in ",;("):
            out[-1] += " " + s
        else:
            out.append(s)
    return [o for o in out if len(o) > 2]


def _experience(text: str) -> tuple[float | None, float | None, str]:
    if re.search(r"\b(fresher|freshers|fresh graduate|recent graduate|no experience (?:required|needed)|entry[- ]level)\b", text, re.I):
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:[-–to]+)\s*(\d+(?:\.\d+)?)\s*\+?\s*years?", text, re.I)
        if not m:
            return 0.0, None, "Fresher / entry level"
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:[-–—]|to)\s*(\d+(?:\.\d+)?)\s*\+?\s*years?(?:['’]s)?(?:\s+of)?(?:\s+\w+){0,3}?\s*(?:experience|exp)?", text, re.I)
    if m:
        return float(m.group(1)), float(m.group(2)), m.group(0).strip()
    m = re.search(r"(?:at\s+least|minimum(?:\s+of)?|min\.?|over|more\s+than|atleast)\s+(\d+(?:\.\d+)?)\s*\+?\s*years?", text, re.I) or \
        re.search(r"(\d+(?:\.\d+)?)\s*\+\s*years?", text, re.I) or \
        re.search(r"(\d+(?:\.\d+)?)\s*years?\s*(?:of\s+)?(?:relevant\s+|professional\s+|working\s+|hands[- ]on\s+)?(?:experience|exp)", text, re.I)
    if m:
        return float(m.group(1)), None, m.group(0).strip()
    return None, None, ""


def _education(text: str) -> tuple[str, list[str], str]:
    level = ""
    if re.search(r"\bph\.?d\b|doctorate", text, re.I):
        level = "phd"
    elif re.search(r"\bmaster'?s?\b|\bm\.?\s?sc\b|\bmsc\b|\bmba\b", text, re.I):
        level = "master"
    elif re.search(r"\bbachelor'?s?\b|\bb\.?\s?sc\b|\bbsc\b|\bundergraduate\b|\bbba\b|\bb\.?\s?tech\b|\bgraduate\b|\bdegree\b", text, re.I):
        level = "bachelor"
    elif re.search(r"\bdiploma\b", text, re.I):
        level = "diploma"
    fields = []
    for rx, name in [(r"\b(?:cse|computer science(?: (?:and|&) engineering)?)\b", "Computer Science"), (r"\b(?:eee|electrical)\b", "Electrical Engineering"),
                     (r"\b(?:ict|information (?:and communication )?technology)\b", "Information Technology"), (r"\bsoftware engineering\b", "Software Engineering"),
                     (r"\b(?:statistics|mathematics|data science)\b", "Statistics / Data Science"), (r"\b(?:business|bba|marketing|finance)\b", "Business")]:
        if re.search(rx, text, re.I) and name not in fields:
            fields.append(name)
    edu_line = next((l.strip(" -•*\t") for l in text.split("\n") if re.search(r"bachelor|master|b\.?sc|m\.?sc|degree|diploma|ph\.?d", l, re.I)), "")
    return level, fields, edu_line[:300]


def parse_job_text(text: str, today: date | None = None, source_url: str = "") -> JobExtraction:
    today = today or date.today()
    lines = _norm_lines(text)
    nonempty = [l for l in lines if l.strip()]
    warnings: list[str] = []
    is_job = bool(JOB_CUES.search(text)) and len(text.strip()) > 40
    if not is_job:
        warnings.append("This text does not look like a job posting.")

    head, secs = _sections(lines)
    joined = "\n".join(lines)

    company = _label(lines, ["company", "company name", "organization", "organisation", "employer", "hiring company", "firm"])
    if not company:
        m = re.search(r"^\s*([A-Z][A-Za-z0-9&.,'\- ]{2,60}?)[ \t]+(?:is|are)\s+(?:now[ \t]+)?(?:hiring|looking for|seeking|recruiting|inviting)", joined, re.M)
        if m:
            company = m.group(1).strip()
    if not company:
        m = re.search(r"\b(?:join|at)[ \t]+([A-Z][A-Za-z0-9&.'\-]+(?:[ \t]+[A-Z][A-Za-z0-9&.'\-]+){0,3}[ \t]*(?:Ltd\.?|Limited|Inc\.?|LLC|Corp\.?|Technologies|Technology|Solutions|Systems|Software|Group|Labs|Bank|Pvt\.? Ltd\.?)?)", joined)
        if m and m.group(1).lower() not in {"the", "our"}:
            company = m.group(1).strip()
    m = re.search(r"\b([A-Z][A-Za-z0-9&.'\-]+(?:[ \t]+[A-Z][A-Za-z0-9&.'\-]+){0,3}[ \t]+(?:Ltd\.?|Limited|Inc\.?|LLC|Pvt\.? Ltd\.?|Technologies|Solutions|Software|Systems|Group|Labs|Bank))\b", joined)
    if not company and m:
        company = m.group(1).strip()
    title = _label(lines, ["position", "job title", "title", "post", "post name", "vacancy", "role", "designation", "job position", "position title", "opening"])
    if not title:
        for ln in nonempty[:12]:
            s = re.sub(r"(?i)\b(we are|we're|now)?\s*hiring[!:.\s]*", "", ln).strip(" !:-–—*#|")
            if 3 <= len(s) <= 90 and TITLE_RE.search(s) and not EMAIL_RE.search(s) and not re.match(r"(?i)(send|apply|email|requirements?|responsibilit|company|location|deadline)", s) \
                    and len(s.split()) <= 9 and not s.endswith("."):
                title = s
                break
    if not title:
        m = re.search(r"(?i)\b(?:hiring|looking for|seeking|recruiting|vacancy for|opening for)\s+(?:an?\s+|the\s+)?([A-Za-z][A-Za-z/&+.\- ]{3,60}?)(?:\s+(?:to|who|for|at|in|with|\(|\.|,|!)|\n|$)", joined)
        if m and TITLE_RE.search(m.group(1)):  # a "title" without any role word is not a title
            title = m.group(1).strip()
    title = re.sub(r"\s+", " ", title).strip(" -–—:")
    m_at = re.match(r"^(.{3,70}?)\s+(?:at|@)\s+([A-Z].{1,60})$", title)
    if m_at and (not company or company.lower() in m_at.group(2).lower() or m_at.group(2).lower() in company.lower()):
        title = m_at.group(1).strip()
        company = company or m_at.group(2).strip()
    if not company:
        warnings.append("Company name was not found in the post.")
    if not title:
        warnings.append("Job title was not found in the post.")

    location = _label(lines, ["location", "job location", "work location", "office location", "place of work", "workplace", "based in", "city"])
    salary = _label(lines, ["salary", "compensation", "remuneration", "pay", "salary range", "stipend", "package"])
    if not salary:
        m = re.search(r"(?:৳|BDT|Tk\.?|USD|\$|€|£|INR|₹)\s?[\d,]+(?:\s*[-–to]+\s*(?:৳|BDT|Tk\.?|USD|\$|€|£|INR|₹)?\s?[\d,]+)?(?:\s*(?:/|per)\s*(?:month|year|hour|mo|yr))?[^.\n]{0,25}", joined, re.I)
        if m:
            salary = m.group(0).strip()
    dept = _label(lines, ["department", "team", "division", "function"])

    low = joined.lower()
    emp = ""
    for pat, val in [(r"\bintern(?:ship)?\b", "internship"), (r"\bpart[- ]?time\b", "part_time"), (r"\b(?:contract|contractual|temporary)\b", "contract"),
                     (r"\bfreelanc", "freelance"), (r"\bfull[- ]?time\b", "full_time"), (r"\bpermanent\b", "full_time")]:
        if re.search(pat, low):
            emp = val
            break
    if not emp and re.search(r"intern", title, re.I):
        emp = "internship"
    wtype = ""
    if re.search(r"\bhybrid\b", low):
        wtype = "hybrid"
    elif re.search(r"\b(remote|work from home|wfh|work-from-home)\b", low) and not re.search(r"no remote|not remote|on-?site only", low):
        wtype = "remote"
    elif re.search(r"\b(on-?site|work from office|in[- ]office|office-based)\b", low):
        wtype = "onsite"

    resp = _items(secs.get("responsibilities", []))
    req_lines = secs.get("requirements", [])
    pref_lines = secs.get("preferred", [])
    ben = _items(secs.get("benefits", []))

    pref_extra = [l for l in req_lines if re.search(r"\b(preferred|plus|bonus|nice to have|advantage|desirable|good to have)\b", l, re.I)]
    req_core = [l for l in req_lines if l not in pref_extra]
    req_text = "\n".join(req_core) if req_core else ("\n".join(head[1:]) if not secs else "")
    pref_text = "\n".join(pref_lines + pref_extra)
    required = find_skills(req_text, include_ambiguous_tokens=bool(re.search(r"skills?\s*:", req_text, re.I)))
    preferred = [s for s in find_skills(pref_text) if s not in required]
    if not secs:  # unstructured post: treat all mentioned skills as required, flag it
        required = find_skills(joined)
        warnings.append("Post has no clear sections; all detected skills were treated as required.")
    all_skills = find_skills(joined)
    tech = all_skills

    exp_scope = "\n".join(req_lines) if req_lines else joined
    min_y, max_y, exp_text = _experience(exp_scope)
    if min_y is None and exp_scope is not joined:
        min_y, max_y, exp_text = _experience(joined)
    edu_level, edu_fields, edu_text = _education("\n".join(req_lines) if req_lines else joined)

    emails = [e for e in EMAIL_RE.findall(joined) if not re.match(r"(?i)(noreply|no-reply|donotreply)", e)]
    app_email = ""
    cue = re.search(r"(?i)(?:send|submit|email|mail|forward|apply|cv|resume)[^\n]{0,80}?(" + EMAIL_RE.pattern + ")", joined)
    if cue:
        app_email = cue.group(1)
    elif emails:
        app_email = emails[0]
    urls = [u.rstrip(".,;") for u in URL_RE.findall(joined)]
    app_url = ""
    for u in urls:
        if re.search(r"apply|career|job|forms\.gle|docs\.google\.com/forms|lever\.co|greenhouse|workable|smartrecruiters|bdjobs|recruit", u, re.I):
            app_url = u
            break
    if not app_url and urls and not app_email:
        app_url = urls[0]
    if source_url and not app_url and not app_email:
        app_url = source_url
    if not app_email and not app_url:
        warnings.append("No application email or URL was found.")

    deadline = extract_deadline(joined, today)
    if deadline and deadline < today:
        warnings.append("The deadline appears to have passed.")

    return JobExtraction(
        company=company, job_title=title, department=dept, location=location, employment_type=emp, workplace_type=wtype, salary=salary,
        min_years=min_y, max_years=max_y, experience_text=exp_text, education_level=edu_level, education_fields=edu_fields, education_text=edu_text,
        required_skills=required, preferred_skills=preferred, tech_stack=tech, responsibilities=resp[:25], benefits=ben[:20], deadline=deadline,
        application_email=app_email, application_url=app_url, is_job_posting=is_job, warnings=warnings,
    )
