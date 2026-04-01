"""Simple in-memory rate limit for expensive routes (per client IP)."""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings

logger = logging.getLogger(__name__)

_PREFIXES = ("/search", "/stream/")


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, per_minute: int | None = None) -> None:
        super().__init__(app)
        self._per_minute = per_minute if per_minute is not None else settings.api_rate_limit_per_minute
        self._window_sec = 60.0
        self._hits: dict[str, list[float]] = {}

    def _client_ip(self, request: Request) -> str:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    def _prune(self, now: float, ip: str) -> None:
        buf = self._hits.get(ip)
        if not buf:
            return
        cutoff = now - self._window_sec
        self._hits[ip] = [t for t in buf if t > cutoff]
        if not self._hits[ip]:
            del self._hits[ip]

    async def dispatch(self, request: Request, call_next) -> Response:
        if self._per_minute <= 0:
            return await call_next(request)

        path = request.url.path
        if not any(path == p or path.startswith(p) for p in _PREFIXES):
            return await call_next(request)

        now = time.monotonic()
        ip = self._client_ip(request)
        self._prune(now, ip)
        buf = self._hits.setdefault(ip, [])
        if len(buf) >= self._per_minute:
            logger.info("rate limit 429 ip=%s path=%s", ip, path)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": {
                        "code": "RATE_LIMIT",
                        "message": "Too many requests. Try again shortly.",
                    }
                },
            )
        buf.append(now)
        return await call_next(request)
