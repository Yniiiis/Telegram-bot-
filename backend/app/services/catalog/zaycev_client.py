"""Official Zaycev external HTTP API (same flow as github.com/pixfid/go-zaycevnet)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE = "https://api.zaycev.net/external"
_lock = asyncio.Lock()
_cached_token: str | None = None
_cached_until: float = 0.0
_TTL_SEC = 45 * 60


def _md5_hex(s: str) -> str:
    return hashlib.md5(s.encode(), usedforsecurity=False).hexdigest()


async def _fetch_json(client: httpx.AsyncClient, url: str, params: dict[str, str]) -> dict[str, Any]:
    r = await client.get(url, params=params, timeout=30.0)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and "error" in data:
        err = data["error"]
        if isinstance(err, dict):
            raise RuntimeError(err.get("text") or str(err))
        raise RuntimeError(str(data))
    return data


async def get_zaycev_access_token(client: httpx.AsyncClient) -> str | None:
    key = (settings.zaycev_static_key or "").strip()
    if not key:
        return None

    global _cached_token, _cached_until
    now = time.monotonic()
    async with _lock:
        if _cached_token and now < _cached_until:
            return _cached_token
        try:
            hello = await _fetch_json(client, f"{_BASE}/hello", {})
            code = str(hello.get("token") or "")
            if not code:
                return None
            auth = await _fetch_json(
                client,
                f"{_BASE}/auth",
                {"code": code, "hash": _md5_hex(code + key)},
            )
            tok = str(auth.get("token") or "")
            if not tok:
                return None
            _cached_token = tok
            _cached_until = now + _TTL_SEC
            return tok
        except Exception as exc:
            logger.warning("zaycev auth failed: %s", exc)
            _cached_token = None
            _cached_until = 0.0
            return None


async def zaycev_search_raw(
    client: httpx.AsyncClient, token: str, query: str, *, page: int
) -> dict[str, Any]:
    return await _fetch_json(
        client,
        f"{_BASE}/search",
        {
            "access_token": token,
            "query": query,
            "page": str(max(1, page)),
            "type": "all",
            "sort": "",
            "style": "",
        },
    )


async def zaycev_play_url(client: httpx.AsyncClient, token: str, track_id: int) -> str | None:
    try:
        data = await _fetch_json(
            client,
            f"{_BASE}/track/{track_id}/play",
            {"access_token": token, "encoded_identifier": ""},
        )
        u = data.get("url")
        return str(u).strip() if u else None
    except Exception as exc:
        logger.debug("zaycev play failed id=%s: %s", track_id, exc)
        return None
