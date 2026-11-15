"""Request-level protections and observability (section 21).

- Origin check: state-changing requests carrying an Origin header must come
  from an allowed origin (defence in depth on top of SameSite cookies).
- Body size cap: requests over NIVRA_MAX_REQUEST_BYTES are refused before
  they are read into memory.
- Request IDs: every response carries X-Request-ID; logs include it, so a
  user-reported problem can be traced without logging any content.
- JSON logs (NIVRA_LOG_FORMAT=json) for production log collectors.
"""

import json
import logging
import secrets
import time
from contextvars import ContextVar

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings

request_id: ContextVar[str] = ContextVar("request_id", default="-")
log = logging.getLogger("nivra.http")

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


class RequestGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        s = get_settings()
        rid = request.headers.get("x-request-id", "")
        rid = rid if (0 < len(rid) <= 64 and rid.replace("-", "").isalnum()) else secrets.token_hex(8)
        token = request_id.set(rid)
        try:
            length = request.headers.get("content-length")
            if length and length.isdigit() and int(length) > s.max_request_bytes:
                return JSONResponse({"detail": "That request is too large."}, status_code=413,
                                    headers={"X-Request-ID": rid})
            origin = request.headers.get("origin")
            if request.method in UNSAFE and origin and origin not in s.allowed_origins:
                return JSONResponse({"detail": "Request blocked."}, status_code=403,
                                    headers={"X-Request-ID": rid})
            start = time.monotonic()
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            # Method, route and status only - never bodies, query strings or headers.
            log.info("%s %s %s %dms", request.method, request.url.path, response.status_code,
                     int((time.monotonic() - start) * 1000))
            return response
        finally:
            request_id.reset(token)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": request_id.get(),
            "message": record.getMessage(),
        })


def configure_logging() -> None:
    s = get_settings()
    handler = logging.StreamHandler()
    if s.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger("nivra")
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    root.propagate = False
