"""YouTube Music search via ytmusicapi; playback URLs resolved at stream time with yt-dlp."""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.services.catalog.protocol import CatalogSource
from app.services.external_track import ExternalTrack

logger = logging.getLogger(__name__)

_YT_WATCH = "https://www.youtube.com/watch?v="


def _parse_duration_seconds(raw: object) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, int):
        return max(0, raw)
    if isinstance(raw, float):
        return max(0, int(raw))
    s = str(raw).strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    parts = s.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        return None
    return None


def _thumb_url(thumbnails: object) -> str | None:
    if not isinstance(thumbnails, list) or not thumbnails:
        return None
    last = thumbnails[-1]
    if isinstance(last, dict):
        u = last.get("url")
        return str(u).strip() if u else None
    return None


def _artists(item: dict) -> str:
    artists = item.get("artists")
    if not isinstance(artists, list) or not artists:
        return "Unknown"
    names: list[str] = []
    for a in artists:
        if isinstance(a, dict) and a.get("name"):
            names.append(str(a["name"]).strip())
    return ", ".join(names) if names else "Unknown"


def _search_sync(query: str, offset: int, limit: int) -> list[ExternalTrack]:
    q = query.strip()
    if not q:
        return []

    try:
        from ytmusicapi import YTMusic
    except ImportError:
        logger.error("ytmusicapi is not installed")
        return []

    cap = min(max(offset + limit, limit), 100)
    try:
        yt = YTMusic()
        rows = yt.search(q, filter="songs", limit=cap)
    except Exception as exc:
        logger.warning("youtube music search failed: %s", exc)
        return []

    if not isinstance(rows, list):
        return []

    out: list[ExternalTrack] = []
    for item in rows[offset : offset + limit]:
        if not isinstance(item, dict):
            continue
        vid = item.get("videoId")
        if not vid:
            continue
        vid_s = str(vid).strip()
        if len(vid_s) < 6:
            continue
        title = str(item.get("title") or "Unknown").strip() or "Unknown"
        artist = _artists(item)
        duration_sec = _parse_duration_seconds(item.get("duration"))
        if duration_sec is None:
            duration_sec = _parse_duration_seconds(item.get("duration_seconds"))

        out.append(
            ExternalTrack(
                source="youtube_music",
                external_id=vid_s,
                title=title,
                artist=artist,
                duration_sec=duration_sec,
                audio_url=f"{_YT_WATCH}{vid_s}",
                cover_url=_thumb_url(item.get("thumbnails")),
                license_url="https://www.youtube.com/static?template=terms",
                license_short="youtube",
            )
        )
        if len(out) >= limit:
            break

    return out


class YoutubeMusicCatalogSource(CatalogSource):
    async def search(
        self,
        _client: httpx.AsyncClient,
        query: str,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> list[ExternalTrack]:
        lim = min(max(1, limit), 50)
        off = max(0, offset)
        return await asyncio.to_thread(_search_sync, query, off, lim)
