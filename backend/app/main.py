from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import init_db
from app.routers import auth, favorites, history, playlists, search, stream, tracks


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with httpx.AsyncClient(
        headers={"User-Agent": "TelegramMusicCatalog/1.0"},
        timeout=httpx.Timeout(60.0),
    ) as client:
        app.state.http_client = client
        yield


app = FastAPI(title="Telegram Music API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(search.router)
app.include_router(history.router)
app.include_router(tracks.router)
app.include_router(favorites.router)
app.include_router(playlists.router)
app.include_router(stream.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
