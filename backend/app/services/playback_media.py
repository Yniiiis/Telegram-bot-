"""Resolve a playable upstream URL for a Track (shared by /stream and /tracks/.../prepare)."""

from __future__ import annotations

import asyncio
from typing import Literal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.track import Track
from app.services.catalog.soundcloud_source import soundcloud_refresh_play_url
from app.services.catalog.zaycev_client import get_zaycev_access_token, zaycev_play_url
from app.services.youtube_audio import extract_youtube_audio_url

StreamKind = Literal["youtube", "direct"]


class PlaybackResolveError(Exception):
    __slots__ = ("code", "message")

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


async def resolve_playback_media(
    db: AsyncSession,
    track: Track,
    http: httpx.AsyncClient,
) -> tuple[str, dict[str, str], StreamKind]:
    """
    Returns (media_url, extra_headers_for_get, kind).
    For youtube, extra_headers must be merged into the upstream request.
    """
    if track.source == "youtube_music":
        resolved = await asyncio.to_thread(extract_youtube_audio_url, track.audio_url)
        if not resolved:
            raise PlaybackResolveError(
                "YOUTUBE_EXTRACT_FAILED",
                "Could not resolve YouTube audio. Install yt-dlp or try another track.",
            )
        media_url, upstream_headers = resolved
        return media_url, dict(upstream_headers), "youtube"

    media_url = track.audio_url
    if track.source == "soundcloud":
        sc_cid = (settings.soundcloud_client_id or "").strip()
        if not sc_cid:
            raise PlaybackResolveError(
                "SOUNDCLOUD_NO_CLIENT_ID",
                "SoundCloud client_id is not configured.",
            )
        fresh = await soundcloud_refresh_play_url(http, track.external_id, sc_cid)
        if not fresh:
            raise PlaybackResolveError(
                "SOUNDCLOUD_RESOLVE_FAILED",
                "Could not resolve SoundCloud stream for this track.",
            )
        if fresh != track.audio_url:
            track.audio_url = fresh
            await db.commit()
        media_url = fresh

    if track.source == "zaycev":
        ztok = await get_zaycev_access_token(http)
        if not ztok:
            raise PlaybackResolveError(
                "ZAYCEV_AUTH",
                "Could not obtain Zaycev access token.",
            )
        try:
            zid = int(track.external_id)
        except (TypeError, ValueError) as exc:
            raise PlaybackResolveError("ZAYCEV_BAD_ID", "Invalid Zaycev track id.") from exc
        fresh = await zaycev_play_url(http, ztok, zid)
        if not fresh:
            raise PlaybackResolveError(
                "ZAYCEV_PLAY",
                "Zaycev did not return a play URL for this track.",
            )
        if fresh != track.audio_url:
            track.audio_url = fresh
            await db.commit()
        media_url = fresh

    return media_url, {}, "direct"
