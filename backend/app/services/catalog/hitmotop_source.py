"""
Hitmotop / Hitmo HTML catalog.

Parsing: `music_provider.hitmotop_parse` (lxml XPath + BS4/lxml fallback).
HTTP: retries + backoff on 429/5xx (see config).
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.services.catalog.protocol import CatalogSource
from app.services.catalog.search_pipeline import normalize_track_metadata, sanitize_track
from app.services.external_track import ExternalTrack
from app.services.music_provider.hitmotop_parse import extract_track_pairs

logger = logging.getLogger(__name__)

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

_mirror_lock = asyncio.Lock()
_cached_mirror: tuple[str, float] | None = None
_MIRROR_TTL_SEC = 3600.0


def _hitmotop_headers(base: str) -> dict[str, str]:
    b = base.rstrip("/")
    return {
        "User-Agent": _BROWSER_UA,
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Referer": f"{b}/",
        "Accept-Encoding": "gzip, deflate, br",
    }


def _tracks_from_pairs(
    pairs: list[tuple[str, str, str, str]],
    base: str,
    query: str,
    *,
    offset: int,
    limit: int,
) -> list[ExternalTrack]:
    start = max(0, offset)
    cap = min(limit, 80)
    slice_pairs = pairs[start : start + cap]
    out: list[ExternalTrack] = []
    for sid, title, mp3, artist in slice_pairs:
        art = " ".join((artist or "Unknown").split()).strip() or "Unknown"
        ttl = " ".join((title or "Unknown").split()).strip() or "Unknown"
        raw = ExternalTrack(
            source="hitmotop",
            external_id=sid,
            title=ttl,
            artist=art,
            duration_sec=None,
            audio_url=mp3,
            cover_url=None,
            license_url=f"{base.rstrip('/')}/copyright",
            license_short="hitmotop",
        )
        out.append(sanitize_track(normalize_track_metadata(raw, query=query)))
    return out


async def _resolve_effective_base(client: httpx.AsyncClient) -> str:
    configured = (settings.hitmotop_base_url or "https://rus.hitmotop.com").rstrip("/")
    lookup = (settings.hitmotop_mirror_lookup_url or "").strip()
    if not lookup:
        return configured

    global _cached_mirror
    now = time.monotonic()
    if _cached_mirror and (now - _cached_mirror[1]) < _MIRROR_TTL_SEC:
        return _cached_mirror[0]

    async with _mirror_lock:
        now = time.monotonic()
        if _cached_mirror and (now - _cached_mirror[1]) < _MIRROR_TTL_SEC:
            return _cached_mirror[0]
        try:
            r = await client.get(
                lookup,
                timeout=8.0,
                follow_redirects=True,
                headers={"User-Agent": _BROWSER_UA, "Accept": "text/html,*/*"},
            )
            if r.status_code < 400 and r.text:
                soup = BeautifulSoup(r.text, "lxml")
                a = soup.select_one("a.link.link--with-badge") or soup.select_one("a.link--with-badge")
                href = (a.get("href") or "").strip() if a else ""
                if href.startswith("http"):
                    resolved = href.rstrip("/")
                    _cached_mirror = (resolved, time.monotonic())
                    logger.info("hitmotop mirror resolved to %s", resolved)
                    return resolved
        except Exception as exc:
            logger.debug("hitmotop mirror lookup failed: %s", exc)
        return configured


class HitmotopCatalogSource(CatalogSource):
    """rus.hitmotop.com (+ optional mirror): fast parse + /search/start pagination."""

    async def _get_html(
        self,
        client: httpx.AsyncClient,
        url: str,
        base: str,
        *,
        params: dict[str, str] | None = None,
        timeout: float = 22.0,
    ) -> str | None:
        headers = _hitmotop_headers(base)
        attempts = max(1, settings.hitmotop_http_max_attempts)
        backoff = max(0.05, settings.hitmotop_http_retry_backoff_sec)

        for attempt in range(attempts):
            try:
                r = await client.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=timeout,
                    follow_redirects=True,
                )
            except httpx.HTTPError as exc:
                logger.warning("hitmotop request failed %s: %s", url[:96], exc)
                if attempt + 1 < attempts:
                    await asyncio.sleep(backoff * (2**attempt))
                continue

            if r.status_code == 429:
                logger.info("hitmotop 429 %s attempt=%s", url[:96], attempt + 1)
                if attempt + 1 < attempts:
                    await asyncio.sleep(backoff * (2**attempt))
                continue

            if r.status_code >= 500:
                logger.info("hitmotop http %s for %s", r.status_code, url[:96])
                if attempt + 1 < attempts:
                    await asyncio.sleep(backoff * (2**attempt))
                continue

            if r.status_code >= 400:
                logger.info("hitmotop http %s for %s", r.status_code, url[:96])
                return None

            return r.text

        return None

    async def _base_resolved(self, client: httpx.AsyncClient) -> str:
        return await _resolve_effective_base(client)

    async def chart_tracks_slice(
        self,
        client: httpx.AsyncClient,
        offset: int,
        limit: int,
    ) -> tuple[list[ExternalTrack], bool]:
        t0 = time.perf_counter()
        base = await self._base_resolved(client)
        path = (settings.hitmotop_charts_path or "/2026").strip()
        if not path.startswith("/"):
            path = "/" + path
        url = f"{base}{path}"
        html = await self._get_html(client, url, base, timeout=28.0)
        if not html:
            return [], False
        t_parse0 = time.perf_counter()
        pairs = extract_track_pairs(html, base)
        parse_ms = (time.perf_counter() - t_parse0) * 1000.0
        if settings.hitmotop_log_parse_ms:
            logger.info(
                "hitmotop chart parse_ms=%.1f pairs=%s total_ms=%.1f",
                parse_ms,
                len(pairs),
                (time.perf_counter() - t0) * 1000.0,
            )
        tracks = _tracks_from_pairs(pairs, base, "", offset=offset, limit=limit)
        start = max(0, offset)
        has_more = start + len(tracks) < len(pairs)
        return tracks, has_more

    async def fetch_chart_tracks(
        self,
        client: httpx.AsyncClient,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> list[ExternalTrack]:
        rows, _ = await self.chart_tracks_slice(client, offset, limit)
        return rows

    async def search(
        self,
        client: httpx.AsyncClient,
        query: str,
        *,
        offset: int = 0,
        limit: int = 20,
        quick: bool = False,
    ) -> list[ExternalTrack]:
        q = query.strip()
        if not q:
            return []

        timeout = (
            settings.hitmotop_search_quick_timeout_sec
            if quick
            else settings.hitmotop_search_normal_timeout_sec
        )
        t0 = time.perf_counter()
        base = await self._base_resolved(client)
        page_step = max(1, settings.hitmotop_page_size)
        pairs: list[tuple[str, str, str, str]] = []
        need = min(limit, 80)

        if settings.hitmotop_search_start_pagination:
            page_start = (max(0, offset) // page_step) * page_step
            url = f"{base}/search/start/{page_start}"
            html = await self._get_html(client, url, base, params={"q": q}, timeout=timeout)
            if html:
                inner = max(0, offset - page_start)
                t_parse0 = time.perf_counter()
                pairs = extract_track_pairs(
                    html, base, skip_valid=inner, take_valid=need
                )
                if settings.hitmotop_log_parse_ms:
                    logger.info(
                        "hitmotop search parse_ms=%.1f pairs=%s q=%r",
                        (time.perf_counter() - t_parse0) * 1000.0,
                        len(pairs),
                        q[:48],
                    )

        if not pairs:
            html = await self._get_html(client, f"{base}/search", base, params={"q": q}, timeout=timeout)
            if html:
                t_parse0 = time.perf_counter()
                pairs = extract_track_pairs(
                    html, base, skip_valid=max(0, offset), take_valid=need
                )
                if settings.hitmotop_log_parse_ms:
                    logger.info(
                        "hitmotop search fallback parse_ms=%.1f pairs=%s",
                        (time.perf_counter() - t_parse0) * 1000.0,
                        len(pairs),
                    )

        if not pairs:
            return []

        if settings.hitmotop_log_parse_ms:
            logger.info(
                "hitmotop search total_ms=%.1f results_slice=%s",
                (time.perf_counter() - t0) * 1000.0,
                min(limit, len(pairs)),
            )

        return _tracks_from_pairs(pairs, base, q, offset=0, limit=limit)


async def refresh_hitmotop_mp3_from_song_page(
    source: str,
    external_id: str,
    client: httpx.AsyncClient,
) -> str | None:
    """
    Re-parse the Hitmotop song page to get a fresh direct MP3 URL.
    Stored CDN links can 403/404 while the site still serves a new link for the same song id.
    """
    if source != "hitmotop":
        return None
    ext = (external_id or "").strip()
    if not ext.isdigit():
        return None
    base = await _resolve_effective_base(client)
    url = f"{base}/song/{ext}"
    src = HitmotopCatalogSource()
    html = await src._get_html(client, url, base, timeout=18.0)
    if not html:
        return None
    pairs = extract_track_pairs(html, base)
    for sid, _title, mp3, _artist in pairs:
        if sid == ext:
            return mp3
    if pairs:
        return pairs[0][2]
    return None
