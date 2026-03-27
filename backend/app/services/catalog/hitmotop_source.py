"""
Hitmotop / Hitmo HTML catalog.

Parsing aligned with JadeMusic API (jademusic-api) selectors and search pagination:
https://github.com/nshib00/jademusic-api — div.track__info, a.track__download-btn,
search URL pattern /search/start/{n}?q= (step = hitmotop_page_size, default 48).
Fallback: legacy walk of /song/ + /get/music/*.mp3 anchors.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import zlib
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.services.catalog.protocol import CatalogSource
from app.services.catalog.search_pipeline import normalize_track_metadata, sanitize_track
from app.services.external_track import ExternalTrack

logger = logging.getLogger(__name__)

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# JadeMusic: generics/html.py
_JADE_TRACK_ROOT = "div.track__info"
_JADE_DL = "a.track__download-btn"
_JADE_ARTIST = "div.track__desc"
_JADE_TITLE = "div.track__title"

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


def _id_from_mp3(mp3: str) -> str:
    m = re.search(r"/(\d+)\.mp3", mp3, re.IGNORECASE)
    if m:
        return m.group(1)
    return str(zlib.adler32(mp3.encode("utf-8", errors="ignore")) & 0x7FFFFFFF)


def _pairs_jade(soup: BeautifulSoup, base: str) -> list[tuple[str, str, str, str]]:
    """(external_id, title, mp3_url, artist) via JadeMusic-style DOM."""
    out: list[tuple[str, str, str, str]] = []
    for div in soup.select(_JADE_TRACK_ROOT):
        dl = div.select_one(_JADE_DL)
        if not dl:
            continue
        href = (dl.get("href") or "").strip()
        if not href or ".mp3" not in href.lower():
            continue
        mp3 = urljoin(base, href)
        artist_el = div.select_one(_JADE_ARTIST)
        title_el = div.select_one(_JADE_TITLE)
        artist = " ".join(artist_el.get_text().split()) if artist_el else "Unknown"
        title = " ".join(title_el.get_text().split()) if title_el else "Unknown"

        sid: str | None = None
        for la in div.select('a[href*="/song/"]'):
            m = re.search(r"/song/(\d+)", la.get("href") or "")
            if m:
                sid = m.group(1)
                break
        if not sid:
            sid = _id_from_mp3(mp3)

        out.append((sid, title, mp3, artist or "Unknown"))
    return out


def _pairs_legacy_soup(soup: BeautifulSoup, base: str) -> list[tuple[str, str, str, str]]:
    out: list[tuple[str, str, str, str]] = []
    pending_id: str | None = None
    pending_title: str | None = None

    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        text = " ".join((a.get_text() or "").split()).strip()

        if "/song/" in href:
            path = urlparse(href).path
            part = path.split("/song/")[-1].split("/")[0]
            if part.isdigit():
                pending_id = part
                pending_title = text or "Unknown"
            continue

        if "/get/music/" in href and href.lower().endswith(".mp3") and pending_id:
            mp3 = urljoin(base, href)
            title = pending_title or "Unknown"
            out.append((pending_id, title, mp3, "Unknown"))
            pending_id = None
            pending_title = None

    return out


def _all_pairs(html: str, base: str) -> list[tuple[str, str, str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    if settings.hitmotop_use_jade_selectors:
        jade = _pairs_jade(soup, base)
        if jade:
            return jade
    return _pairs_legacy_soup(soup, base)


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
    """Optional mirror from gde-hitmo.org (JadeMusic url.py); else configured base."""
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
                soup = BeautifulSoup(r.text, "html.parser")
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
    """rus.hitmotop.com (+ optional mirror): Jade-style fast parse + /search/start pagination."""

    async def _get_html(
        self,
        client: httpx.AsyncClient,
        url: str,
        base: str,
        *,
        params: dict[str, str] | None = None,
        timeout: float = 22.0,
    ) -> str | None:
        try:
            r = await client.get(
                url,
                params=params,
                headers=_hitmotop_headers(base),
                timeout=timeout,
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            logger.warning("hitmotop request failed %s: %s", url[:96], exc)
            return None
        if r.status_code >= 400:
            logger.info("hitmotop http %s for %s", r.status_code, url[:96])
            return None
        return r.text

    async def _base_resolved(self, client: httpx.AsyncClient) -> str:
        return await _resolve_effective_base(client)

    async def chart_tracks_slice(
        self,
        client: httpx.AsyncClient,
        offset: int,
        limit: int,
    ) -> tuple[list[ExternalTrack], bool]:
        base = await self._base_resolved(client)
        path = (settings.hitmotop_charts_path or "/2026").strip()
        if not path.startswith("/"):
            path = "/" + path
        url = f"{base}{path}"
        html = await self._get_html(client, url, base, timeout=28.0)
        if not html:
            return [], False
        pairs = _all_pairs(html, base)
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
    ) -> list[ExternalTrack]:
        q = query.strip()
        if not q:
            return []

        base = await self._base_resolved(client)
        page_step = max(1, settings.hitmotop_page_size)
        pairs: list[tuple[str, str, str, str]] = []
        from_pagination = False

        if settings.hitmotop_search_start_pagination:
            page_start = (max(0, offset) // page_step) * page_step
            url = f"{base}/search/start/{page_start}"
            html = await self._get_html(client, url, base, params={"q": q}, timeout=22.0)
            if html:
                pairs = _all_pairs(html, base)
                from_pagination = bool(pairs)

        if not pairs:
            html = await self._get_html(client, f"{base}/search", base, params={"q": q}, timeout=22.0)
            if html:
                pairs = _all_pairs(html, base)
            from_pagination = False

        if not pairs:
            return []

        if from_pagination and settings.hitmotop_search_start_pagination:
            page_start = (max(0, offset) // page_step) * page_step
            inner = max(0, offset - page_start)
            slice_pairs = pairs[inner : inner + min(limit, 80)]
            return _tracks_from_pairs(slice_pairs, base, q, offset=0, limit=limit)

        return _tracks_from_pairs(pairs, base, q, offset=offset, limit=limit)
