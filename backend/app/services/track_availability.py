"""Lightweight checks that a track's upstream audio can be reached (before showing in lists)."""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import settings
from app.models.track import Track
from app.services.catalog.soundcloud_source import soundcloud_refresh_play_url
from app.services.catalog.zaycev_client import get_zaycev_access_token, zaycev_play_url
from app.services.youtube_audio import extract_youtube_audio_url

logger = logging.getLogger(__name__)

_STREAM_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


async def _probe_direct_url(client: httpx.AsyncClient, url: str, timeout_sec: float) -> bool:
    if not url or not url.startswith(("http://", "https://")):
        return False
    headers = {"User-Agent": _STREAM_BROWSER_UA, "Accept": "*/*", "Range": "bytes=0-0"}
    t = httpx.Timeout(timeout_sec)
    try:
        r = await client.get(url, headers=headers, follow_redirects=True, timeout=t)
        if r.status_code not in (200, 206):
            return False
        return len(r.content) >= 1
    except Exception as exc:
        logger.debug("probe url failed %s: %s", url[:96], exc)
        return False


async def probe_track_playable(client: httpx.AsyncClient, track: Track) -> bool:
    """Return True if we believe /stream could relay bytes for this row (best-effort, fast)."""
    timeout = settings.track_availability_timeout_sec

    if track.source == "youtube_music":
        if not settings.track_probe_youtube:
            return True
        resolved = await asyncio.to_thread(extract_youtube_audio_url, track.audio_url)
        if not resolved:
            return False
        media_url, hdr = resolved
        h = {**hdr, "User-Agent": hdr.get("User-Agent") or _STREAM_BROWSER_UA, "Range": "bytes=0-0"}
        try:
            r = await client.get(
                media_url,
                headers=h,
                follow_redirects=True,
                timeout=httpx.Timeout(timeout),
            )
            return r.status_code in (200, 206) and len(r.content) >= 1
        except Exception as exc:
            logger.debug("youtube probe failed: %s", exc)
            return False

    if track.source == "soundcloud":
        cid = (settings.soundcloud_client_id or "").strip()
        if not cid:
            return False
        try:
            url = await soundcloud_refresh_play_url(client, track.external_id, cid)
        except Exception as exc:
            logger.debug("soundcloud resolve probe failed: %s", exc)
            return False
        if not url:
            return False
        return await _probe_direct_url(client, url, timeout)

    if track.source == "zaycev":
        ztok = await get_zaycev_access_token(client)
        if not ztok:
            return False
        try:
            zid = int(track.external_id)
        except (TypeError, ValueError):
            return False
        try:
            url = await zaycev_play_url(client, ztok, zid)
        except Exception as exc:
            logger.debug("zaycev play probe failed: %s", exc)
            return False
        if not url:
            return False
        return await _probe_direct_url(client, url, timeout)

    return await _probe_direct_url(client, track.audio_url, timeout)


async def filter_tracks_by_availability(
    client: httpx.AsyncClient,
    tracks: list[Track],
) -> list[Track]:
    """Drop tracks that fail `probe_track_playable`, preserving order."""
    if not settings.track_availability_enabled or not tracks:
        return tracks

    sem = asyncio.Semaphore(max(1, settings.track_availability_concurrency))

    async def one(tr: Track) -> tuple[Track, bool]:
        async with sem:
            ok = await probe_track_playable(client, tr)
            return tr, ok

    pairs = await asyncio.gather(*[one(t) for t in tracks])
    return [t for t, ok in pairs if ok]
