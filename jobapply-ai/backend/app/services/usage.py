"""Plan limits and usage metering. Limits live in the DB (plan_limits) and can be changed without deploys."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import PlanLimit, Subscription, UsageRecord, User

# metric: (period, free, pro, business)
DEFAULT_LIMITS: dict[str, tuple[str, int, int, int]] = {
    "resumes": ("total", 3, 20, 100),
    "cv_versions": ("total", 20, 200, 2000),
    "job_analyses": ("month", 60, 1500, 15000),
    "ai_generations": ("month", 25, 600, 6000),
    "emails_sent": ("month", 25, 400, 4000),
    "candidate_profiles": ("total", 1, 1, 50),
}
PLANS = ("free", "pro", "business")


def seed_plan_limits(db: Session) -> None:
    existing = {(p.plan, p.metric) for p in db.scalars(select(PlanLimit))}
    for metric, (period, *vals) in DEFAULT_LIMITS.items():
        for plan, val in zip(PLANS, vals):
            if (plan, metric) not in existing:
                db.add(PlanLimit(plan=plan, metric=metric, period=period, limit_value=val))
    db.commit()


def user_plan(db: Session, user_id: uuid.UUID) -> str:
    sub = db.scalar(select(Subscription).where(Subscription.user_id == user_id))
    return sub.plan if sub and sub.status == "active" else "free"


def limit_for(db: Session, plan: str, metric: str) -> tuple[str, int]:
    row = db.scalar(select(PlanLimit).where(PlanLimit.plan == plan, PlanLimit.metric == metric))
    if row:
        return row.period, row.limit_value
    period, *vals = DEFAULT_LIMITS[metric]
    return period, vals[PLANS.index(plan)]


def used(db: Session, user_id: uuid.UUID, metric: str, period: str) -> int:
    q = select(func.coalesce(func.sum(UsageRecord.quantity), 0)).where(UsageRecord.user_id == user_id, UsageRecord.metric == metric)
    if period == "month":
        now = datetime.now(timezone.utc)
        q = q.where(UsageRecord.created_at >= datetime(now.year, now.month, 1, tzinfo=timezone.utc))
    return int(db.scalar(q) or 0)


def check_quota(db: Session, user: User, metric: str, qty: int = 1) -> None:
    plan = user_plan(db, user.id)
    period, lim = limit_for(db, plan, metric)
    if used(db, user.id, metric, period) + qty > lim:
        raise HTTPException(402, detail={"code": "quota_exceeded", "metric": metric, "limit": lim, "plan": plan,
                                         "message": f"Your {plan} plan allows {lim} {metric.replace('_', ' ')} ({'per month' if period == 'month' else 'in total'}). Upgrade or wait for the next period."})


def record_usage(db: Session, user_id: uuid.UUID, metric: str, qty: int = 1, **meta) -> None:
    db.add(UsageRecord(user_id=user_id, metric=metric, quantity=qty, meta=meta))


def usage_summary(db: Session, user_id: uuid.UUID) -> dict:
    plan = user_plan(db, user_id)
    out = {}
    for metric in DEFAULT_LIMITS:
        period, lim = limit_for(db, plan, metric)
        out[metric] = {"used": used(db, user_id, metric, period), "limit": lim, "period": period}
    cost = db.scalar(select(func.coalesce(func.sum(UsageRecord.est_cost_usd_micros), 0)).where(UsageRecord.user_id == user_id, UsageRecord.metric == "ai_tokens")) or 0
    toks = db.execute(select(func.coalesce(func.sum(UsageRecord.input_tokens), 0), func.coalesce(func.sum(UsageRecord.output_tokens), 0)).where(
        UsageRecord.user_id == user_id, UsageRecord.metric == "ai_tokens")).one()
    return {"plan": plan, "limits": out, "ai": {"input_tokens": int(toks[0]), "output_tokens": int(toks[1]), "estimated_cost_usd": round(cost / 1_000_000, 4)}}
