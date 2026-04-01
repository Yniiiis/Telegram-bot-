# Handoff context (paste into new chat)

## Repo
- Monorepo: `backend/` FastAPI, `frontend/` React+Vite+Tailwind, `bot/` aiogram 3.x.
- Remote: `origin` → GitHub `Yniiiis/Telegram-bot-` (user may have force-pushed history).

## Stack (user rules)
- FastAPI, SQLAlchemy 2 async (`Mapped`/`mapped_column`), Pydantic v2, httpx async, python-dotenv.
- aiogram 3.x; validate Telegram WebApp `initData` on backend.
- Frontend: React 18, react-router-dom, zustand, `@twa-dev/sdk`.

## Current product state
- **Catalog + playback: Hitmotop only** (`rus.hitmotop.com`, JadeMusic-style parsing). No TIDAL, SoundCloud, Zaycev, Jamendo, YouTube Music, Bandcamp, Last.fm resolver, mock catalog — removed.
- `backend/app/services/catalog/engine.py`: `SOURCE_REGISTRY` = `{ hitmotop }`; `search_catalog` → only Hitmotop.
- `backend/app/config.py`: no `catalog_provider_chain`; Hitmotop env vars only (see `backend/.env.example`).
- `playback_media.py`: only `source == "hitmotop"` → direct MP3 URL; `StreamKind` = `"direct"`.
- `stream.py`: relays direct HTTP stream (no YouTube branch).

## Important paths
- API entry: `backend/app/main.py` — routers: auth, discovery, search, history, tracks, favorites, playlists, recommendations, stream.
- Search: `backend/app/routers/search.py` → `search_catalog` + `upsert_external_tracks`.
- Discovery/new releases: `backend/app/services/discovery.py` + `HitmotopCatalogSource`.
- Hitmotop: `backend/app/services/catalog/hitmotop_source.py`.
- Auth: `backend/app/routers/auth.py` → `upsert_user_from_telegram` in `app/services/users.py`.
- Frontend API: `frontend/src/lib/api.ts`; dev base `/api` via Vite proxy → `http://127.0.0.1:8000`.
- Player: `frontend/src/hooks/usePlayerEngine.ts`; shell `frontend/src/layout/AppShell.tsx`.

## Env
- **Backend** `backend/.env`: `DATABASE_URL`, `TELEGRAM_BOT_TOKEN`, `JWT_SECRET`, `ALLOW_DEV_AUTH`, Hitmotop vars. Never commit `.env`.
- **Frontend** prod: `VITE_API_BASE_URL` must be full `https://…` to FastAPI root where `GET /health` works (not relative `/api` on static hosts without proxy).
- **Bot** `bot/.env`: token / `WEBAPP_URL` per local setup.

## Git / history note
- User requested **hard reset to pre-TIDAL** (`378dc87`), then **removed non-Hitmotop catalog code** in working tree; commits after that may need `git status` / `git log -1`.

## Ops pitfall (seen in prod)
- If `GET /health` OK but `/tidal/*` 404 — irrelevant now (no TIDAL). If future API routes 404 while `/health` works → wrong deploy or wrong path prefix.

## Commands
- Backend: from `backend/`, run uvicorn as you usually do (e.g. `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`).
- Frontend: `cd frontend && npm run dev` (port 5173, proxies `/api`).
- Build: `cd frontend && npm run build`.
