"""Post-rank catalog hits so typos (e.g. rammstain → Rammstein) beat unrelated first-provider noise."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from app.services.external_track import ExternalTrack


def _fold(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.casefold()
    s = re.sub(r"[^\w\s\u0400-\u04FF]", " ", s, flags=re.UNICODE)
    return " ".join(s.split())


def _token_sort_ratio(a: str, b: str) -> float:
    """Fuzzy: order-insensitive token bag (good for "rammstein du hast" vs "du hast rammstein")."""
    ta = sorted(_fold(a).split())
    tb = sorted(_fold(b).split())
    if not ta or not tb:
        return 0.0
    return SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()


def _partial_best_ratio(short_q: str, blob: str) -> float:
    """Best contiguous match ratio for a sliding window (short query vs long blob)."""
    qf = _fold(short_q)
    bf = _fold(blob)
    if not qf or not bf:
        return 0.0
    if len(qf) >= len(bf):
        return SequenceMatcher(None, qf, bf).ratio()
    best = 0.0
    n, m = len(qf), len(bf)
    if m < n:
        return SequenceMatcher(None, qf[:m], bf).ratio()
    step = max(1, (m - n) // 16)
    for i in range(0, m - n + 1, step):
        chunk = bf[i : i + n]
        best = max(best, SequenceMatcher(None, qf, chunk).ratio())
    return best


def relevance_score(query: str, title: str, artist: str) -> float:
    """
    0..1 heuristic: token overlap + fuzzy match against artist/title combined.
    Handles single-word typos via SequenceMatcher on artist/title tokens.
    """
    q = _fold(query)
    if not q:
        return 0.0
    artist_f = _fold(artist)
    title_f = _fold(title)
    blob = f"{artist_f} {title_f}".strip()
    if not blob:
        return 0.0

    if q in blob:
        return 1.0

    tokens = [t for t in q.split() if len(t) >= 2]
    if not tokens:
        tokens = [q]

    token_scores: list[float] = []
    for tok in tokens:
        if tok in blob:
            token_scores.append(1.0)
            continue
        best = 0.0
        for part in blob.split():
            if len(part) < 2:
                continue
            r = SequenceMatcher(None, tok, part).ratio()
            if len(tok) >= 4 and len(part) >= 4 and (part.startswith(tok[:4]) or tok.startswith(part[:4])):
                r = max(r, 0.72)
            best = max(best, r)
        token_scores.append(best)

    overlap = sum(token_scores) / len(token_scores)
    whole_blob = SequenceMatcher(None, q, blob).ratio()
    whole_artist = SequenceMatcher(None, q, artist_f).ratio() if artist_f else 0.0
    whole_title = SequenceMatcher(None, q, title_f).ratio() if title_f else 0.0
    ts_blob = _token_sort_ratio(query, blob)
    ts_artist = _token_sort_ratio(query, artist_f) if artist_f else 0.0
    ts_title = _token_sort_ratio(query, title_f) if title_f else 0.0
    partial = _partial_best_ratio(query, blob) * 0.92 if len(q) >= 4 else 0.0
    return max(
        overlap,
        whole_blob * 0.95,
        whole_artist,
        whole_title,
        ts_blob,
        ts_artist,
        ts_title,
        partial,
    )


def _source_playback_tie_index(source: str) -> int:
    """Lower index = preferred when relevance ties (restore priority list when re-adding merge)."""
    _ = source
    return 999


def rank_by_relevance(query: str, tracks: list[ExternalTrack]) -> list[tuple[float, ExternalTrack]]:
    scored = [(relevance_score(query, t.title, t.artist), t) for t in tracks]
    scored.sort(
        key=lambda x: (-x[0], _source_playback_tie_index(x[1].source), x[1].title.casefold()),
    )
    return scored
