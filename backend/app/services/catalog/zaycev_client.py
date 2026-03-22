"""
Zaycev.net external API client.

Python port of the protocol implemented in:
https://github.com/pixfid/go-zaycevnet (api/ZClient.go, api/ZUtils.go) —
same base URL, hello → auth(MD5(hello_token + static_key) as hex), and endpoints.

This file does not embed Go code; it reimplements the documented HTTP contract.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.zaycev.net/external"

_lock = asyncio.Lock()
_cached_token: str | None = None
_cached_until: float = 0.0
_TOKEN_TTL_SEC = 45 * 60


def _md5_hex(text: str) -> str:
    """Same as go-zaycevnet api.MD5Hash: MD5 sum as lowercase hex string."""
    return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()


async def _fetch_json(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, str],
) -> dict[str, Any]:
    r = await client.get(url, params=params, timeout=30.0)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and "error" in data:
        err = data["error"]
        if isinstance(err, dict):
            raise RuntimeError(err.get("text") or str(err))
        raise RuntimeError(str(data))
    if not isinstance(data, dict):
        raise RuntimeError("unexpected zaycev json shape")
    return data


class ZaycevNetClient:
    """
    Async counterpart to go-zaycevnet's `api.ZClient`:
    Auth(), Search, AutoComplete, Top, MusicSetList, MusicSetDetail, Genre,
    Artist, Track, Options, Download, Play.
    """

    def __init__(self, http_client: httpx.AsyncClient, static_key: str) -> None:
        self._http = http_client
        self.static_key = static_key.strip()
        self.access_token: str | None = None

    async def hello(self) -> str:
        data = await _fetch_json(self._http, f"{API_BASE}/hello", {})
        code = str(data.get("token") or "")
        if not code:
            raise RuntimeError("zaycev hello: empty token")
        return code

    async def auth_with_hello_code(self, hello_token: str) -> str:
        h = _md5_hex(hello_token + self.static_key)
        data = await _fetch_json(
            self._http,
            f"{API_BASE}/auth",
            {"code": hello_token, "hash": h},
        )
        tok = str(data.get("token") or "")
        if not tok:
            raise RuntimeError("zaycev auth: empty token")
        self.access_token = tok
        return tok

    async def full_auth(self) -> str:
        if not self.static_key:
            raise RuntimeError("Empty static key")
        hc = await self.hello()
        return await self.auth_with_hello_code(hc)

    def _tok_params(self) -> dict[str, str]:
        if not self.access_token:
            raise RuntimeError("not authenticated")
        return {"access_token": self.access_token}

    async def search(
        self,
        query: str,
        page: int,
        *,
        type_: str = "all",
        sort: str = "",
        style: str = "",
    ) -> dict[str, Any]:
        p = self._tok_params()
        p.update(
            {
                "query": query,
                "page": str(max(1, page)),
                "type": type_,
                "sort": sort,
                "style": style,
            }
        )
        return await _fetch_json(self._http, f"{API_BASE}/search", p)

    async def autocomplete(self, query: str) -> dict[str, Any]:
        p = self._tok_params()
        p["query"] = query
        return await _fetch_json(self._http, f"{API_BASE}/autocomplete", p)

    async def top(self, page: int) -> dict[str, Any]:
        p = self._tok_params()
        p["page"] = str(max(1, page))
        return await _fetch_json(self._http, f"{API_BASE}/top", p)

    async def music_set_list(self, page: int) -> dict[str, Any]:
        p = self._tok_params()
        p["page"] = str(max(1, page))
        return await _fetch_json(self._http, f"{API_BASE}/musicset/list", p)

    async def music_set_detail(self, set_id: int) -> dict[str, Any]:
        p = self._tok_params()
        p["id"] = str(set_id)
        return await _fetch_json(self._http, f"{API_BASE}/musicset/detail", p)

    async def genre(self, genre_name: str, page: int) -> dict[str, Any]:
        p = self._tok_params()
        p["page"] = str(max(1, page))
        p["genre"] = genre_name
        return await _fetch_json(self._http, f"{API_BASE}/genre", p)

    async def artist(self, artist_id: int) -> dict[str, Any]:
        p = self._tok_params()
        return await _fetch_json(self._http, f"{API_BASE}/artist/{artist_id}", p)

    async def track(self, track_id: int) -> dict[str, Any]:
        p = self._tok_params()
        return await _fetch_json(self._http, f"{API_BASE}/track/{track_id}", p)

    async def options(self) -> dict[str, Any]:
        return await _fetch_json(self._http, f"{API_BASE}/options", self._tok_params())

    async def download(self, track_id: int) -> dict[str, Any]:
        p = self._tok_params()
        p["encoded_identifier"] = ""
        return await _fetch_json(self._http, f"{API_BASE}/track/{track_id}/download/", p)

    async def play(self, track_id: int) -> dict[str, Any]:
        p = self._tok_params()
        p["encoded_identifier"] = ""
        return await _fetch_json(self._http, f"{API_BASE}/track/{track_id}/play", p)


async def get_zaycev_access_token(client: httpx.AsyncClient) -> str | None:
    """Cached access token (shared across requests)."""
    key = (settings.zaycev_static_key or "").strip()
    if not key:
        return None

    global _cached_token, _cached_until
    now = time.monotonic()
    async with _lock:
        if _cached_token and now < _cached_until:
            return _cached_token
        try:
            zc = ZaycevNetClient(client, key)
            await zc.full_auth()
            tok = zc.access_token
            if not tok:
                return None
            _cached_token = tok
            _cached_until = now + _TOKEN_TTL_SEC
            return tok
        except Exception as exc:
            logger.warning("zaycev auth failed: %s", exc)
            _cached_token = None
            _cached_until = 0.0
            return None


async def zaycev_search_raw(
    client: httpx.AsyncClient, token: str, query: str, *, page: int
) -> dict[str, Any]:
    """Search (same params as go-zaycevnet Search + README example)."""
    zc = ZaycevNetClient(client, (settings.zaycev_static_key or "").strip())
    zc.access_token = token
    return await zc.search(query.strip(), page)


async def zaycev_play_url(client: httpx.AsyncClient, token: str, track_id: int) -> str | None:
    zc = ZaycevNetClient(client, (settings.zaycev_static_key or "").strip())
    zc.access_token = token
    try:
        data = await zc.play(track_id)
        u = data.get("url")
        return str(u).strip() if u else None
    except Exception as exc:
        logger.debug("zaycev play failed id=%s: %s", track_id, exc)
        return None


async def zaycev_track_json(client: httpx.AsyncClient, token: str, track_id: int) -> dict[str, Any] | None:
    """Optional: full track metadata (`ZClient.Track` in go-zaycevnet)."""
    zc = ZaycevNetClient(client, (settings.zaycev_static_key or "").strip())
    zc.access_token = token
    try:
        return await zc.track(track_id)
    except Exception as exc:
        logger.debug("zaycev track failed id=%s: %s", track_id, exc)
        return None
