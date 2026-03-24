"""Resolve a watch URL to a short-lived direct audio stream URL (for proxying via httpx)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

# Reuse yt-dlp results briefly: extract_info is CPU/network heavy; same watch URL → same CDN URL for a few minutes.
_yt_lock = threading.Lock()
_yt_url_cache: dict[str, tuple[tuple[str, dict[str, str]], float]] = {}
_YT_CACHE_TTL_SEC = 600.0
_YT_CACHE_MAX = 256


def _yt_cache_get(watch_url: str) -> tuple[str, dict[str, str]] | None:
    now = time.monotonic()
    with _yt_lock:
        ent = _yt_url_cache.get(watch_url)
        if not ent:
            return None
        val, until = ent
        if now > until:
            del _yt_url_cache[watch_url]
            return None
        return val


def _yt_cache_put(watch_url: str, val: tuple[str, dict[str, str]]) -> None:
    with _yt_lock:
        if len(_yt_url_cache) >= _YT_CACHE_MAX:
            # Drop arbitrary oldest bucket (simple cap; avoids unbounded RAM with many distinct URLs).
            drop = next(iter(_yt_url_cache), None)
            if drop is not None:
                del _yt_url_cache[drop]
        _yt_url_cache[watch_url] = (val, time.monotonic() + _YT_CACHE_TTL_SEC)


def extract_youtube_audio_url(watch_url: str) -> tuple[str, dict[str, str]] | None:
    """
    Returns (media_url, headers_to_send) or None.
    Uses yt-dlp; URLs expire — resolve at playback time, not at search index time.
    Cached in-memory per watch_url to speed repeat play / prepare / seek reconnects.
    """
    hit = _yt_cache_get(watch_url)
    if hit is not None:
        return hit

    resolved = _extract_youtube_audio_url_uncached(watch_url)
    if resolved is not None:
        _yt_cache_put(watch_url, resolved)
    return resolved


def _extract_youtube_audio_url_uncached(watch_url: str) -> tuple[str, dict[str, str]] | None:
    try:
        import yt_dlp
    except ImportError:
        logger.error("yt_dlp is not installed")
        return None

    # Prefer modest bitrate for faster start and less buffering in Telegram WebView; avoid postprocessors.
    opts: dict[str, Any] = {
        "format": "bestaudio[abr<=128]/bestaudio[abr<=192]/bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "noprogress": True,
        "postprocessors": [],
        "extractor_args": {
            # Single client = faster extract than trying multiple fallbacks.
            "youtube": {"player_client": ["android", "web"]},
        },
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
