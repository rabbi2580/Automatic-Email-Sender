"""Admin API — aggregate/operational data only. No endpoint returns CV text, job text, or generated documents."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import require_admin
from app.models import (
    AIRequestLog, Application, AuditLog, EmailAccount, FeatureFlag, Job, PlanLimit, Resume, SendLog, Subscription, UsageRecord, User,
)
from app.services import usage
from app.services.audit import audit

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class UserAdminPatch(BaseModel):
    is_active: bool | None = None
    flagged_reason: str | None = Field(default=None, max_length=255)
    plan: str | None = Field(default=None, pattern="^(free|pro|business)$")


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


@router.patch("/users/{user_id}")
def patch_user(user_id: str, body: UserAdminPatch, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
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
    audit(db, admin.id, "admin.user_update", entity_type="user", entity_id=u.id, request=request, fields=sorted(d))
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


@router.get("/audit-log")
def audit_log(limit: int = 100, db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500))).all()
    return [{"at": r.created_at.isoformat(), "user_id": str(r.user_id) if r.user_id else None, "action": r.action, "entity": r.entity_type, "ip": r.ip} for r in rows]


@router.get("/feature-flags")
def flags(db: Session = Depends(get_db)):
    return [{"key": f.key, "enabled": f.enabled, "description": f.description} for f in db.scalars(select(FeatureFlag).order_by(FeatureFlag.key))]


@router.put("/feature-flags")
def put_flag(body: FlagIn, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    f = db.scalar(select(FeatureFlag).where(FeatureFlag.key == body.key))
    if not f:
        f = FeatureFlag(key=body.key)
        db.add(f)
    f.enabled, f.description = body.enabled, body.description
    audit(db, admin.id, "admin.flag", request=request, key=body.key, enabled=body.enabled)
    db.commit()
    return {"ok": True}


@router.get("/limits")
def limits(db: Session = Depends(get_db)):
    return [{"plan": l.plan, "metric": l.metric, "period": l.period, "limit_value": l.limit_value} for l in db.scalars(select(PlanLimit).order_by(PlanLimit.plan, PlanLimit.metric))]


@router.put("/limits")
def put_limit(body: LimitIn, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if body.metric not in usage.DEFAULT_LIMITS:
        raise HTTPException(422, f"Unknown metric. Valid: {sorted(usage.DEFAULT_LIMITS)}")
    row = db.scalar(select(PlanLimit).where(PlanLimit.plan == body.plan, PlanLimit.metric == body.metric))
    if row:
        row.limit_value = body.limit_value
    else:
        db.add(PlanLimit(plan=body.plan, metric=body.metric, period=usage.DEFAULT_LIMITS[body.metric][0], limit_value=body.limit_value))
    audit(db, admin.id, "admin.limit", request=request, plan=body.plan, metric=body.metric, value=body.limit_value)
    db.commit()
    return {"ok": True}
