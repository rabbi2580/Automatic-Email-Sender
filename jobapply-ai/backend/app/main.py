from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.core.config import get_settings
from app.core.db import Base, SessionLocal, engine
from app.core.logging import setup_logging

log = logging.getLogger("jobapply.http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    setup_logging(s.debug)
    if s.environment in ("development", "test"):
        import app.models  # noqa: F401

        Base.metadata.create_all(engine)  # production uses Alembic migrations
    from app.services.usage import seed_plan_limits

    with SessionLocal() as db:
        seed_plan_limits(db)
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title=s.app_name, version=__version__, lifespan=lifespan, docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json",
                  description="AI job-application assistant. All endpoints (except auth and signed file downloads) require a Bearer token and are tenant-isolated.")
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in s.cors_origins.split(",") if o.strip()], allow_credentials=False,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"], max_age=600)

    @app.middleware("http")
    async def security_and_logging(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        t0 = time.monotonic()
        try:
            resp = await call_next(request)
        except Exception:  # noqa: BLE001
            log.exception("unhandled error", extra={"request_id": rid, "path": request.url.path, "method": request.method})
            resp = JSONResponse({"detail": "Internal server error", "request_id": rid}, status_code=500)
        resp.headers.update({
            "X-Request-ID": rid, "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'" if not request.url.path.startswith(("/docs", "/redoc")) else "default-src 'self' 'unsafe-inline' cdn.jsdelivr.net data:",
        })
        if request.url.path.startswith(("/api/", "/admin/")):
            resp.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        if s.is_production():
            resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        if not request.url.path.startswith("/api/v1/files/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        log.info("request", extra={"request_id": rid, "path": request.url.path, "method": request.method, "status": resp.status_code,
                                   "duration_ms": int((time.monotonic() - t0) * 1000), "user_id": getattr(request.state, "user_id", None)})
        return resp

    from app.api.routes import admin, applications, auth, email_accounts, files, jobs, matches, misc, profile, resumes

    for r in (auth.router, profile.router, resumes.router, jobs.router, matches.router, applications.router, email_accounts.router, misc.router, files.router, admin.auth_router, admin.router):
        app.include_router(r, prefix="/api/v1")

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
