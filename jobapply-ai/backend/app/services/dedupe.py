"""Duplicate job detection: URL, email+title, company+title, exact hash, and text similarity."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import sha256_hex
from app.models import Job

_SUFFIX = re.compile(r"\b(ltd|limited|inc|incorporated|llc|llp|plc|pvt|private|co|corp|corporation|company|bd|bangladesh)\b\.?", re.I)
_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "ref", "source", "trk"}
SIMILARITY_THRESHOLD = 0.82


def norm_company(name: str) -> str:
    n = _SUFFIX.sub(" ", name.lower())
    return re.sub(r"[^a-z0-9]+", " ", n).strip()


def norm_title(title: str) -> str:
    t = re.sub(r"\b(urgent(?:ly)?|hiring|vacancy|opening|job|position|needed|required)\b", " ", title.lower())
    return re.sub(r"[^a-z0-9+#]+", " ", t).strip()


def norm_url(url: str) -> str:
    if not url:
        return ""
    p = urlparse(url.strip())
    q = urlencode(sorted((k, v) for k, v in parse_qsl(p.query) if k.lower() not in _TRACKING))
    host = p.netloc.lower().removeprefix("www.")
    return f"{host}{p.path.rstrip('/')}" + (f"?{q}" if q else "")


def content_hash(text: str) -> str:
    return sha256_hex(re.sub(r"\W+", " ", text.lower()).strip())


def _shingles(text: str, n: int = 3) -> set[str]:
    words = re.findall(r"[a-z0-9+#]+", text.lower())
    return {" ".join(words[i:i + n]) for i in range(max(0, len(words) - n + 1))} or set(words)


def text_similarity(a: str, b: str) -> float:
    sa, sb = _shingles(a), _shingles(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


@dataclass
class DuplicateResult:
    job_id: uuid.UUID
    score: float
    reasons: list[str]


def find_duplicate(new: dict, existing: list[dict]) -> DuplicateResult | None:
    """`new`/`existing` dicts: id, company_name, job_title, application_email, application_url, source_url, original_content, content_hash."""
    best: DuplicateResult | None = None
    nc, nt = norm_company(new.get("company_name", "")), norm_title(new.get("job_title", ""))
    nurls = {u for u in (norm_url(new.get("application_url", "")), norm_url(new.get("source_url", ""))) if u}
    nemail = (new.get("application_email") or "").lower()
    for ex in existing:
        if ex["id"] == new.get("id"):
            continue
        score, reasons = 0.0, []
        if new.get("content_hash") and new["content_hash"] == ex.get("content_hash"):
            score, reasons = 1.0, ["identical text"]
        exurls = {u for u in (norm_url(ex.get("application_url", "")), norm_url(ex.get("source_url", ""))) if u}
        if nurls & exurls:
            score, reasons = max(score, 0.98), reasons + ["same URL"]
        ec, et = norm_company(ex.get("company_name", "")), norm_title(ex.get("job_title", ""))
        same_company = bool(nc and nc == ec)
        same_title = bool(nt and nt == et)
        if same_company and same_title:
            score, reasons = max(score, 0.92), reasons + ["same company and title"]
        elif nemail and nemail == (ex.get("application_email") or "").lower() and same_title:
            score, reasons = max(score, 0.9), reasons + ["same application email and title"]
        sim = text_similarity(new.get("original_content", ""), ex.get("original_content", ""))
        shared_channel = bool(nurls & exurls) or bool(nemail and nemail == (ex.get("application_email") or "").lower())
        different_companies = bool(nc and ec and nc != ec) and not shared_channel
        if different_companies:
            pass  # near-identical text at two different employers is a separate opening (e.g. templates), not a duplicate
        elif sim >= SIMILARITY_THRESHOLD:
            score, reasons = max(score, sim), reasons + [f"description {sim:.0%} similar"]
        elif sim >= 0.6 and (same_company or same_title) and not different_companies:
            score, reasons = max(score, 0.75 + sim / 10), reasons + [f"similar description ({sim:.0%})"]
        if score >= 0.75 and (best is None or score > best.score):
            best = DuplicateResult(ex["id"], round(score, 3), reasons)
    return best


def find_duplicate_for_user(db: Session, user_id: uuid.UUID, new: dict) -> DuplicateResult | None:
    rows = db.execute(
        select(Job.id, Job.company_name, Job.job_title, Job.application_email, Job.application_url, Job.source_url, Job.original_content, Job.content_hash)
        .where(Job.user_id == user_id, Job.deleted_at.is_(None), Job.duplicate_of_id.is_(None)).limit(3000)
    ).all()
    existing = [dict(zip(("id", "company_name", "job_title", "application_email", "application_url", "source_url", "original_content", "content_hash"), r)) for r in rows]
    return find_duplicate(new, existing)
