"""
Fast Hitmotop HTML → (external_id, title, mp3_url, artist) pairs.

Primary path: lxml + XPath (single tree walk, no BeautifulSoup for Jade layout).
Optional skip_valid/take_valid: stop after enough valid tracks (search hot path).
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


def _pair_from_jade_div(div, base: str) -> tuple[str, str, str, str] | None:
    dl = div.xpath(_DL_XPATH)
    if not dl:
        return None
    href = (dl[0].get("href") or "").strip()
    if not href or ".mp3" not in href.lower():
        return None
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

    return (sid, title, mp3, artist or "Unknown")


def _pairs_jade_lxml(
    html_text: str,
    base: str,
    *,
    skip_valid: int = 0,
    take_valid: int | None = None,
) -> list[tuple[str, str, str, str]]:
    out: list[tuple[str, str, str, str]] = []
    try:
        doc = lhtml.fromstring(html_text.encode("utf-8"))
    except Exception as exc:
        logger.debug("lxml parse failed, fallback to bs4: %s", exc)
        return []

    skip = max(0, skip_valid)
    for div in doc.xpath(_JADE_TRACK_XPATH):
        p = _pair_from_jade_div(div, base)
        if p is None:
            continue
        if skip > 0:
            skip -= 1
            continue
        out.append(p)
        if take_valid is not None and len(out) >= take_valid:
            break
    return out


def _pairs_jade_bs4(
    soup: BeautifulSoup,
    base: str,
    *,
    skip_valid: int = 0,
    take_valid: int | None = None,
) -> list[tuple[str, str, str, str]]:
    out: list[tuple[str, str, str, str]] = []
    skip = max(0, skip_valid)
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

        if skip > 0:
            skip -= 1
            continue
        out.append((sid, title, mp3, artist or "Unknown"))
        if take_valid is not None and len(out) >= take_valid:
            break
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


def extract_track_pairs(
    html: str,
    base: str,
    *,
    skip_valid: int = 0,
    take_valid: int | None = None,
) -> list[tuple[str, str, str, str]]:
    """
    Parse Hitmotop listing/search HTML into track tuples.

    skip_valid: skip this many valid (downloadable) tracks.
    take_valid: stop after this many valid tracks (None = all). Used on search to avoid scanning the whole page.
    """
    if settings.hitmotop_use_jade_selectors:
        jade = _pairs_jade_lxml(html, base, skip_valid=skip_valid, take_valid=take_valid)
        if jade:
            return jade
        soup = BeautifulSoup(html, "lxml")
        jade_bs4 = _pairs_jade_bs4(soup, base, skip_valid=skip_valid, take_valid=take_valid)
        if jade_bs4:
            return jade_bs4
    soup = BeautifulSoup(html, "lxml")
    legacy = _pairs_legacy_soup(soup, base)
    if skip_valid or take_valid is not None:
        start = max(0, skip_valid)
        end = start + take_valid if take_valid is not None else len(legacy)
        return legacy[start:end]
    return legacy
