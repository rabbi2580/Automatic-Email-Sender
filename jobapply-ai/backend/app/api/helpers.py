"""Serializers kept separate from routes so response shapes are consistent and never leak internals (storage keys, secrets)."""
from __future__ import annotations

from datetime import date

from app.models import Application, ApplicationDocument, ApplicationEmail, CoverLetter, EmailAccount, Job, JobMatch, Resume
from app.services.parsing.deadlines import days_remaining, urgency_label


def job_out(j: Job, m: JobMatch | None = None, app: Application | None = None) -> dict:
    dr = days_remaining(j.deadline)
    out = {
        "id": str(j.id), "company": j.company_name, "title": j.job_title, "department": j.department, "location": j.location,
        "employment_type": j.employment_type, "workplace_type": j.workplace_type, "salary": j.salary,
        "experience_required": j.experience_required, "education_required": j.education_required,
        "required_skills": j.required_skills, "preferred_skills": j.preferred_skills, "tech_stack": j.tech_stack,
        "responsibilities": j.responsibilities, "benefits": j.benefits, "deadline": j.deadline.isoformat() if j.deadline else None,
        "days_remaining": dr, "urgency": urgency_label(dr), "application_email": j.application_email, "application_url": j.application_url,
        "source": j.source, "source_url": j.source_url, "status": j.status, "status_reason": j.status_reason, "warnings": (j.extracted_information or {}).get("warnings", []),
        "duplicate_of": str(j.duplicate_of_id) if j.duplicate_of_id else None, "duplicate_score": j.duplicate_score,
        "duplicate_message": "This appears to be a duplicate of an existing job." if j.duplicate_of_id else None,
        "duplicate_reasons": (j.extracted_information or {}).get("duplicate_reasons", []),
        "created_at": j.created_at.isoformat(), "batch_id": str(j.batch_id) if j.batch_id else None,
    }
    if m:
        out["match"] = match_out(m)
    if app:
        out["application"] = {"id": str(app.id), "status": app.status, "generation_status": app.generation_status}
    return out


def match_out(m: JobMatch) -> dict:
    return {"score": m.score, "classification": m.classification, "dimensions": m.dimensions, "strong_matches": m.strong_matches, "partial_matches": m.partial_matches,
            "missing": m.missing, "concerns": m.concerns, "explanation": m.explanation, "weights_used": m.weights_used, "thresholds_used": m.thresholds_used}


def resume_out(r: Resume) -> dict:
    return {"id": str(r.id), "filename": r.filename, "label": r.label, "size_bytes": r.size_bytes, "status": r.status, "status_reason": r.status_reason,
            "parse_quality": r.parse_quality or {},
            "is_master": r.is_master, "created_at": r.created_at.isoformat()}


def doc_out(d: ApplicationDocument) -> dict:
    return {"id": str(d.id), "kind": d.kind, "filename": d.filename, "content_type": d.content_type, "size_bytes": d.size_bytes}


def email_out(e: ApplicationEmail | None) -> dict | None:
    if not e:
        return None
    return {"id": str(e.id), "to_address": e.to_address, "subject": e.subject, "body": e.body, "attachment_doc_ids": e.attachment_doc_ids, "status": e.status,
            "attempts": e.attempts, "last_error": e.last_error, "sent_at": e.sent_at.isoformat() if e.sent_at else None,
            "email_account_id": str(e.email_account_id) if e.email_account_id else None, "edited_by_user": e.edited_by_user}


def account_out(a: EmailAccount) -> dict:
    return {"id": str(a.id), "provider": a.provider, "address": a.address, "display_name": a.display_name, "status": a.status, "is_default": a.is_default,
            "scopes": a.scopes, "tracking_enabled": a.tracking_enabled, "tracking_error": a.tracking_error,
            "last_tracking_at": a.last_tracking_at.isoformat() if a.last_tracking_at else None,
            "last_used_at": a.last_used_at.isoformat() if a.last_used_at else None, "connected_at": a.created_at.isoformat()}


def application_summary(a: Application, j: Job, m: JobMatch | None) -> dict:
    dr = days_remaining(j.deadline)
    return {"id": str(a.id), "job_id": str(j.id), "company": j.company_name, "title": j.job_title, "status": a.status, "generation_status": a.generation_status,
            "generation_reason": a.generation_reason, "qc_passed": a.qc_passed, "score": m.score if m else None, "classification": m.classification if m else None,
            "deadline": j.deadline.isoformat() if j.deadline else None, "days_remaining": dr, "urgency": urgency_label(dr), "channel": a.channel,
            "sent_at": a.sent_at.isoformat() if a.sent_at else None, "notes": a.notes, "reminder_at": a.reminder_at.isoformat() if a.reminder_at else None,
            "updated_at": a.updated_at.isoformat(), "has_email": bool(j.application_email), "has_url": bool(j.application_url)}
