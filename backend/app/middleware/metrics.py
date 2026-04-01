"""Request timing + structured logs (API latency; pair with hitmotop parse logs)."""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.metrics")


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        t0 = time.perf_counter()
        path = request.url.path
        method = request.method
        try:
            response = await call_next(request)
        except Exception:
            ms = (time.perf_counter() - t0) * 1000.0
            logger.warning(
                "request error method=%s path=%s duration_ms=%.2f",
                method,
                path,
                ms,
            )
            raise
        ms = (time.perf_counter() - t0) * 1000.0
        if path != "/health":
            logger.info(
                "request method=%s path=%s status=%s duration_ms=%.2f",
                method,
                path,
                response.status_code,
                ms,
            )
        response.headers["X-Response-Time-ms"] = f"{ms:.1f}"
        return response
