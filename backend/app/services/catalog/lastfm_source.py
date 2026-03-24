"""
Last.fm API (metadata + charts). Playback: resolve each hit to Zaycev / Hitmotop.

Get an API key: https://www.last.fm/api/account/create
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any

import httpx

from app.config import settings
from app.services.catalog.protocol import CatalogSource
from app.services.catalog.resolve_playable import resolve_many_playable
from app.services.external_track import ExternalTrack

logger = logging.getLogger(__name__)

_API = "https://ws.audioscrobbler.com/2.0/"
_UA = "TelegramMusicCatalog/1.0 (discovery)"

# Last.fm free tier: avoid huge bursts; these caps keep latency reasonable.
_LFM_SEARCH_PAGE_SIZE = 30  # API default max per page for track.search
_LFM_MAX_SEEDS_SEARCH = 140
_LFM_RESOLVE_LIMIT_SEARCH = 56  # playable rows to collect before caller trims
_LFM_MOOD_CHART_TRACKS = 50
_LFM_MOOD_TAG_PAGE = 28
_LFM_MOOD_TOP_ARTISTS = 12
_LFM_MOOD_ARTIST_TOP_EACH = 8


def _api_key() -> str | None:
    k = (settings.lastfm_api_key or "").strip()
    return k or None


async def _lfm_get(client: httpx.AsyncClient, params: dict[str, Any]) -> dict[str, Any] | None:
    key = _api_key()
    if not key:
        return None
    q = {**params, "api_key": key, "format": "json"}
    try:
        r = await client.get(_API, params=q, headers={"User-Agent": _UA}, timeout=25.0)
        if r.status_code >= 400:
            return None
        data = r.json()
        if not isinstance(data, dict):
            return None
        if data.get("error") is not None:
            logger.debug("last.fm api error %s: %s", data.get("error"), data.get("message"))
            return None
        return data
    except Exception as exc:
        logger.debug("last.fm request failed: %s", exc)
        return None


def _listeners(track: dict[str, Any]) -> int | None:
    raw = track.get("listeners")
    if raw is None and isinstance(track.get("playcount"), str):
        raw = track.get("playcount")
    try:
        return int(raw) if raw is not None and str(raw).isdigit() else None
    except (TypeError, ValueError):
        return None


def _seed_key(artist: str, title: str) -> tuple[str, str]:
    return (artist.casefold().strip(), title.casefold().strip())


def _add_seed(
    seeds: list[tuple[str, str, int | None, int | None]],
    seen: set[tuple[str, str]],
    artist: str,
    title: str,
    lst: int | None,
) -> None:
    a, t = artist.strip(), title.strip()
    if not a or not t:
        return
    if a.lower() == "unknown" and t.lower() == "unknown":
        return
    k = _seed_key(a, t)
    if k in seen:
        return
    seen.add(k)
    seeds.append((a, t, lst, None))


def _parse_trackmatch_items(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not data:
        return []
    matches = (((data.get("results") or {}).get("trackmatches") or {}).get("track")) or []
    if isinstance(matches, dict):
        return [matches]
    if isinstance(matches, list):
        return [m for m in matches if isinstance(m, dict)]
    return []


def _parse_top_tracks_block(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not data:
        return []
    coll = ((data.get("tracks") or {}).get("track")) or []
    if isinstance(coll, dict):
        return [coll]
    if isinstance(coll, list):
        return [x for x in coll if isinstance(x, dict)]
    return []


async def _append_track_search_seeds(
    client: httpx.AsyncClient,
    q: str,
    offset: int,
    seeds: list[tuple[str, str, int | None, int | None]],
    seen: set[tuple[str, str]],
) -> None:
    page = max(1, offset // _LFM_SEARCH_PAGE_SIZE + 1)
    data = await _lfm_get(
        client,
        {
            "method": "track.search",
            "track": q,
            "limit": str(_LFM_SEARCH_PAGE_SIZE),
            "page": str(page),
        },
    )
    items = _parse_trackmatch_items(data)
    start = offset % _LFM_SEARCH_PAGE_SIZE
    for item in items[start:]:
        araw = item.get("artist")
        if isinstance(araw, dict):
            artist = str(araw.get("name") or "").strip() or "Unknown"
        else:
            artist = str(araw or "").strip() or "Unknown"
        title = str(item.get("name") or "").strip() or "Unknown"
        _add_seed(seeds, seen, artist, title, _listeners(item))


async def _append_artist_branch(
    client: httpx.AsyncClient,
    q: str,
    seeds: list[tuple[str, str, int | None, int | None]],
    seen: set[tuple[str, str]],
) -> None:
    adata = await _lfm_get(
        client,
        {"method": "artist.search", "artist": q, "limit": "20"},
    )
    if not adata:
        return
    block = (adata.get("results") or {}).get("artistmatches") or {}
    raw = block.get("artist") or []
    artists: list[dict[str, Any]] = [raw] if isinstance(raw, dict) else [x for x in raw if isinstance(x, dict)]

    sem = asyncio.Semaphore(4)

    async def top_for(a: dict[str, Any]) -> None:
        name = str(a.get("name") or "").strip()
        if len(name) < 2:
            return
        async with sem:
            tdata = await _lfm_get(
                client,
                {"method": "artist.getTopTracks", "artist": name, "limit": "14"},
            )
        for item in _parse_top_tracks_block(tdata):
            artist = str((item.get("artist") or {}).get("name") or name).strip()
            title = str(item.get("name") or "").strip()
            _add_seed(seeds, seen, artist, title, _listeners(item))

    await asyncio.gather(*[top_for(a) for a in artists[:6]])


async def _append_tag_branch(
    client: httpx.AsyncClient,
    q: str,
    seeds: list[tuple[str, str, int | None, int | None]],
    seen: set[tuple[str, str]],
) -> None:
    if len(q) < 2 or len(q) > 60:
        return
    tdata = await _lfm_get(
        client,
        {"method": "tag.getTopTracks", "tag": q, "limit": "32"},
    )
    for item in _parse_top_tracks_block(tdata):
        artist = str((item.get("artist") or {}).get("name") or "").strip()
        title = str(item.get("name") or "").strip()
        _add_seed(seeds, seen, artist, title, _listeners(item))


class LastFmCatalogSource(CatalogSource):
    async def search(
        self,
        client: httpx.AsyncClient,
        query: str,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> list[ExternalTrack]:
        q = query.strip()
        if not q or not _api_key():
            return []

        seeds: list[tuple[str, str, int | None, int | None]] = []
        seen: set[tuple[str, str]] = set()

        await _append_track_search_seeds(client, q, offset, seeds, seen)
        await asyncio.gather(
            _append_artist_branch(client, q, seeds, seen),
            _append_tag_branch(client, q, seeds, seen),
        )

        seeds.sort(key=lambda s: -(s[2] or 0))
        seeds = seeds[:_LFM_MAX_SEEDS_SEARCH]

        resolve_cap = min(_LFM_RESOLVE_LIMIT_SEARCH, max(limit * 3, limit + 24))
        resolved = await resolve_many_playable(
            client,
            seeds,
            concurrency=8,
            limit=resolve_cap,
        )
        return resolved[:limit]


# --- Discovery: weekday mood tags → Last.fm (charts + tags + top artists) ---

WEEKDAY_MOOD_TAGS: list[list[str]] = [
    ["indie", "alternative"],
    ["electronic", "synthpop"],
    ["rock", "metal"],
    ["hip hop", "rap"],
    ["pop", "dance"],
    ["party", "house"],
    ["chill", "ambient"],
]


async def collect_lastfm_mood_tracks(client: httpx.AsyncClient, *, limit: int) -> tuple[list[ExternalTrack], str]:
    """
    Charts + tag top tracks + chart top artists' top tracks; resolve to Zaycev/Hitmotop.
    """
    if not _api_key():
        return [], "Last.fm"

    wd = datetime.date.today().weekday()
    tags = WEEKDAY_MOOD_TAGS[wd % len(WEEKDAY_MOOD_TAGS)]
    label = f"Last.fm · {', '.join(tags)}"

    seeds: list[tuple[str, str, int | None, int | None]] = []
    seen: set[tuple[str, str]] = set()

    chart = await _lfm_get(client, {"method": "chart.getTopTracks", "limit": str(_LFM_MOOD_CHART_TRACKS)})
    for item in _parse_top_tracks_block(chart):
        araw = item.get("artist")
        if isinstance(araw, dict):
            artist = str(araw.get("name") or "").strip()
        else:
            artist = str(araw or "").strip()
        title = str(item.get("name") or "").strip()
        _add_seed(seeds, seen, artist, title, _listeners(item))

    per_tag = max(14, min(_LFM_MOOD_TAG_PAGE, limit // max(1, len(tags)) + 10))
    for tag in tags:
        data = await _lfm_get(
            client,
            {"method": "tag.getTopTracks", "tag": tag, "limit": str(per_tag)},
        )
        for item in _parse_top_tracks_block(data):
            artist = str((item.get("artist") or {}).get("name") or "").strip()
            title = str(item.get("name") or "").strip()
            _add_seed(seeds, seen, artist, title, _listeners(item))

    art_chart = await _lfm_get(client, {"method": "chart.getTopArtists", "limit": str(_LFM_MOOD_TOP_ARTISTS)})
    if art_chart:
        ablock = (art_chart.get("artists") or {}).get("artist") or []
        if isinstance(ablock, dict):
            ablock = [ablock]
        names = [str(a.get("name") or "").strip() for a in ablock if isinstance(a, dict) and a.get("name")]
        sem = asyncio.Semaphore(4)

        async def artist_top(name: str) -> None:
            if not name:
                return
            async with sem:
                tdata = await _lfm_get(
                    client,
                    {
                        "method": "artist.getTopTracks",
                        "artist": name,
                        "limit": str(_LFM_MOOD_ARTIST_TOP_EACH),
                    },
                )
            for item in _parse_top_tracks_block(tdata):
                artist = str((item.get("artist") or {}).get("name") or name).strip()
                title = str(item.get("name") or "").strip()
                _add_seed(seeds, seen, artist, title, _listeners(item))

        await asyncio.gather(*[artist_top(n) for n in names[:_LFM_MOOD_TOP_ARTISTS]])

    seeds.sort(key=lambda s: -(s[2] or 0))
    mood_resolve = min(120, max(limit * 4, limit + 40))
    resolved = await resolve_many_playable(
        client,
        seeds[:140],
        concurrency=8,
        limit=mood_resolve,
    )
    return resolved, label
