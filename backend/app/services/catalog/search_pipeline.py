"""
Search pipeline: query normalization, deep variants, cross-source dedupe, merge + sort, metadata sanitize.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import replace

from app.config import settings
from app.services.external_track import ExternalTrack

# Brackets / feat. stripping for dedupe keys only (not for display).
_FEATURE_PAT = re.compile(
    r"\s*[\(\[]\s*(feat\.?|ft\.?|featuring|при уч\.|prod\.?)\s*[^\)\]]*[\)\]]",
    re.IGNORECASE,
)
_EXTRA_PARENS = re.compile(r"\([^)]*\)|\[[^\]]*\]")


def fold_text(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.casefold()
    s = re.sub(r"[^\w\s\u0400-\u04FF]", " ", s, flags=re.UNICODE)
    return " ".join(s.split())


def strip_markers_for_key(title: str) -> str:
    t = _FEATURE_PAT.sub(" ", title)
    t = _EXTRA_PARENS.sub(" ", t)
    return " ".join(t.split())


def track_fingerprint(track: ExternalTrack) -> str:
    """Cross-provider dedupe key (same recording from different catalogs)."""
    title_k = strip_markers_for_key(track.title)
    return f"{fold_text(track.artist)}|{fold_text(title_k)}"


_UNKNOWN_ARTIST_FOLD = frozenset(
    {
        "",
        "unknown",
        "неизвестно",
        "неизвестный",
        "неизвестный исполнитель",
        "various artists",
        "various",
        "n a",
        "na",
    }
)


def _is_unknown_artist(artist: str) -> bool:
    a = fold_text(artist or "")
    return not a or a in _UNKNOWN_ARTIST_FOLD


def split_combined_title(title: str) -> tuple[str, str] | None:
    """If title looks like «A – B», return both segments (order not decided)."""
    if not title:
        return None
    for sep in (" – ", " — ", " - ", " | "):
        if sep in title:
            left, right = title.split(sep, 1)
            left, right = left.strip(), right.strip()
            if left and right:
                return (left, right)
    return None


def split_space_using_query(title: str, query: str) -> tuple[str, str] | None:
    """
    Zaycev / др.: в поле названия часто «Километры Кишлак» без дефиса, а артист Unknown.
    Если запрос — «кишлак», отрезаем совпадающий суффикс/префикс как артиста.
    """
    fq = fold_text(query or "")
    if len(fq) < 2:
        return None
    words = title.split()
    if len(words) < 2:
        return None

    long_query = len(fq.split()) > 5 or len(fq) > 40

    def q_matches(blob: str) -> bool:
        b = fold_text(blob)
        if not b:
            return False
        if b == fq:
            return True
        if long_query:
            return False
        if len(fq) < 4:
            return False
        if fq in b:
            return True
        if len(b) >= 4 and b in fq:
            return True
        return False

    # Суффикс-артист: «… Название Артист»
    for n in range(min(3, len(words) - 1), 0, -1):
        left, right = " ".join(words[:-n]), " ".join(words[-n:])
        if left and right and q_matches(right) and not q_matches(left):
            return left, right

    # Префикс-артист: «Арист …»
    for n in range(1, min(4, len(words))):
        left, right = " ".join(words[:n]), " ".join(words[n:])
        if right and q_matches(left) and not q_matches(right):
            return right, left

    return None


def strip_redundant_artist_suffix(track: ExternalTrack) -> ExternalTrack:
    """Убрать повтор артиста в конце строки названия («Трек Кишлак» при artist=Кишлак)."""
    if _is_unknown_artist(track.artist):
        return track
    t = " ".join((track.title or "").split())
    a = " ".join((track.artist or "").split())
    if not t or not a:
        return track
    ft, fa = fold_text(t), fold_text(a)
    if ft == fa:
        return track
    tail = " " + a
    if t.casefold().endswith(tail.casefold()) and len(t) > len(a) + 1:
        new_title = t[: -len(tail)].strip()
        if new_title:
            return replace(track, title=new_title)
    for sep in (" - ", " – ", " — "):
        if sep not in t:
            continue
        left, right = t.split(sep, 1)
        if fold_text(right.strip()) == fa:
            nl = left.strip()
            if nl:
                return replace(track, title=nl)
    return track


def normalize_track_metadata(track: ExternalTrack, *, query: str = "") -> ExternalTrack:
    """
    Many catalogs put «Artist - Title» only in `title` and leave artist as Unknown.
    Split using the search query and simple heuristics so UI can show title on top, artist below.
    """
    title = (track.title or "").strip() or "Unknown"
    artist = (track.artist or "").strip() or "Unknown"
    if not _is_unknown_artist(artist):
        return strip_redundant_artist_suffix(track)

    pair = split_combined_title(title)
    if pair:
        left, right = pair
        fq = fold_text(query)
        fl, fr = fold_text(left), fold_text(right)

        if fq and len(fq) >= 2:
            l_hit = fq in fl or fl in fq
            r_hit = fq in fr or fr in fq
            if l_hit and not r_hit:
                return strip_redundant_artist_suffix(replace(track, artist=left, title=right))
            if r_hit and not l_hit:
                return strip_redundant_artist_suffix(replace(track, artist=right, title=left))

        # Shorter first segment → often «Artist - Long track name»
        if len(left) <= 36 and len(right) > len(left) + 8:
            return strip_redundant_artist_suffix(replace(track, artist=left, title=right))
        if len(right) <= 36 and len(left) > len(right) + 8:
            return strip_redundant_artist_suffix(replace(track, artist=right, title=left))

        return strip_redundant_artist_suffix(replace(track, artist=left, title=right))

    spaced = split_space_using_query(title, query)
    if spaced:
        new_title, new_artist = spaced
        return strip_redundant_artist_suffix(replace(track, title=new_title, artist=new_artist))

    return track


def sanitize_track(track: ExternalTrack) -> ExternalTrack:
    """Light display normalization: trim and collapse whitespace."""
    title = " ".join((track.title or "").split())
    artist = " ".join((track.artist or "").split())
    if title == track.title and artist == track.artist:
        return track
    return replace(track, title=title or "Unknown", artist=artist or "Unknown")


def deep_query_variants(query: str, *, max_variants: int) -> list[str]:
    """
    Extra query strings for provider APIs (artist/title permutations, stripped brackets).
    """
    q = query.strip()
    if not q:
        return []

    seen: dict[str, None] = {}
    out: list[str] = []

    def add(s: str) -> None:
        s = " ".join(s.split())
        if len(s) < 1:
            return
        k = fold_text(s)
        if k not in seen:
            seen[k] = None
            out.append(s)

    add(q)
    no_paren = _EXTRA_PARENS.sub(" ", q)
    add(no_paren)

    folded = fold_text(q)
    parts = folded.split()
    if len(parts) >= 2:
        add(" ".join(parts))
        # "title artist" guess (last chunk as artist prefix)
        add(f"{parts[-1]} {' '.join(parts[:-1])}")
        if len(parts) >= 3:
            add(f"{parts[-2]} {parts[-1]} {' '.join(parts[:-2])}")

    return out[: max(1, max_variants)]


def _source_priority_map() -> dict[str, int]:
    raw = (settings.search_source_priority or "").strip()
    if not raw:
        order = ["jamendo", "soundcloud", "youtube_music", "zaycev", "hitmotop", "mock"]
    else:
        order = [p.strip().lower() for p in raw.split(",") if p.strip()]
    return {name: i for i, name in enumerate(order)}


def merge_dedupe_cross_source(
    scored: list[tuple[float, ExternalTrack]],
) -> list[tuple[float, ExternalTrack]]:
    """
    After per-(source,id) merge: collapse same fingerprint; keep best score,
    tie-break by source priority (lower index = better).
    """
    prio = _source_priority_map()

    best: dict[str, tuple[float, ExternalTrack]] = {}
    for score, track in scored:
        fp = track_fingerprint(track)
        if fp not in best:
            best[fp] = (score, track)
            continue
        ps, pt = best[fp]
        if score > ps:
            best[fp] = (score, track)
        elif score == ps:
            p_new = prio.get(track.source, 99)
            p_old = prio.get(pt.source, 99)
            if p_new < p_old:
                best[fp] = (score, track)

    merged = list(best.values())
    merged.sort(key=lambda x: (-x[0], x[1].title.casefold()))
    return merged
