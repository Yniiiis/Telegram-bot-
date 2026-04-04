import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.session import SessionLocal, init_db
from app.middleware.metrics import MetricsMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.routers import auth, client_debug, discovery, favorites, history, playlists, recommendations, search, stream, tracks

logger = logging.getLogger(__name__)

_HITMOTOP_WARMUP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


async def _warmup_hitmotop_catalog(client: httpx.AsyncClient) -> None:
    if not settings.hitmotop_warmup_on_startup:
        return
    base = (settings.hitmotop_base_url or "https://rus.hitmotop.com").rstrip("/")
    headers = {
        "User-Agent": _HITMOTOP_WARMUP_UA,
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Referer": f"{base}/",
        "Accept-Encoding": "gzip, deflate, br",
    }
    try:
        await client.get(f"{base}/", headers=headers, timeout=8.0)
        logger.debug("hitmotop catalog warmup finished")
    except Exception:
        logger.debug("hitmotop catalog warmup failed", exc_info=True)


async def _new_releases_refresh_loop(app: FastAPI) -> None:
    from app.services.discovery import refresh_featured_new_releases

    await asyncio.sleep(12)
    while True:
        try:
            async with SessionLocal() as db:
                n = await refresh_featured_new_releases(db, app.state.http_client)
                logger.info("featured new releases refreshed (%s tracks)", n)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("featured new releases refresh failed")
        await asyncio.sleep(max(300, settings.new_releases_refresh_sec))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    limits_catalog = httpx.Limits(
        max_connections=max(8, settings.httpx_catalog_max_connections),
        max_keepalive_connections=max(4, settings.httpx_catalog_max_keepalive),
    )
    limits_stream = httpx.Limits(
        max_connections=max(8, settings.httpx_stream_max_connections),
        max_keepalive_connections=max(4, settings.httpx_stream_max_keepalive),
    )
    catalog_timeout = httpx.Timeout(max(5.0, settings.httpx_catalog_timeout_sec))
    stream_timeout = httpx.Timeout(
        settings.stream_read_timeout_sec,
        connect=settings.stream_connect_timeout_sec,
    )

    catalog_kw: dict = {
        "headers": {"User-Agent": "TelegramMusicCatalog/1.0"},
        "timeout": catalog_timeout,
        "limits": limits_catalog,
        "follow_redirects": True,
    }
    if settings.httpx_catalog_http2:
        catalog_kw["http2"] = True

    async with httpx.AsyncClient(**catalog_kw) as catalog_client, httpx.AsyncClient(
        timeout=stream_timeout,
        limits=limits_stream,
        follow_redirects=True,
    ) as stream_client:
        app.state.http_client = catalog_client
        app.state.stream_http_client = stream_client
        asyncio.create_task(_warmup_hitmotop_catalog(catalog_client))
        task = asyncio.create_task(_new_releases_refresh_loop(app))
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(title="Telegram Music API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # JWT is in headers / ?token=, not cookies — False avoids invalid * + credentials pairs in strict WebViews.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["content-length", "content-range", "accept-ranges", "x-response-time-ms"],
)

app.add_middleware(MetricsMiddleware)
if settings.api_rate_limit_per_minute > 0:
    app.add_middleware(RateLimitMiddleware, per_minute=settings.api_rate_limit_per_minute)

app.include_router(auth.router)
app.include_router(client_debug.router)
app.include_router(discovery.router)
app.include_router(search.router)
app.include_router(history.router)
app.include_router(tracks.router)
app.include_router(favorites.router)
app.include_router(playlists.router)
app.include_router(recommendations.router)
app.include_router(stream.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
