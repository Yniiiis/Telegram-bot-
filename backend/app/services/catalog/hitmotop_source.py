import logging
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.services.catalog.protocol import CatalogSource
from app.services.external_track import ExternalTrack

logger = logging.getLogger(__name__)

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


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


class HitmotopCatalogSource(CatalogSource):
    """HTML search on rus.hitmotop.com (may 403 from some datacenters; works on many home IPs)."""

    async def search(
        self,
        client: httpx.AsyncClient,
        query: str,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> list[ExternalTrack]:
        base = (settings.hitmotop_base_url or "https://rus.hitmotop.com").rstrip("/")
        url = f"{base}/search"
        try:
            r = await client.get(
                url,
                params={"q": query.strip()},
                headers={"User-Agent": _BROWSER_UA, "Accept-Language": "ru-RU,ru;q=0.9"},
                timeout=30.0,
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            logger.warning("hitmotop request failed: %s", exc)
            return []

        if r.status_code >= 400:
            logger.info("hitmotop search http %s (empty catalog)", r.status_code)
            return []

        pairs = _pairs_from_html(r.text, base)
        start = max(0, offset)
        slice_pairs = pairs[start : start + min(limit, 50)]

        out: list[ExternalTrack] = []
        for sid, title, mp3 in slice_pairs:
            artist = "Unknown"
            t = title
            if " - " in title:
                t, _, rest = title.partition(" - ")
                artist = rest.strip() or artist
            elif " – " in title:
                t, _, rest = title.partition(" – ")
                artist = rest.strip() or artist
            out.append(
                ExternalTrack(
                    source="hitmotop",
                    external_id=sid,
                    title=t.strip() or "Unknown",
                    artist=artist,
                    duration_sec=None,
                    audio_url=mp3,
                    cover_url=None,
                    license_url=f"{base}/copyright",
                    license_short="hitmotop",
                )
            )

        return out
