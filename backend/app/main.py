import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.session import SessionLocal, init_db
from app.routers import auth, discovery, favorites, history, playlists, recommendations, search, stream, tracks

logger = logging.getLogger(__name__)


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
    stream_timeout = httpx.Timeout(
        settings.stream_read_timeout_sec,
        connect=settings.stream_connect_timeout_sec,
    )
    stream_limits = httpx.Limits(max_connections=120, max_keepalive_connections=40)
    async with httpx.AsyncClient(
        headers={"User-Agent": "TelegramMusicCatalog/1.0"},
        timeout=httpx.Timeout(60.0),
    ) as client, httpx.AsyncClient(
        timeout=stream_timeout,
        follow_redirects=True,
        limits=stream_limits,
    ) as stream_client:
        app.state.http_client = client
        app.state.stream_upstream_client = stream_client
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
    expose_headers=["content-length", "content-range", "accept-ranges"],
)

app.include_router(auth.router)
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
