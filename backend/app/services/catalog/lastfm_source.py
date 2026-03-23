"""
Last.fm API (metadata + charts). Playback: resolve each hit to Zaycev / Hitmotop.

Get an API key: https://www.last.fm/api/account/create
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

import httpx

from app.config import settings
from app.services.catalog.protocol import CatalogSource
from app.services.catalog.resolve_playable import resolve_many_playable, resolve_to_zaycev_or_hitmotop
from app.services.external_track import ExternalTrack

logger = logging.getLogger(__name__)

_API = "https://ws.audioscrobbler.com/2.0/"
_UA = "TelegramMusicCatalog/1.0 (discovery)"


def _api_key() -> str | None:
    k = (settings.lastfm_api_key or "").strip()
    return k or None


async def _lfm_get(client: httpx.AsyncClient, params: dict[str, Any]) -> dict[str, Any] | None:
    key = _api_key()
    if not key:
        return None
    q = {**params, "api_key": key, "format": "json"}
    try:
        r = await client.get(_API, params=q, headers={"User-Agent": _UA}, timeout=22.0)
        if r.status_code >= 400:
            return None
        data = r.json()
        return data if isinstance(data, dict) else None
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

        data = await _lfm_get(
            client,
            {"method": "track.search", "track": q, "limit": min(40, max(10, limit * 2))},
        )
        if not data:
            return []

        matches = (((data.get("results") or {}).get("trackmatches") or {}).get("track")) or []
        if isinstance(matches, dict):
            matches = [matches]

        seeds: list[tuple[str, str, int | None, int | None]] = []
        for item in matches:
            if not isinstance(item, dict):
                continue
            araw = item.get("artist")
            if isinstance(araw, dict):
                artist = str(araw.get("name") or "").strip() or "Unknown"
            else:
                artist = str(araw or "").strip() or "Unknown"
            title = str(item.get("name") or "").strip() or "Unknown"
            if artist == "Unknown" and title == "Unknown":
                continue
            lst = _listeners(item)
            seeds.append((artist, title, lst, None))

        if offset > 0:
            seeds = seeds[offset : offset + limit * 3]
        else:
            seeds = seeds[: max(30, limit * 2)]

        resolved = await resolve_many_playable(client, seeds, concurrency=5, limit=limit)
        return resolved


# --- Discovery: weekday mood tags → Last.fm tag top tracks only ---

# Used by discovery meta (hint) and mood harvest.
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
    Charts + tag top tracks for today's weekday; resolve to Zaycev/Hitmotop only.
    Returns (tracks, display_label).
    """
    if not _api_key():
        return [], "Last.fm"

    wd = datetime.date.today().weekday()
    tags = WEEKDAY_MOOD_TAGS[wd % len(WEEKDAY_MOOD_TAGS)]
    label = f"Last.fm · {', '.join(tags)}"

    seeds: list[tuple[str, str, int | None, int | None]] = []
    seen: set[tuple[str, str]] = set()

    chart = await _lfm_get(client, {"method": "chart.getTopTracks", "limit": 40})
    if chart:
        tracks = (chart.get("tracks") or {}).get("track") or []
        if isinstance(tracks, dict):
            tracks = [tracks]
        for item in tracks:
            if not isinstance(item, dict):
                continue
            araw = item.get("artist")
            if isinstance(araw, dict):
                artist = str(araw.get("name") or "").strip()
            else:
                artist = str(araw or "").strip()
            title = str(item.get("name") or "").strip()
            if not artist or not title:
                continue
            k = (artist.casefold(), title.casefold())
            if k in seen:
                continue
            seen.add(k)
            seeds.append((artist, title, _listeners(item), None))

    per_tag = max(12, min(24, limit // max(1, len(tags)) + 8))
    for tag in tags:
        data = await _lfm_get(
            client,
            {"method": "tag.getTopTracks", "tag": tag, "limit": per_tag},
        )
        if not data:
            continue
        coll = ((data.get("tracks") or {}).get("track")) or []
        if isinstance(coll, dict):
            coll = [coll]
        for item in coll:
            if not isinstance(item, dict):
                continue
            artist = str((item.get("artist") or {}).get("name") or "").strip()
            title = str(item.get("name") or "").strip()
            if not artist or not title:
                continue
            k = (artist.casefold(), title.casefold())
            if k in seen:
                continue
            seen.add(k)
            seeds.append((artist, title, _listeners(item), None))

    seeds.sort(key=lambda s: -(s[2] or 0))
    resolved = await resolve_many_playable(client, seeds[: 80], concurrency=6, limit=limit)
    return resolved, label
