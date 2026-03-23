"""Map metadata (Last.fm, etc.) to playable rows from Zaycev / Hitmotop."""

from __future__ import annotations

import asyncio
import logging

import httpx
from dataclasses import replace

from app.services.catalog.hitmotop_source import HitmotopCatalogSource
from app.services.catalog.relevance import relevance_score
from app.services.catalog.zaycev_source import ZaycevCatalogSource
from app.services.external_track import ExternalTrack

logger = logging.getLogger(__name__)

_Z = ZaycevCatalogSource()
_H = HitmotopCatalogSource()


async def resolve_to_zaycev_or_hitmotop(
    client: httpx.AsyncClient,
    artist: str,
    title: str,
    *,
    listeners: int | None = None,
    released_ts: int | None = None,
    min_score: float = 0.34,
) -> ExternalTrack | None:
    """Pick first catalog hit whose title/artist matches the seed (Zaycev first)."""
    q = f"{artist} {title}".strip()
    if len(q) < 2:
        return None

    try:
        zh = await _Z.search(client, q, offset=0, limit=8)
    except Exception as exc:
        logger.debug("zaycev resolve failed: %s", exc)
        zh = []

    best: ExternalTrack | None = None
    best_s = 0.0
    for t in zh:
        s = relevance_score(q, t.title, t.artist)
        if s >= min_score and s > best_s:
            best_s = s
            best = t

    if best:
        return replace(
            best,
            listeners=listeners if listeners is not None else best.listeners,
            released_ts=released_ts if released_ts is not None else best.released_ts,
        )

    try:
        hh = await _H.search(client, q, offset=0, limit=8)
    except Exception as exc:
        logger.debug("hitmotop resolve failed: %s", exc)
        hh = []

    for t in hh:
        s = relevance_score(q, t.title, t.artist)
        if s >= min_score and s > best_s:
            best_s = s
            best = t

    if not best:
        return None
    return replace(
        best,
        listeners=listeners if listeners is not None else best.listeners,
        released_ts=released_ts if released_ts is not None else best.released_ts,
    )


async def resolve_many_playable(
    client: httpx.AsyncClient,
    seeds: list[tuple[str, str, int | None, int | None]],
    *,
    concurrency: int = 5,
    limit: int = 24,
) -> list[ExternalTrack]:
    """Seeds: (artist, title, listeners|None, released_ts|None). Deduped by fingerprint."""
    from app.services.catalog.search_pipeline import track_fingerprint

    seen_fp: set[str] = set()
    out: list[ExternalTrack] = []
    chunk = max(1, concurrency)

    for i in range(0, len(seeds), chunk):
        if len(out) >= limit:
            break
        batch = seeds[i : i + chunk]
        rows = await asyncio.gather(
            *[
                resolve_to_zaycev_or_hitmotop(client, a, t, listeners=l, released_ts=r)
                for a, t, l, r in batch
            ],
            return_exceptions=True,
        )
        for r in rows:
            if len(out) >= limit:
                break
            if isinstance(r, BaseException) or r is None:
                continue
            fp = track_fingerprint(r)
            if fp in seen_fp:
                continue
            seen_fp.add(fp)
            out.append(r)
    return out[:limit]
