"""
Fast Hitmotop HTML → (external_id, title, mp3_url, artist) pairs.

Primary path: lxml + XPath (single tree walk, no BeautifulSoup for Jade layout).
Legacy path: BeautifulSoup with lxml parser (still faster than html.parser).
"""

from __future__ import annotations

import logging
import re
import zlib
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from lxml import html as lhtml

from app.config import settings

logger = logging.getLogger(__name__)

_JADE_TRACK_XPATH = (
    "//div[contains(concat(' ', normalize-space(@class), ' '), ' track__info ')]"
)
_DL_XPATH = (
    ".//a[contains(concat(' ', normalize-space(@class), ' '), ' track__download-btn ')]"
)
_ARTIST_XPATH = (
    ".//div[contains(concat(' ', normalize-space(@class), ' '), ' track__desc ')]"
)
_TITLE_XPATH = (
    ".//div[contains(concat(' ', normalize-space(@class), ' '), ' track__title ')]"
)
_SONG_A_XPATH = ".//a[contains(@href, '/song/')]"

_SONG_ID_RE = re.compile(r"/song/(\d+)", re.IGNORECASE)
_MP3_ID_RE = re.compile(r"/(\d+)\.mp3", re.IGNORECASE)


def _id_from_mp3(mp3: str) -> str:
    m = _MP3_ID_RE.search(mp3)
    if m:
        return m.group(1)
    return str(zlib.adler32(mp3.encode("utf-8", errors="ignore")) & 0x7FFFFFFF)


def _text(el) -> str:
    if el is None:
        return ""
    return " ".join("".join(el.itertext()).split())


def _pairs_jade_lxml(html_text: str, base: str) -> list[tuple[str, str, str, str]]:
    out: list[tuple[str, str, str, str]] = []
    try:
        doc = lhtml.fromstring(html_text)
    except Exception as exc:
        logger.debug("lxml parse failed, fallback to bs4: %s", exc)
        return []

    for div in doc.xpath(_JADE_TRACK_XPATH):
        dl = div.xpath(_DL_XPATH)
        if not dl:
            continue
        href = (dl[0].get("href") or "").strip()
        if not href or ".mp3" not in href.lower():
            continue
        mp3 = urljoin(base, href)

        artist_el = div.xpath(_ARTIST_XPATH)
        title_el = div.xpath(_TITLE_XPATH)
        artist = _text(artist_el[0]) if artist_el else "Unknown"
        title = _text(title_el[0]) if title_el else "Unknown"

        sid: str | None = None
        for la in div.xpath(_SONG_A_XPATH):
            m = _SONG_ID_RE.search(la.get("href") or "")
            if m:
                sid = m.group(1)
                break
        if not sid:
            sid = _id_from_mp3(mp3)

        out.append((sid, title, mp3, artist or "Unknown"))
    return out


def _pairs_jade_bs4(soup: BeautifulSoup, base: str) -> list[tuple[str, str, str, str]]:
    out: list[tuple[str, str, str, str]] = []
    for div in soup.select("div.track__info"):
        dl = div.select_one("a.track__download-btn")
        if not dl:
            continue
        href = (dl.get("href") or "").strip()
        if not href or ".mp3" not in href.lower():
            continue
        mp3 = urljoin(base, href)
        artist_el = div.select_one("div.track__desc")
        title_el = div.select_one("div.track__title")
        artist = " ".join(artist_el.get_text().split()) if artist_el else "Unknown"
        title = " ".join(title_el.get_text().split()) if title_el else "Unknown"

        sid: str | None = None
        for la in div.select('a[href*="/song/"]'):
            m = _SONG_ID_RE.search(la.get("href") or "")
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


def extract_track_pairs(html: str, base: str) -> list[tuple[str, str, str, str]]:
    """Parse Hitmotop listing/search HTML into track tuples."""
    if settings.hitmotop_use_jade_selectors:
        jade = _pairs_jade_lxml(html, base)
        if jade:
            return jade
        soup = BeautifulSoup(html, "lxml")
        jade_bs4 = _pairs_jade_bs4(soup, base)
        if jade_bs4:
            return jade_bs4
    soup = BeautifulSoup(html, "lxml")
    return _pairs_legacy_soup(soup, base)
