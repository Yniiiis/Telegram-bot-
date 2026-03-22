"""
SoundCloud catalog via api-v2 (same family as soundcloud.com web player).

Public API usage is analogous to demo clients such as:
https://github.com/r-park/soundcloud-ngrx (Angular + Express; MIT).

Requires SOUNDCLOUD_CLIENT_ID (from DevTools on soundcloud.com or developer app).
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import settings
from app.services.catalog.protocol import CatalogSource
from app.services.catalog.search_pipeline import fold_text
from app.services.external_track import ExternalTrack

logger = logging.getLogger(__name__)

_API_BASE = "https://api-v2.soundcloud.com"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def _client_id() -> str | None:
    cid = (settings.soundcloud_client_id or "").strip()
    return cid or None


def _artwork_url(raw: object) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    u = raw.strip()
    if "-large" in u:
        return u.replace("-large", "-t500x500")
    if "{size}" in u:
        return u.replace("{size}", "t500x500")
    return u


def _progressive_transcoding_url(track: dict) -> str | None:
    media = track.get("media")
    if not isinstance(media, dict):
        return None
    trans = media.get("transcodings")
    if not isinstance(trans, list):
        return None
    for t in trans:
        if not isinstance(t, dict):
            continue
        u = t.get("url")
        if not u:
            continue
        fmt = t.get("format")
        proto = ""
        if isinstance(fmt, dict):
            proto = str(fmt.get("protocol") or "")
        if proto == "progressive":
            return str(u)
    return None


async def _resolve_stream_url(client: httpx.AsyncClient, transcoding_api_url: str, cid: str) -> str | None:
    try:
        r = await client.get(
            transcoding_api_url,
            params={"client_id": cid},
            headers={"User-Agent": _UA},
            timeout=25.0,
        )
        if r.status_code >= 400:
            return None
        data = r.json()
        u = data.get("url")
        return str(u).strip() if u else None
    except Exception as exc:
        logger.debug("soundcloud stream resolve failed: %s", exc)
        return None


async def soundcloud_refresh_play_url(
    client: httpx.AsyncClient,
    soundcloud_track_id: str,
    cid: str,
) -> str | None:
    """Fresh progressive stream URL for a SoundCloud track id (expires; call at playback time)."""
    try:
        r = await client.get(
            f"{_API_BASE}/tracks/{soundcloud_track_id}",
            params={"client_id": cid},
            headers={"User-Agent": _UA},
            timeout=25.0,
        )
        if r.status_code >= 400:
            return None
        item = r.json()
        if not isinstance(item, dict):
            return None
    except Exception as exc:
        logger.warning("soundcloud track fetch failed: %s", exc)
        return None
    tc_url = _progressive_transcoding_url(item)
    if not tc_url:
        return None
    return await _resolve_stream_url(client, tc_url, cid)


class SoundCloudCatalogSource(CatalogSource):
    async def search(
        self,
        client: httpx.AsyncClient,
        query: str,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> list[ExternalTrack]:
        cid = _client_id()
        if not cid:
            return []

        q = query.strip()
        if not q:
            return []

        lim = min(max(1, limit), 50)
        off = max(0, offset)

        try:
            r = await client.get(
                f"{_API_BASE}/search/tracks",
                params={
                    "q": q,
                    "client_id": cid,
                    "limit": lim,
                    "offset": off,
                    "linked_partitioning": "1",
                },
                headers={"User-Agent": _UA},
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            logger.warning("soundcloud search failed: %s", exc)
            return []

        if r.status_code >= 400:
            logger.info("soundcloud search http %s (empty catalog)", r.status_code)
            return []

        try:
            payload = r.json()
        except Exception:
            return []

        coll = payload.get("collection")
        if not isinstance(coll, list):
            return []

        sem = asyncio.Semaphore(8)

        async def build_one(item: object) -> ExternalTrack | None:
            if not isinstance(item, dict):
                return None
            tid = item.get("id")
            if tid is None:
                return None
            try:
                tid_str = str(int(tid))
            except (TypeError, ValueError):
                tid_str = str(tid)

            title = str(item.get("title") or "Unknown").strip() or "Unknown"
            user = item.get("user")
            artist = "Unknown"
            if isinstance(user, dict):
                artist = str(user.get("username") or user.get("permalink") or "Unknown").strip() or "Unknown"

            split_done = False
            ua = fold_text(artist) if artist != "Unknown" else ""
            for sep in (" – ", " — ", " - "):
                if sep not in title:
                    continue
                left, _, right = title.partition(sep)
                left, right = left.strip(), right.strip()
                if not left or not right:
                    continue
                if ua and ua == fold_text(left):
                    artist, title = left, right
                    split_done = True
                    break
                if ua and ua == fold_text(right):
                    artist, title = right, left
                    split_done = True
                    break
            if not split_done and (" - " in title or " – " in title or " — " in title):
                artist = "Unknown"

            dur = item.get("duration")
            duration_sec: int | None
            if isinstance(dur, (int, float)):
                duration_sec = max(0, int(dur // 1000))
            else:
                duration_sec = None

            tc_url = _progressive_transcoding_url(item)
            if not tc_url:
                return None

            async with sem:
                audio = await _resolve_stream_url(client, tc_url, cid)
            if not audio:
                return None

            return ExternalTrack(
                source="soundcloud",
                external_id=tid_str,
                title=title,
                artist=artist,
                duration_sec=duration_sec,
                audio_url=audio,
                cover_url=_artwork_url(item.get("artwork_url")),
                license_url="https://soundcloud.com/terms-of-use",
                license_short="soundcloud",
            )

        built = await asyncio.gather(*[build_one(x) for x in coll])
        return [x for x in built if x is not None]
