"""Build a pool of catalog tracks similar to a seed (artist / title), for radio-style queue."""

from __future__ import annotations

import logging

import httpx

from app.models.track import Track
from app.services.catalog import search_catalog
from app.services.discovery import dedupe_external
from app.services.external_track import ExternalTrack

logger = logging.getLogger(__name__)

_BAD_ARTISTS = frozenset(
    {
        "",
        "unknown",
        "неизвестен",
        "неизвестный исполнитель",
        "various artists",
        "various",
    }
)


def _title_seed_words(title: str, max_words: int = 4) -> str:
    t = (title or "").strip()
    if not t:
        return ""
    cut = t.split("(")[0].split("[")[0]
    cf = cut.casefold()
    for sep in (" feat.", " feat ", " ft.", " ft ", " featuring "):
        s = sep.casefold()
        if s in cf:
            idx = cf.index(s)
            cut = cut[:idx]
            break
    parts = cut.replace("–", " ").replace("—", "-").split()
    words = [w for w in parts if len(w) > 1][:max_words]
    return " ".join(words)


async def collect_similar_catalog_tracks(
    client: httpx.AsyncClient,
    seed: Track,
    *,
    pool: int = 40,
) -> list[ExternalTrack]:
    art = (seed.artist or "").strip()
    ttl = (seed.title or "").strip()
    skip_key = (seed.source, seed.external_id)

    queries: list[str] = []
    art_key = art.casefold()
    if art and art_key not in _BAD_ARTISTS:
        queries.append(art)
        hint = _title_seed_words(ttl)
        if hint and len(hint) > 2:
            queries.append(f"{art} {hint}")
    elif ttl:
        queries.append(_title_seed_words(ttl) or ttl)

    if not queries:
        return []

    per = max(18, min(28, pool // max(1, len(queries)) + 8))
    merged: list[ExternalTrack] = []
    for q in queries[:3]:
        try:
            merged.extend(await search_catalog(client, q, offset=0, limit=per))
        except Exception as exc:
            logger.warning("similar search failed %r: %s", q, exc)

    merged = dedupe_external(merged)
    merged = [t for t in merged if (t.source, t.external_id) != skip_key]
    return merged[:pool]
