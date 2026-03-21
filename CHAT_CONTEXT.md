# Контекст проекта для нового чата (Telegram Music Bot / Mini App)

Скопируй этот файл целиком в новый чат с ИИ, чтобы продолжить работу без потери контекста.

---

## Что это

Монорепозиторий: **REST API (FastAPI)** + **React Telegram Mini App** + **бот (aiogram 3)**. Каталог музыки **модульный** (`backend/app/services/catalog/`): цепочка провайдеров задаётся **`CATALOG_PROVIDER_CHAIN`** (по умолчанию `zaycev,hitmotop,jamendo,mock` — первый непустой результат побеждает).

- **Zaycev** — официальный API `https://api.zaycev.net/external` (hello → auth с MD5, search, затем `/track/{id}/play` для URL потока). Ключ **`ZAYCEV_STATIC_KEY`** (в репо по умолчанию демо-ключ из go-zaycevnet; для своего приложения лучше свой).
- **Hitmotop** — разбор HTML `rus.hitmotop.com/search` (BeautifulSoup); с части IP возможен **403**; база **`HITMOTOP_BASE_URL`**.
- **Jamendo** — при **`JAMENDO_CLIENT_ID`**; только поле **`audio`** (не download URL); в ответе есть метаданные лицензии.
- **mock** — демо SoundHelix, если API недоступны.

У треков в БД и API: **`license_url`**, **`license_short`**. UUID в моделях через **`sqlalchemy.Uuid`** — совместимо с Postgres и SQLite.

## Структура папок

```
/backend     — FastAPI, SQLAlchemy 2 async, БД: Postgres или SQLite
/frontend    — React 18 + Vite + TypeScript + Tailwind + Zustand + react-router
/bot         — aiogram 3.26, кнопка Web App
docker-compose.yml — опционально (если есть Docker + compose v2): db, api, bot, frontend
```

## Стек (важное)

- Backend: FastAPI ~0.115, Pydantic v2, httpx, PyJWT, `python-dotenv`, **beautifulsoup4** (Hitmotop)
- DB: **PostgreSQL** (прод / Docker) или **SQLite** (`sqlite+aiosqlite:///./music_bot.db` в `backend/`) — без Docker; `create_all` при старте; для прод при смене схемы — **Alembic**
- Frontend: `@twa-dev/sdk`, HTML5 `<audio>`, dev-прокси `VITE_API_BASE_URL=/api` → `127.0.0.1:8000`
- Bot: **`BOT_TOKEN`** или **`TELEGRAM_BOT_TOKEN`** в `bot/.env` — **должен совпадать** с **`TELEGRAM_BOT_TOKEN`** в **`backend/.env`** (проверка `initData` и выдача JWT)

## Переменные окружения

**`backend/.env`** (см. `.env.example`):

- `DATABASE_URL` — Postgres **или** `sqlite+aiosqlite:///./music_bot.db`
- `TELEGRAM_BOT_TOKEN`, `JWT_SECRET`, `JWT_EXPIRE_MINUTES`
- `JAMENDO_CLIENT_ID` (опционально)
- `CATALOG_PROVIDER_CHAIN`, `ZAYCEV_STATIC_KEY`, `HITMOTOP_BASE_URL`
- **`ALLOW_DEV_AUTH=1`** — только локально: включает **`POST /auth/dev`** (синтетический пользователь `telegram_id=999999999`, выдача JWT). **В проде выключить.**

**`frontend/.env`**: `VITE_API_BASE_URL=/api`; опционально **`VITE_DEV_BEARER_TOKEN`** — валидный JWT (редко нужен, если есть `/auth/dev`).

**`bot/.env`**: `BOT_TOKEN`, **`WEBAPP_URL`** — URL Mini App; локально совпадает с Vite (**`http://localhost:5173`** или **5174**, если порт занят). Для Telegram на телефоне обычно нужен **HTTPS** (туннель).

**Корень** `.env.example` — для Docker Compose при наличии Docker.

## Аутентификация

1. В Telegram: `POST /auth/telegram` с `{ "init_data": "<WebApp.initData>" }` → JWT.
2. **Локальный браузер (DEV):** без `initData` фронт вызывает **`POST /auth/dev`**, если **`ALLOW_DEV_AUTH=1`** на бэкенде.
3. Остальные запросы: `Authorization: Bearer <token>`.
4. **Стриминг:** `GET /stream/{track_id}?token=<JWT>` (Bearer или query `token`).

## Основные эндпоинты API

| Метод | Путь | Назначение |
|--------|------|------------|
| POST | `/auth/telegram` | Вход по initData |
| POST | `/auth/dev` | Только при `ALLOW_DEV_AUTH=1`, не в OpenAPI schema |
| GET | `/search?...` | Поиск, кэш в памяти ~5 мин |
| GET | `/track/{id}` | Метаданные |
| GET | `/stream/{id}` | Прокси аудио, Range |
| GET/POST | `/favorites`, DELETE `...` | Избранное |
| CRUD | `/playlists`, … | Плейлисты |
| POST | `/history/play` | История |
| GET | `/history/recent?limit=` | Недавние |
| GET | `/health` | Health |

## Модели БД (суть)

`users`, `tracks` (unique `source`+`external_id`, поля `license_url`, `license_short`), `favorites`, `playlists`, `playlist_tracks`, `play_history`.

**Upsert треков** (`track_upsert.py`): для SQLite — `sqlite.insert` + `ON CONFLICT (source, external_id)`; для Postgres — `postgresql.insert` + именованный constraint; `populate_existing` на execute.

## Фронтенд

Страницы: `/`, `/search`, `/favorites`, `/playlists`, `/playlists/:id`. Плеер, таб-бар, lazy-обложки, `preload="none"` у `<audio>`, throttling прогресса через `requestAnimationFrame`.

## Запуск локально (без Docker)

1. **`backend/.env`**: SQLite или свой Postgres; выставить секреты и при необходимости **`ALLOW_DEV_AUTH=1`**.
2. `cd backend && pip install -r requirements.txt && .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
3. `cd frontend && npm i && npm run dev` — смотри в выводе порт (**5173** или **5174**); **`WEBAPP_URL`** в боте должен совпадать.
4. `cd bot && python3 main.py` (нужен установленный **aiogram** в этом Python).

Если сессия в браузере «залипла»: Local Storage ключ **`tg-music-auth`** — очистить.

## Docker

Если установлены Docker **и** `docker compose` (v2): `docker compose up db` и т.д. На машинах **без** daemon — использовать **SQLite** (см. выше).

## Ограничения и заметки

- Кэш поиска без Redis (in-process).
- Аудио с CDN не кэшируется на диск.
- Сторонние каталоги — соблюдение ToS и авторских прав на стороне оператора сервиса.
- **Секреты** (токен бота, JWT) не коммитить; при утечке — revoke в BotFather.

---

*Путь в репозитории: `CHAT_CONTEXT.md`*
