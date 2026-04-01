"""LRU + TTL in-memory cache for catalog search (fewer upstream Hitmotop round-trips)."""

from __future__ import annotations

import asyncio
import copy
import time
from collections import OrderedDict

from app.config import settings


_lock = asyncio.Lock()
_store: OrderedDict[str, tuple[float, list]] = OrderedDict()


def _key(query: str, offset: int, limit: int, *, artist_focus: bool = False, quick: bool = False) -> str:
    af = "1" if artist_focus else "0"
    qk = "1" if quick else "0"
    return f"{query.strip().lower()}\t{offset}\t{limit}\t{af}\t{qk}"


def _touch_lru(k: str) -> None:
    if k in _store:
        _store.move_to_end(k)


def _evict_if_needed() -> None:
    max_e = max(16, settings.search_cache_max_entries)
    while len(_store) > max_e:
        _store.popitem(last=False)


async def get_cached(
    query: str,
    offset: int,
    limit: int,
    *,
    artist_focus: bool = False,
    quick: bool = False,
) -> list | None:
    async with _lock:
        k = _key(query, offset, limit, artist_focus=artist_focus, quick=quick)
        item = _store.get(k)
        if not item:
            return None
        expires_at, rows = item
        if time.monotonic() > expires_at:
            del _store[k]
            return None
        _touch_lru(k)
        return copy.deepcopy(rows)


async def set_cached(
    query: str,
    offset: int,
    limit: int,
    rows: list,
    *,
    artist_focus: bool = False,
    quick: bool = False,
) -> None:
    async with _lock:
        k = _key(query, offset, limit, artist_focus=artist_focus, quick=quick)
        ttl = max(5.0, float(settings.search_cache_ttl_sec))
        _store[k] = (time.monotonic() + ttl, copy.deepcopy(rows))
        _touch_lru(k)
        _evict_if_needed()
