"""Resolve a playable upstream URL for a Track (Hitmotop direct MP3 only in this deployment)."""

from __future__ import annotations

from typing import Literal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.track import Track

StreamKind = Literal["direct"]


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
    _ = (db, http)
    if track.source != "hitmotop":
        raise PlaybackResolveError(
            "UNSUPPORTED_SOURCE",
            "Only Hitmotop (rus.hitmotop.com) tracks are supported. Search again to add tracks.",
        )
    media_url = (track.audio_url or "").strip()
    if not media_url.startswith("http"):
        raise PlaybackResolveError(
            "NO_AUDIO_URL",
            "This track has no playable URL. Try another result from Hitmotop.",
        )
    return media_url, {}, "direct"
