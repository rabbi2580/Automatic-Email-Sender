"""Admin API — aggregate/operational data only. No endpoint returns CV text, job text, or generated documents."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import hashlib
import csv
import io
import secrets
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import require_admin
from app.core.ratelimit import rate_limit
from app.core.security import create_admin_access_token, hash_password, validate_password_strength, verify_password
from app.models import (
    AIRequestLog, Admin, AdminSession, Application, AuditLog, EmailAccount, FeatureFlag, Job, PlanLimit, Resume, SendLog, Subscription, UsageRecord, User,
)
from app.schemas.api import LoginIn
from app.services import usage
from app.services.audit import audit
from app.services.storage import get_storage
from app.workers.dispatch import enqueue

auth_router = APIRouter(prefix="/admin", tags=["admin-auth"])
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@auth_router.post("/login", dependencies=[Depends(rate_limit("admin-auth", 10))])
def admin_login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    password = body.password
    # Avoid a distinct response for unknown accounts.
    admin = db.scalar(select(Admin).where(Admin.email == email))
    if not admin or not admin.is_active or not verify_password(password, admin.password_hash):
        raise HTTPException(401, "Incorrect email or password.")
    raw = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    db.add(AdminSession(admin_id=admin.id, token_hash=hashlib.sha256(raw.encode()).hexdigest(),
                        csrf_hash=hashlib.sha256(csrf.encode()).hexdigest(),
                        expires_at=datetime.now(timezone.utc) + timedelta(minutes=get_settings().admin_session_minutes)))
    admin.last_login_at = datetime.now(timezone.utc)
    db.commit()
    response = JSONResponse({"access_token": create_admin_access_token(admin.id), "token_type": "bearer", "csrf_token": csrf,
                             "expires_in": get_settings().admin_session_minutes * 60})
    response.set_cookie("admin_session", raw, httponly=True, secure=get_settings().is_production(),
                        samesite="strict", max_age=get_settings().admin_session_minutes * 60, path="/api/v1/admin")
    return response


@auth_router.post("/logout", status_code=204)
def admin_logout(request: Request, db: Session = Depends(get_db), _admin: Admin = Depends(require_admin)):
    raw = request.cookies.get("admin_session")
    if raw:
        row = db.scalar(select(AdminSession).where(AdminSession.token_hash == hashlib.sha256(raw.encode()).hexdigest()))
        if row:
            row.revoked_at = datetime.now(timezone.utc)
            db.commit()


@auth_router.get("/login", include_in_schema=False)
def admin_login_page():
    return {"detail": "Use the admin web client to sign in."}


class UserAdminPatch(BaseModel):
    is_active: bool | None = None
    flagged_reason: str | None = Field(default=None, max_length=255)
    plan: str | None = Field(default=None, pattern="^(free|pro|business)$")


class UserAdminBulk(BaseModel):
    user_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    is_active: bool | None = None
    flagged_reason: str | None = Field(default=None, max_length=255)


class FlagIn(BaseModel):
    key: str = Field(min_length=2, max_length=60, pattern="^[a-z0-9_.-]+$")
    enabled: bool
    description: str = ""


class LimitIn(BaseModel):
    plan: str = Field(pattern="^(free|pro|business)$")
    metric: str
    limit_value: int = Field(ge=0)


@router.get("/health")
def health(db: Session = Depends(get_db)):
    s = get_settings()
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    ai_total = db.scalar(select(func.count()).select_from(AIRequestLog).where(AIRequestLog.created_at >= since)) or 0
    ai_fail = db.scalar(select(func.count()).select_from(AIRequestLog).where(AIRequestLog.created_at >= since, AIRequestLog.success.is_(False))) or 0
    stuck = db.scalar(select(func.count()).select_from(Job).where(Job.status == "processing", Job.updated_at < datetime.now(timezone.utc) - timedelta(minutes=15))) or 0
    sends = db.execute(select(SendLog.success, func.count()).where(SendLog.created_at >= since).group_by(SendLog.success)).all()
    return {"database": db_ok, "task_mode": s.task_mode, "ai_provider": s.ai_provider, "environment": s.environment,
            "users": db.scalar(select(func.count()).select_from(User).where(User.deleted_at.is_(None))) or 0,
            "jobs_24h": db.scalar(select(func.count()).select_from(Job).where(Job.created_at >= since)) or 0,
            "stuck_jobs": stuck, "ai_requests_24h": ai_total, "ai_failure_rate_24h": round(ai_fail / ai_total, 3) if ai_total else 0.0,
            "sends_24h": {("ok" if k else "failed"): v for k, v in sends}}


@router.get("/analytics")
def analytics(db: Session = Depends(get_db)):
    """Small operational dashboard query set; returns counts only, never CV contents."""
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    users = lambda since=None: db.scalar(select(func.count()).select_from(User).where(User.deleted_at.is_(None), *( [User.created_at >= since] if since else [] ))) or 0
    resumes = lambda status=None: db.scalar(select(func.count()).select_from(Resume).where(Resume.deleted_at.is_(None), *([Resume.status == status] if status else []))) or 0
    return {"users": {"total": users(), "last_24h": users(day_ago), "last_7d": users(week_ago)},
            "cvs": {"total": resumes(), "completed": resumes("completed"), "needs_review": resumes("requires_review"), "failed": resumes("failed"), "queued": resumes("queued"), "processing": resumes("processing")},
            "parse_success_rate": round((resumes("completed") + resumes("requires_review")) / resumes() * 100, 1) if resumes() else 0.0,
            "parse_errors_7d": db.scalar(select(func.count()).select_from(Resume).where(Resume.status == "failed", Resume.updated_at >= week_ago)) or 0,
            "generated_at": now.isoformat()}


@router.get("/users")
def users(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    rows = db.execute(select(User, Subscription.plan).outerjoin(Subscription, Subscription.user_id == User.id).where(User.deleted_at.is_(None)).order_by(User.created_at.desc()).limit(min(limit, 200)).offset(offset)).all()
    out = []
    for u, plan in rows:
        out.append({"id": str(u.id), "email": u.email, "role": u.role, "plan": plan or "free", "is_active": u.is_active, "email_verified": u.email_verified, "flagged_reason": u.flagged_reason,
                    "created_at": u.created_at.isoformat(), "counts": {
                        "jobs": db.scalar(select(func.count()).select_from(Job).where(Job.user_id == u.id)) or 0,
                        "applications": db.scalar(select(func.count()).select_from(Application).where(Application.user_id == u.id)) or 0,
                        "resumes": db.scalar(select(func.count()).select_from(Resume).where(Resume.user_id == u.id, Resume.deleted_at.is_(None))) or 0}})
    return out


@router.patch("/users/bulk")
def bulk_users(body: UserAdminBulk, request: Request, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(User).where(User.id.in_(body.user_ids), User.deleted_at.is_(None))).all()
    if body.is_active is None and body.flagged_reason is None:
        raise HTTPException(422, "Provide an action to apply.")
    for u in rows:
        if body.is_active is not None:
            u.is_active = body.is_active
        if body.flagged_reason is not None:
            u.flagged_reason = body.flagged_reason or None
    audit(db, None, "admin.users_bulk_update", request=request, admin_id=str(admin.id), count=len(rows))
    db.commit()
    return {"updated": len(rows)}


@router.get("/users.csv")
def export_users_csv(db: Session = Depends(get_db)):
    rows = db.scalars(select(User).where(User.deleted_at.is_(None)).order_by(User.created_at.desc())).all()
    out = io.StringIO(); writer = csv.writer(out)
    writer.writerow(["id", "email", "full_name", "active", "verified", "created_at"])
    for u in rows:
        writer.writerow([str(u.id), u.email, u.full_name, u.is_active, u.email_verified, u.created_at.isoformat()])
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=users.csv"})


@router.patch("/users/{user_id}")
def patch_user(user_id: str, body: UserAdminPatch, request: Request, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    import uuid

    try:
        u = db.get(User, uuid.UUID(user_id))
    except ValueError:
        u = None
    if not u or u.deleted_at:
        raise HTTPException(404, "Not found")
    d = body.model_dump(exclude_unset=True)
    if "is_active" in d:
        u.is_active = d["is_active"]
    if "flagged_reason" in d:
        u.flagged_reason = d["flagged_reason"] or None
    if d.get("plan"):
        sub = db.scalar(select(Subscription).where(Subscription.user_id == u.id))
        if sub:
            sub.plan = d["plan"]
        else:
            db.add(Subscription(user_id=u.id, plan=d["plan"]))
    audit(db, None, "admin.user_update", entity_type="user", entity_id=u.id, request=request, admin_id=str(admin.id), fields=sorted(d))
    db.commit()
    return {"ok": True}


@router.get("/usage")
def usage_overview(db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(days=30)
    rows = db.execute(select(UsageRecord.metric, func.sum(UsageRecord.quantity), func.sum(UsageRecord.input_tokens), func.sum(UsageRecord.output_tokens),
                             func.sum(UsageRecord.est_cost_usd_micros)).where(UsageRecord.created_at >= since).group_by(UsageRecord.metric)).all()
    return [{"metric": m, "quantity": int(q or 0), "input_tokens": int(i or 0), "output_tokens": int(o or 0), "est_cost_usd": round((c or 0) / 1_000_000, 4)} for m, q, i, o, c in rows]


@router.get("/ai")
def ai_stats(db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(days=7)
    rows = db.execute(select(AIRequestLog.task, AIRequestLog.provider, func.count(), func.sum(AIRequestLog.success.cast(__import__("sqlalchemy").Integer)),
                             func.sum(AIRequestLog.cache_hit.cast(__import__("sqlalchemy").Integer)), func.avg(AIRequestLog.latency_ms)).where(AIRequestLog.created_at >= since)
                      .group_by(AIRequestLog.task, AIRequestLog.provider)).all()
    s = get_settings()
    return {"configured_provider": s.ai_provider, "fallback_to_heuristic": s.ai_fallback_to_heuristic,
            "tasks": [{"task": t, "provider": p, "requests": n, "success": int(ok or 0), "cache_hits": int(c or 0), "avg_latency_ms": int(l or 0)} for t, p, n, ok, c, l in rows]}


@router.get("/delivery-failures")
def delivery_failures(db: Session = Depends(get_db)):
    rows = db.scalars(select(SendLog).where(SendLog.success.is_(False)).order_by(SendLog.created_at.desc()).limit(100)).all()
    return [{"at": r.created_at.isoformat(), "provider": r.provider, "recipient_domain": r.recipient.split("@")[-1], "error": r.error, "user_id": str(r.user_id)} for r in rows]


@router.get("/integrations")
def integrations(db: Session = Depends(get_db)):
    rows = db.execute(select(EmailAccount.provider, EmailAccount.status, func.count()).where(EmailAccount.deleted_at.is_(None)).group_by(EmailAccount.provider, EmailAccount.status)).all()
    return [{"provider": p, "status": s, "count": c} for p, s, c in rows]


@router.get("/errors")
def errors(db: Session = Depends(get_db)):
    rows = db.scalars(select(Job).where(Job.status == "failed").order_by(Job.updated_at.desc()).limit(50)).all()
    return [{"job_id": str(j.id), "reason": j.status_reason, "at": j.updated_at.isoformat(), "source": j.source} for j in rows]


@router.get("/cvs")
def cvs(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    rows = db.scalars(select(Resume).where(Resume.deleted_at.is_(None)).order_by(Resume.created_at.desc())
                      .limit(min(max(limit, 1), 200)).offset(max(offset, 0))).all()
    return [{"id": str(r.id), "user_id": str(r.user_id), "filename": r.filename, "content_type": r.content_type,
             "size_bytes": r.size_bytes, "status": r.status, "status_reason": r.status_reason,
             "created_at": r.created_at.isoformat()} for r in rows]


@router.get("/parse-errors")
def parse_errors(db: Session = Depends(get_db)):
    rows = db.scalars(select(Resume).where(Resume.deleted_at.is_(None), Resume.status == "failed").order_by(Resume.updated_at.desc()).limit(100)).all()
    return [{"id": str(r.id), "user_id": str(r.user_id), "filename": r.filename, "reason": r.status_reason,
             "updated_at": r.updated_at.isoformat()} for r in rows]


@router.post("/cvs/{resume_id}/retry")
def retry_cv(resume_id: uuid.UUID, db: Session = Depends(get_db)):
    r = db.scalar(select(Resume).where(Resume.id == resume_id, Resume.deleted_at.is_(None)))
    if not r:
        raise HTTPException(404, "Not found")
    if r.status not in ("failed", "requires_review"):
        raise HTTPException(409, "Only failed or review-required CVs can be retried.")
    r.status, r.status_reason = "queued", None
    db.commit(); enqueue("process_resume", str(r.id))
    return {"queued": True, "id": str(r.id)}


@router.get("/cvs/{resume_id}")
def cv_detail(resume_id: uuid.UUID, db: Session = Depends(get_db)):
    r = db.scalar(select(Resume).where(Resume.id == resume_id, Resume.deleted_at.is_(None)))
    if not r:
        raise HTTPException(404, "Not found")
    # Deliberately metadata-only: extracted CV contents are private user data.
    return {"id": str(r.id), "user_id": str(r.user_id), "filename": r.filename, "content_type": r.content_type,
            "size_bytes": r.size_bytes, "status": r.status, "status_reason": r.status_reason,
            "has_extracted_text": bool(r.extracted_text), "created_at": r.created_at.isoformat()}


@router.delete("/cvs/{resume_id}", status_code=204)
def delete_cv(resume_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    r = db.scalar(select(Resume).where(Resume.id == resume_id, Resume.deleted_at.is_(None)))
    if not r:
        raise HTTPException(404, "Not found")
    get_storage().delete(r.storage_key)
    r.deleted_at, r.extracted_text, r.status = datetime.now(timezone.utc), "", "deleted"
    audit(db, None, "admin.cv_delete", entity_type="resume", entity_id=r.id, request=request)
    db.commit()


@router.get("/audit-log")
def audit_log(limit: int = 100, db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500))).all()
    return [{"at": r.created_at.isoformat(), "user_id": str(r.user_id) if r.user_id else None, "action": r.action, "entity": r.entity_type, "ip": r.ip} for r in rows]


@router.get("/feature-flags")
def flags(db: Session = Depends(get_db)):
    return [{"key": f.key, "enabled": f.enabled, "description": f.description} for f in db.scalars(select(FeatureFlag).order_by(FeatureFlag.key))]


@router.put("/feature-flags")
def put_flag(body: FlagIn, request: Request, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    f = db.scalar(select(FeatureFlag).where(FeatureFlag.key == body.key))
    if not f:
        f = FeatureFlag(key=body.key)
        db.add(f)
    f.enabled, f.description = body.enabled, body.description
    audit(db, None, "admin.flag", request=request, admin_id=str(admin.id), key=body.key, enabled=body.enabled)
    db.commit()
    return {"ok": True}


@router.get("/limits")
def limits(db: Session = Depends(get_db)):
    return [{"plan": l.plan, "metric": l.metric, "period": l.period, "limit_value": l.limit_value} for l in db.scalars(select(PlanLimit).order_by(PlanLimit.plan, PlanLimit.metric))]


@router.put("/limits")
def put_limit(body: LimitIn, request: Request, admin: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    if body.metric not in usage.DEFAULT_LIMITS:
        raise HTTPException(422, f"Unknown metric. Valid: {sorted(usage.DEFAULT_LIMITS)}")
    row = db.scalar(select(PlanLimit).where(PlanLimit.plan == body.plan, PlanLimit.metric == body.metric))
    if row:
        row.limit_value = body.limit_value
    else:
        db.add(PlanLimit(plan=body.plan, metric=body.metric, period=usage.DEFAULT_LIMITS[body.metric][0], limit_value=body.limit_value))
    audit(db, None, "admin.limit", request=request, admin_id=str(admin.id), plan=body.plan, metric=body.metric, value=body.limit_value)
    db.commit()
    return {"ok": True}
