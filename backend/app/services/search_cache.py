"""Short-lived in-memory cache for catalog search (reduces upstream calls)."""

from __future__ import annotations

import asyncio
import copy
import time

TTL_SEC = 300.0
MAX_ENTRIES = 256

_lock = asyncio.Lock()
_store: dict[str, tuple[float, list]] = {}


def _key(query: str, offset: int, limit: int, *, artist_focus: bool = False) -> str:
    af = "1" if artist_focus else "0"
    return f"{query.strip().lower()}\t{offset}\t{limit}\t{af}"


async def get_cached(query: str, offset: int, limit: int, *, artist_focus: bool = False) -> list | None:
    async with _lock:
        k = _key(query, offset, limit, artist_focus=artist_focus)
        item = _store.get(k)
        if not item:
            return None
        expires_at, rows = item
        if time.monotonic() > expires_at:
            del _store[k]
            return None
        return copy.deepcopy(rows)


async def set_cached(
    query: str, offset: int, limit: int, rows: list, *, artist_focus: bool = False
) -> None:
    async with _lock:
        if len(_store) >= MAX_ENTRIES:
            # Drop arbitrary oldest half by clearing (simple; cache is best-effort)
            _store.clear()
        k = _key(query, offset, limit, artist_focus=artist_focus)
        _store[k] = (time.monotonic() + TTL_SEC, copy.deepcopy(rows))
