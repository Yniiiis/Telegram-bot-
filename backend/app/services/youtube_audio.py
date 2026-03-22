"""Resolve a watch URL to a short-lived direct audio stream URL (for proxying via httpx)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def extract_youtube_audio_url(watch_url: str) -> tuple[str, dict[str, str]] | None:
    """
    Returns (media_url, headers_to_send) or None.
    Uses yt-dlp; URLs expire — resolve at playback time, not at search index time.
    """
    try:
        import yt_dlp
    except ImportError:
        logger.error("yt_dlp is not installed")
        return None

    opts: dict[str, Any] = {
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "extractor_args": {"youtube": {"player_client": ["android_creator", "web"]}},
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(watch_url, download=False)
    except Exception as exc:
        logger.warning("yt-dlp extract failed for %s: %s", watch_url, exc)
        return None

    if not info:
        return None

    base_hdr = dict(info.get("http_headers") or {})
    url = info.get("url")
    if url:
        return str(url), base_hdr

    for f in reversed(info.get("formats") or []):
        if not isinstance(f, dict):
            continue
        u, ac = f.get("url"), f.get("acodec")
        if u and ac and str(ac) != "none":
            fh = dict(f.get("http_headers") or {})
            merged = {**base_hdr, **fh}
            return str(u), merged

    return None
