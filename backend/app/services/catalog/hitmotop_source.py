import logging
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


def _hitmotop_headers(base: str) -> dict[str, str]:
    b = base.rstrip("/")
    return {
        "User-Agent": _BROWSER_UA,
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Referer": f"{b}/",
    }


def _pairs_from_html(html: str, base: str) -> list[tuple[str, str, str]]:
    """Return (external_id, title, absolute_mp3_url) in document order."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[tuple[str, str, str]] = []
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
            out.append((pending_id, title, mp3))
            pending_id = None
            pending_title = None

    return out


def _tracks_from_pairs(
    pairs: list[tuple[str, str, str]],
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
    for sid, title, mp3 in slice_pairs:
        combined = " ".join((title or "Unknown").split()).strip() or "Unknown"
        raw = ExternalTrack(
            source="hitmotop",
            external_id=sid,
            title=combined,
            artist="Unknown",
            duration_sec=None,
            audio_url=mp3,
            cover_url=None,
            license_url=f"{base.rstrip('/')}/copyright",
            license_short="hitmotop",
        )
        out.append(sanitize_track(normalize_track_metadata(raw, query=query)))
    return out


class HitmotopCatalogSource(CatalogSource):
    """rus.hitmotop.com: HTML search + chart/list pages (e.g. /2026) with direct MP3 links."""

    async def _get_html(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, str] | None = None,
        timeout: float = 22.0,
    ) -> str | None:
        try:
            r = await client.get(
                url,
                params=params,
                headers=_hitmotop_headers(self._base()),
                timeout=timeout,
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            logger.warning("hitmotop request failed %s: %s", url[:80], exc)
            return None
        if r.status_code >= 400:
            logger.info("hitmotop http %s for %s", r.status_code, url[:80])
            return None
        return r.text

    def _base(self) -> str:
        return (settings.hitmotop_base_url or "https://rus.hitmotop.com").rstrip("/")

    def _charts_url(self) -> str:
        path = (settings.hitmotop_charts_path or "/2026").strip()
        if not path.startswith("/"):
            path = "/" + path
        return f"{self._base()}{path}"

    async def chart_tracks_slice(
        self,
        client: httpx.AsyncClient,
        offset: int,
        limit: int,
    ) -> tuple[list[ExternalTrack], bool]:
        """Chart/list page slice + whether more rows exist on the same HTML page."""
        html = await self._get_html(client, self._charts_url(), timeout=28.0)
        if not html:
            return [], False
        base = self._base()
        pairs = _pairs_from_html(html, base)
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
        """Tracks from the configured charts/list path (default /2026)."""
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
        base = self._base()
        url = f"{base}/search"
        html = await self._get_html(client, url, params={"q": query.strip()})
        if not html:
            return []
        pairs = _pairs_from_html(html, base)
        return _tracks_from_pairs(pairs, base, query.strip(), offset=offset, limit=limit)
