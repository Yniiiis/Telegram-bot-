# Telegram Music (monorepo)

REST API backend, React Mini App frontend, and Telegram bot — each app has its own `.env.example`.

## Layout

| Path | Stack | Role |
|------|--------|------|
| `backend/` | FastAPI, PostgreSQL, SQLAlchemy | REST API (`/search` with pagination + cache, `/stream`, `/history`, auth, playlists, …) |
| `frontend/` | React, Vite, Zustand | Telegram Web App UI |
| `bot/` | aiogram 3.x | Welcome, Web App button, `/help` |

## Local development

1. **Database:** from repo root, `docker compose up db` (or install Postgres locally).
2. **Backend:** `cd backend && cp .env.example .env`, install deps, `uvicorn app.main:app --reload`.
3. **Frontend:** `cd frontend && cp .env.example .env`, `npm install`, `npm run dev` (proxies `/api` → `http://127.0.0.1:8000`).
4. **Bot:** `cd bot && cp .env.example .env`, set `BOT_TOKEN` and HTTPS `WEBAPP_URL`, `python main.py`.

## Docker (full stack)

```bash
cp .env.example .env
# Fill TELEGRAM_BOT_TOKEN, JWT_SECRET, WEBAPP_URL (e.g. https://your-tunnel.example.com)
docker compose up --build
```

- API: `http://localhost:8000`
- Frontend (nginx + `/api` proxy): `http://localhost:8080`
- Postgres: `localhost:5432`

Production Web Apps require **HTTPS** for `WEBAPP_URL`; use a tunnel (ngrok, Cloudflare Tunnel, etc.) when testing with Telegram.

## API notes

- **Search:** `GET /search?q=&offset=&limit=` — returns `tracks`, `offset`, `limit`, `has_more`. Catalog hits are cached in memory (~5 min) per query page.
- **History:** `POST /history/play` `{ "track_id": "uuid" }` (called by the Mini App when playback starts), `GET /history/recent?limit=`.
- **Stream errors:** failed upstream responses use JSON `detail` with `code` such as `UPSTREAM_NOT_AVAILABLE` or `UPSTREAM_UNREACHABLE`.

If you use Alembic in production, generate a migration after model changes (`play_history` table).
