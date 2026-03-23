"""
Bandcamp: public fuzzy search API + track page parse for progressive MP3 URL.

Unofficial; may break if Bandcamp changes markup.
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.services.catalog.protocol import CatalogSource
from app.services.external_track import ExternalTrack

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
_SEARCH_URL = "https://bandcamp.com/api/fuzzysearch/1/autocompletesearch"
_MP3_RE = re.compile(r"https://[^\"'\s]+\.bcbits\.com/[^\"'\s]+\.mp3(?:\?[^\"'\s]*)?")


def _artist_name(item: dict) -> str:
    arts = item.get("artists") or item.get("band")
    if isinstance(arts, list) and arts:
        a0 = arts[0]
        if isinstance(a0, dict):
            return str(a0.get("name") or "").strip() or "Unknown"
    if isinstance(arts, dict):
        return str(arts.get("name") or "").strip() or "Unknown"
    return str(item.get("artist") or "Unknown").strip() or "Unknown"


async def _extract_mp3(client: httpx.AsyncClient, page_url: str) -> str | None:
    try:
        r = await client.get(
            page_url,
            headers={"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"},
            timeout=20.0,
            follow_redirects=True,
        )
        if r.status_code >= 400:
            return None
        html = r.text
        m = _MP3_RE.search(html)
        if m:
            return m.group(0).split('"')[0].split("'")[0]

        soup = BeautifulSoup(html, "html.parser")
        script = soup.find("script", attrs={"type": "application/ld+json"})
        if script and script.string:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    enc = data.get("encoding") or data.get("associatedMedia")
                    if isinstance(enc, list) and enc:
                        u = enc[0].get("contentUrl") if isinstance(enc[0], dict) else None
                        if u and ".mp3" in str(u):
                            return str(u)
            except json.JSONDecodeError:
                pass
    except Exception as exc:
        logger.debug("bandcamp page parse failed %s: %s", page_url[:80], exc)
    return None


class BandcampCatalogSource(CatalogSource):
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

        try:
            r = await client.post(
                _SEARCH_URL,
                json={"search_text": q},
                headers={
                    "User-Agent": _UA,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=22.0,
            )
        except httpx.HTTPError as exc:
            logger.warning("bandcamp fuzzy search failed: %s", exc)
            return []

        if r.status_code >= 400:
            return []

        try:
            payload = r.json()
        except Exception:
            return []

        auto = (payload.get("auto") or {}).get("results") or []
        track_items: list[dict] = []
        for item in auto:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "") != "t":
                continue
            track_items.append(item)

        start = max(0, offset)
        slice_items = track_items[start : start + min(limit, 25)]
        out: list[ExternalTrack] = []

        for item in slice_items:
            url = str(item.get("url") or "").strip()
            title = str(item.get("name") or "Unknown").strip() or "Unknown"
            artist = _artist_name(item)
            if not url or "bandcamp.com" not in url:
                continue
            mp3 = await _extract_mp3(client, url)
            if not mp3:
                continue
            path = urlparse(url).path.strip("/").replace("/", "_")
            ext_id = path[-200:] or mp3.split("/")[-1][:80]
            out.append(
                ExternalTrack(
                    source="bandcamp",
                    external_id=ext_id[:256],
                    title=title,
                    artist=artist,
                    duration_sec=None,
                    audio_url=mp3,
                    cover_url=item.get("img") if isinstance(item.get("img"), str) else None,
                    license_url=str(url).split("?")[0],
                    license_short="bandcamp",
                )
            )
            if len(out) >= limit:
                break

        return out
