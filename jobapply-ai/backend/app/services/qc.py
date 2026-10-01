"""Quality-control agent: independent, deterministic verification of everything before an application can be approved.

It never trusts the generator. Anything in the CV must be traceable to the stored candidate profile.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.generation.cv_builder import rewrite_is_safe
from app.services.generation.exporters import extract_pdf_text
from app.services.generation.letters import PLACEHOLDER_RX, letter_text, validate_letter
from app.services.parsing.skills import canonicalize
from app.services.profile_view import skill_universe

EMAIL_OK = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
ORG_RX = re.compile(r"\b([A-Z][A-Za-z0-9&.'\-]+(?:\s+[A-Z][A-Za-z0-9&.'\-]+){0,3}\s+(?:Ltd\.?|Limited|Inc\.?|LLC|LLP|Pvt\.?\s?Ltd\.?|Corporation|Corp\.?|GmbH|PLC))\b")


@dataclass
class QCResult:
    checks: list[dict] = field(default_factory=list)

    def add(self, id_: str, ok: bool, message: str, severity: str = "block") -> None:
        self.checks.append({"id": id_, "ok": ok, "severity": severity, "message": message})

    def report(self) -> dict:
        blocking = [c for c in self.checks if not c["ok"] and c["severity"] == "block"]
        warnings = [c for c in self.checks if not c["ok"] and c["severity"] == "warn"]
        return {"passed": not blocking, "blocking": blocking, "warnings": warnings, "checks": self.checks,
                "summary": ("Application blocked — review required. Reason: " + blocking[0]["message"]) if blocking else "All automatic checks passed."}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def check_cv(r: QCResult, cv: dict, profile: dict, job: dict, pdf: bytes | None, pages_limit: int, pages: int | None) -> None:
    h = cv["header"]
    r.add("cv.name", _norm(h["name"]) == _norm(profile["full_name"]) and bool(h["name"]), "Candidate name on the CV does not match your profile.")
    r.add("cv.contact", _norm(h["email"]) == _norm(profile["email"]) and _norm(h["phone"]) == _norm(profile["phone"]),
          "Contact details on the CV differ from your profile.")
    p_exp = {e["id"]: e for e in profile["experiences"]}
    bad: list[str] = []
    for e in cv["experience"]:
        src = p_exp.get(e["id"])
        if not src:
            bad.append(f"unknown experience '{e['title']}'")
            continue
        for k in ("company", "title", "start_date", "end_date", "is_current"):
            if e[k] != src[k]:
                bad.append(f"{src['company']}: {k} changed ('{src[k]}' → '{e[k]}')")
        original = "\n".join(src["bullets"])
        for b in e["bullets"]:
            if b not in src["bullets"] and not any(rewrite_is_safe(o, b) for o in src["bullets"]):
                bad.append(f"{src['company']}: unsupported bullet '{b[:50]}…'")
    r.add("cv.experience", not bad, "Experience does not match your profile: " + "; ".join(bad[:3]))
    p_edu = {e["id"]: e for e in profile["educations"]}
    bad = []
    for e in cv["education"]:
        src = p_edu.get(e["id"])
        if not src or any(e[k] != src[k] for k in ("institution", "degree", "start_date", "end_date", "grade")):
            bad.append(e.get("degree") or e.get("institution") or "?")
    r.add("cv.education", not bad, "Education does not match your profile: " + ", ".join(bad))
    p_sk = {s["id"]: s for s in profile["skills"]}
    universe = skill_universe(profile)
    bad = [s["name"] for s in cv["skills"] if not (p_sk.get(s["id"]) and p_sk[s["id"]]["name"] == s["name"]) and canonicalize(s["name"]) not in universe]
    r.add("cv.skills", not bad, "Skills not found in your profile: " + ", ".join(bad))
    p_proj = {p["id"]: p for p in profile["projects"]}
    bad = []
    for p in cv["projects"]:
        src = p_proj.get(p["id"])
        if not src or src["name"] != p["name"]:
            bad.append(p["name"])
            continue
        if any(b not in src["bullets"] and not any(rewrite_is_safe(o, b) for o in src["bullets"]) for b in p["bullets"]):
            bad.append(p["name"] + " (bullet)")
    r.add("cv.projects", not bad, "Projects do not match your profile: " + ", ".join(bad))
    p_cert = {c["name"] for c in profile["certifications"]}
    bad = [c["name"] for c in cv["certifications"] if c["name"] not in p_cert]
    r.add("cv.certifications", not bad, "Certifications not in your profile: " + ", ".join(bad))
    r.add("cv.target_company", _norm(cv["meta"].get("target_company", "")) == _norm(job["company_name"]),
          "Company name mismatch detected between the CV target and the job post.")
    blob = "\n".join([cv["summary"], *[b for e in cv["experience"] for b in e["bullets"]], *[b for p in cv["projects"] for b in p["bullets"]]])
    r.add("cv.placeholders", not PLACEHOLDER_RX.search(blob), "The CV contains placeholder text.")
    if pdf is not None:
        text = extract_pdf_text(pdf)
        ok = _norm(h["name"]) in _norm(text) and (not h["email"] or h["email"].lower() in text.lower()) and bool(re.search(r"education|শিক্ষা", text, re.I))
        r.add("cv.ats_readable", ok, "The PDF text could not be read back reliably (ATS risk).")
        if pages is not None:
            r.add("cv.page_limit", pages <= pages_limit, f"The CV is {pages} pages; the limit is {pages_limit}. Reduce content or choose two pages.", "warn")


URL_RX = re.compile(r"(?:https?://|www\.)[^\s)>\]]+", re.I)
ADDR_RX = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def _known_contacts(profile: dict, job: dict) -> set[str]:
    vals = [profile.get("email") or "", job.get("application_email") or "", job.get("application_url") or ""]
    links = profile.get("links") or {}
    for v in links.values():
        vals.extend(v if isinstance(v, list) else [v])
    for p in profile.get("projects", []):
        vals.append(p.get("url") or "")
    return {re.sub(r"^(https?://)?(www\.)?", "", str(v).strip().lower()).rstrip("/") for v in vals if v}


def check_links(r: QCResult, text: str, profile: dict, job: dict, label: str) -> None:
    """Generated text may only contain URLs / addresses that the candidate or the job post supplied (prompt-injection and hallucination guard)."""
    known = _known_contacts(profile, job)
    found = [re.sub(r"^(https?://)?(www\.)?", "", m.lower()).rstrip("/.,;") for m in URL_RX.findall(text)] + [m.lower() for m in ADDR_RX.findall(text)]
    unknown = [f for f in dict.fromkeys(found) if not any(f == k or f.startswith(k) or k.startswith(f) for k in known)]
    r.add(f"{label}.links", not unknown, f"The {label.replace('_', ' ')} contains a link or address that is not in your profile or the job post: " + ", ".join(unknown[:3]))


def check_letter(r: QCResult, letter: dict, profile: dict, job: dict, own_employers: set[str]) -> None:
    problems = validate_letter(letter, profile, job)
    r.add("letter.content", not problems, "Cover letter issue: " + " ".join(problems))
    text = letter_text(letter)
    allowed = {_norm(job["company_name"])} | {_norm(x) for x in own_employers} | {_norm(e["institution"]) for e in profile["educations"]}
    foreign = [m for m in ORG_RX.findall(text) if _norm(m) not in allowed and not any(_norm(m) in a or a in _norm(m) for a in allowed if a)]
    check_links(r, text, profile, job, "cover_letter")
    r.add("letter.employer_refs", not foreign, "Cover letter references another organisation: " + ", ".join(foreign[:3]))


def check_email(r: QCResult, email: dict, profile: dict, job: dict, attachments: list[dict], include_letter: bool, prior_sends: list[dict]) -> None:
    to = (email.get("to_address") or "").strip()
    if not job.get("application_email") and not to:
        r.add("email.recipient", True, "No application email: this job uses an application link.", "warn")
        return
    r.add("email.recipient_valid", bool(EMAIL_OK.match(to)), "The recipient email address is missing or invalid.")
    if job.get("application_email") and to.lower() != job["application_email"].lower():
        r.add("email.recipient_matches_post", False, f"Recipient '{to}' differs from the address in the job post ('{job['application_email']}').", "warn")
    subj = email.get("subject", "")
    title_words = [w for w in re.findall(r"[a-z]{4,}", (job["job_title"] or "").lower()) if w not in {"junior", "senior"}]
    r.add("email.subject", bool(subj.strip()) and (not title_words or any(w in subj.lower() for w in title_words)) and _norm(profile["full_name"]).split(" ")[0] in subj.lower(),
          "The email subject must mention the position and your name.")
    body = email.get("body", "")
    r.add("email.placeholders", not PLACEHOLDER_RX.search(subj + "\n" + body), "The email contains placeholder text.")
    check_links(r, subj + "\n" + body, profile, job, "email")
    comp = (job.get("company_name") or "").lower()
    others = [m for m in ORG_RX.findall(body) if comp and _norm(m) not in comp and comp not in _norm(m)]
    r.add("email.company", not others, "The email mentions a different organisation: " + ", ".join(others[:2]))
    kinds = {a["kind"] for a in attachments}
    r.add("email.attachment_cv", "cv_pdf" in kinds or "cv_docx" in kinds, "The tailored CV is not attached.")
    if include_letter:
        r.add("email.attachment_letter", "cover_letter_pdf" in kinds or "cover_letter_docx" in kinds, "The cover letter is not attached.")
    dup = [p for p in prior_sends if p["to"].lower() == to.lower() and p["job_title"].lower() == (job["job_title"] or "").lower()]
    r.add("email.duplicate", not dup, "An application for this position was already sent to this recipient.")


def run_qc(*, profile: dict, job: dict, cv: dict, pdf: bytes | None, pages: int | None, pages_limit: int, letter: dict, email: dict,
           attachments: list[dict], include_letter: bool, prior_sends: list[dict]) -> dict:
    r = QCResult()
    check_cv(r, cv, profile, job, pdf, pages_limit, pages)
    check_letter(r, letter, profile, job, {e["company"] for e in profile["experiences"]})
    check_email(r, email, profile, job, attachments, include_letter, prior_sends)
    return r.report()
