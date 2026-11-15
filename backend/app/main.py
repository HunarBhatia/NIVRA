"""FastAPI application entry point.

Run (from backend/):  .venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import account, agents, auth, cases, complaints, discovery, evidence, images, monitoring
from app.core.config import get_settings
from app.core.hardening import RequestGuard, configure_logging

settings = get_settings()
configure_logging()
log = logging.getLogger("nivra")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    stop = None
    if settings.inline_worker and settings.environment == "development":
        from app.discovery.worker import start_inline_worker

        stop = start_inline_worker()
    yield
    if stop:
        stop.set()


app = FastAPI(
    title="Nivra API",
    version="1.0.0-rc1",
    lifespan=lifespan,
    # Interactive docs are handy in development, but not exposed in production.
    docs_url=None if settings.is_production else "/api/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/api/openapi.json",
)

app.add_middleware(RequestGuard)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    # Case data must never sit in browser or proxy caches.
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    # Report which fields were wrong, but never echo the submitted values back
    # (they could be passphrases or links).
    fields = sorted({".".join(str(p) for p in e["loc"][1:]) or "body" for e in exc.errors()})
    return JSONResponse({"detail": "Some details aren't valid.", "fields": fields}, status_code=422)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    # Log the error type and route only - not the request body.
    log.error("Unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path)
    return JSONResponse({"detail": "Something went wrong on our side."}, status_code=500)


@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness: the process is up."""
    return {"status": "ok"}


@app.get("/api/ready", tags=["health"])
def ready() -> JSONResponse:
    """Readiness: the database answers, evidence storage is writable and the
    platform directory loads. Used by load balancers before sending traffic."""
    import os
    from pathlib import Path

    from sqlalchemy import text

    from app import platforms
    from app.core.db import engine

    checks = {}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
    try:
        d = Path(settings.evidence_dir)
        d.mkdir(parents=True, exist_ok=True)
        checks["evidence_storage"] = "ok" if os.access(d, os.W_OK) else "error"
    except OSError:
        checks["evidence_storage"] = "error"
    try:
        checks["platforms"] = "ok" if platforms.all_platforms() else "error"
    except Exception:
        checks["platforms"] = "error"
    ok = all(v == "ok" for v in checks.values())
    return JSONResponse({"status": "ok" if ok else "not_ready", "checks": checks},
                        status_code=200 if ok else 503)


app.include_router(auth.router)
app.include_router(account.router)
app.include_router(cases.router)
app.include_router(images.router)
app.include_router(discovery.router)
app.include_router(agents.router)
app.include_router(complaints.router)
app.include_router(evidence.router)
app.include_router(monitoring.router)
