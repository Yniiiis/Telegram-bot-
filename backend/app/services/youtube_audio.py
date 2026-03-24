"""Resolve a watch URL to a short-lived direct audio stream URL (for proxying via httpx)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# Reuse yt-dlp results briefly: extract_info is CPU/network heavy; same watch URL → same CDN URL for a few minutes.
_yt_lock = threading.Lock()
_yt_url_cache: dict[str, tuple[tuple[str, dict[str, str]], float]] = {}
_YT_CACHE_TTL_SEC = 600.0
_YT_CACHE_MAX = 256
# Bump when format / extractor logic changes so running workers do not reuse stale CDN URLs.
_YT_CACHE_KEY_VER = 4


def _yt_cache_key(watch_url: str) -> str:
    return f"{watch_url}\0{_YT_CACHE_KEY_VER}"


def _yt_cache_get(watch_url: str) -> tuple[str, dict[str, str]] | None:
    now = time.monotonic()
    key = _yt_cache_key(watch_url)
    with _yt_lock:
        ent = _yt_url_cache.get(key)
        if not ent:
            return None
        val, until = ent
        if now > until:
            del _yt_url_cache[key]
            return None
        return val


def _yt_cache_put(watch_url: str, val: tuple[str, dict[str, str]]) -> None:
    key = _yt_cache_key(watch_url)
    with _yt_lock:
        if len(_yt_url_cache) >= _YT_CACHE_MAX:
            drop = next(iter(_yt_url_cache), None)
            if drop is not None:
                del _yt_url_cache[drop]
        _yt_url_cache[key] = (val, time.monotonic() + _YT_CACHE_TTL_SEC)


def _is_bad_stream_protocol(fmt: dict[str, Any]) -> bool:
    """HLS/DASH manifests are a poor match for <audio src> through a simple byte proxy."""
    prot = str(fmt.get("protocol") or "").lower()
    if "m3u8" in prot or "dash" in prot:
        return True
    url = str(fmt.get("url") or "")
    if ".m3u8" in url.lower():
        return True
    return False


def _has_audio(fmt: dict[str, Any]) -> bool:
    ac = fmt.get("acodec")
    return bool(ac) and str(ac) != "none"


def _telegram_webview_audio_score(fmt: dict[str, Any]) -> int:
    """
    Telegram Mini App uses a WebKit-like <audio> stack — Opus-in-WebM often yields MEDIA_ERR_SRC_NOT_SUPPORTED.
    Prefer progressive M4A / AAC-in-MP4.
    """
    ext = str(fmt.get("ext") or "").lower()
    ac_raw = fmt.get("acodec")
    ac = str(ac_raw or "").lower()
    if _is_bad_stream_protocol(fmt):
        return -1
    if (not ac_raw or str(ac_raw) == "none") and ext in ("m4a", "mp4"):
        return 95
    if not _has_audio(fmt):
        return -1
    if ac in ("opus", "vorbis"):
        return 0
    if ext == "webm":
        return 5 if ("aac" in ac or "mp4a" in ac) else 0
    if ext in ("m4a", "mp4", "m4v"):
        return 100
    if "mp4a" in ac or ac == "aac":
        return 90
    if ext == "3gp":
        return 45
    return 25


def _pick_direct_media_url(info: dict[str, Any]) -> tuple[str | None, dict[str, str]]:
    """
    Among all yt-dlp format entries, pick the URL with the best Telegram WebView compatibility score.
    """
    base_hdr = dict(info.get("http_headers") or {})
    candidates: list[tuple[int, str, dict[str, str]]] = []

    def consider(fmt: dict[str, Any]) -> None:
        u = fmt.get("url")
        if not isinstance(u, str) or not u.startswith("http"):
            return
        sc = _telegram_webview_audio_score(fmt)
        if sc <= 0:
            return
        fh = dict(fmt.get("http_headers") or {})
        candidates.append((sc, u, {**base_hdr, **fh}))

    consider(info)

    for fmt in info.get("requested_formats") or []:
        if isinstance(fmt, dict):
            consider(fmt)

    for fmt in info.get("formats") or []:
        if isinstance(fmt, dict):
            consider(fmt)

    if not candidates:
        return None, base_hdr

    candidates.sort(key=lambda x: -x[0])
    _sc, url, hdr = candidates[0]
    return url, hdr


def _yt_common_opts() -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 45,
        "noprogress": True,
        "postprocessors": [],
    }
    cf = (settings.youtube_cookies_file or "").strip()
    if cf:
        opts["cookiefile"] = cf
    return opts


def _extract_once(watch_url: str, format_spec: str, extractor_youtube: dict[str, Any]) -> dict[str, Any] | None:
    try:
        import yt_dlp
    except ImportError:
        logger.error("yt_dlp is not installed")
        return None

    opts: dict[str, Any] = {
        **_yt_common_opts(),
        "format": format_spec,
        "extractor_args": {"youtube": extractor_youtube},
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(watch_url, download=False)
    except Exception as exc:
        logger.debug("yt-dlp extract pass failed (%s): %s", format_spec[:48], exc)
        return None


def _extract_youtube_audio_url_uncached(watch_url: str) -> tuple[str, dict[str, str]] | None:
    """
    Prefer formats that Telegram WebView can decode; avoid falling back to opus/webm when possible.
    """
    passes: list[tuple[str, dict[str, Any]]] = [
        (
            "bestaudio[ext=m4a]/bestaudio[acodec^=mp4a]/bestaudio[acodec=aac]/bestaudio[ext=mp4]",
            {"player_client": ["ios", "web", "android"]},
        ),
        (
            "bestaudio[ext=m4a]/bestaudio[acodec^=mp4a]",
            {"player_client": ["android", "web_creator", "web"]},
        ),
        (
            "bestaudio[acodec!=opus][ext!=webm]/bestaudio[ext=m4a]/bestaudio",
            {"player_client": ["web", "tv_embedded", "android"]},
        ),
        (
            "ba[acodec!=opus][ext!=webm]/ba/b",
            {},
        ),
    ]

    for fmt_spec, yt_args in passes:
        info = _extract_once(watch_url, fmt_spec, yt_args)
        if not info:
            continue
        url, hdr = _pick_direct_media_url(info)
        if url:
            return url, hdr

    logger.warning(
        "yt-dlp: no WebView-safe audio URL for %s (try YOUTUBE_COOKIES_FILE or yt-dlp -U)",
        watch_url[:80],
    )
    return None


def extract_youtube_audio_url(watch_url: str) -> tuple[str, dict[str, str]] | None:
    """
    Returns (media_url, headers_to_send) or None.
    Uses yt-dlp; URLs expire — resolve at playback time, not at search index time.
    """
    hit = _yt_cache_get(watch_url)
    if hit is not None:
        return hit

    resolved = _extract_youtube_audio_url_uncached(watch_url)
    if resolved is not None:
        _yt_cache_put(watch_url, resolved)
    return resolved
