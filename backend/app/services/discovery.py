"""Home discovery: contexts, new-release refresh (Hitmotop catalog only)."""

from __future__ import annotations

import logging
from collections.abc import Iterable

import httpx
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.featured_new_release import FeaturedNewRelease
from app.services.catalog import search_catalog
from app.services.catalog.engine import SOURCE_REGISTRY
from app.services.catalog.hitmotop_source import HitmotopCatalogSource
from app.services.catalog.search_pipeline import sanitize_track
from app.services.external_track import ExternalTrack
from app.services.track_upsert import upsert_external_tracks

logger = logging.getLogger(__name__)

CONTEXT_QUERY_BATCHES: dict[str, list[str]] = {
    "work": [
        "lofi hip hop beats instrumental focus no lyrics",
        "ambient electronic deep work concentration",
        "minimal calm office background music",
    ],
    "study": [
        "classical piano study concentration quiet",
        "ambient soft instrumental reading no vocals",
        "baroque strings calm focus",
    ],
    "sport": [
        "high energy edm gym workout motivation",
        "hip hop gym training aggressive beats",
        "techno fitness cardio power",
    ],
    "run": [
        "running music house 128 bpm energetic",
        "upbeat electronic jogging steady tempo",
        "dance pop cardio fast pace workout",
    ],
    "relax": [
        "acoustic guitar chill relax evening soft",
        "ambient meditation calm peaceful",
        "lofi relax slow vibes sunset",
    ],
    "party": [
        "dance pop party hits club night",
        "latin reggaeton party upbeat",
        "house edm festival dance floor",
    ],
}

_CONTEXT_LABELS: dict[str, str] = {
    "work": "Работа / фокус",
    "study": "Учёба",
    "sport": "Спорт / зал",
    "run": "Бег",
    "relax": "Отдых",
    "party": "Вечеринка",
}

_CONTEXT_ORDER = ("work", "study", "sport", "run", "relax", "party")

DAILY_CONTEXTS: list[dict[str, str]] = [
    {
        "id": cid,
        "label": _CONTEXT_LABELS[cid],
        "query": CONTEXT_QUERY_BATCHES[cid][0],
    }
    for cid in _CONTEXT_ORDER
]

def catalog_source_ids() -> list[str]:
    return sorted(SOURCE_REGISTRY.keys())


def weekday_mood_query() -> str:
    p = (settings.hitmotop_charts_path or "/2026").strip() or "/2026"
    return f"Hitmotop · {p}"


def parse_sources_filter(raw: str | None) -> set[str] | None:
    if not raw or not raw.strip():
        return None
    allowed = set(SOURCE_REGISTRY.keys())
    got = {p.strip().lower() for p in raw.split(",") if p.strip()}
    got &= allowed
    return got or None


def filter_external_tracks(
    tracks: list[ExternalTrack],
    *,
    sources: set[str] | None,
    min_duration_sec: int | None,
    max_duration_sec: int | None,
) -> list[ExternalTrack]:
    out: list[ExternalTrack] = []
    for t in tracks:
        if sources and t.source not in sources:
            continue
        d = t.duration_sec
        if min_duration_sec is not None:
            if d is None or d < min_duration_sec:
                continue
        if max_duration_sec is not None:
            if d is None or d > max_duration_sec:
                continue
        out.append(t)
    return out


def dedupe_external(tracks: Iterable[ExternalTrack]) -> list[ExternalTrack]:
    seen: set[tuple[str, str]] = set()
    out: list[ExternalTrack] = []
    for t in tracks:
        k = (t.source, t.external_id)
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    return out


async def collect_discovery_picks(
    client: httpx.AsyncClient,
    *,
    mode: str,
    context: str | None,
    limit: int,
) -> tuple[list[ExternalTrack], str, str | None]:
    m = (mode or "weekday").strip().lower()

    async def _from_seeds(
        seeds: list[str],
        display_name: str,
        ctx_id: str | None,
    ) -> tuple[list[ExternalTrack], str, str | None]:
        n_seeds = max(1, len(seeds))
        per_seed = max(12, min(30, (limit * 3) // n_seeds + 10))
        merged: list[ExternalTrack] = []
        for sq in seeds:
            try:
                chunk = await search_catalog(client, sq, offset=0, limit=per_seed)
                merged.extend(chunk)
            except Exception as exc:
                logger.warning("discovery picks seed failed %r: %s", sq, exc)
        merged = dedupe_external(merged)
        out = [sanitize_track(t) for t in merged][:limit]
        return out, display_name, ctx_id

    if m == "context":
        if not context or not context.strip():
            raise ValueError("context_required")
        cid = context.strip()
        if cid not in CONTEXT_QUERY_BATCHES:
            raise ValueError("unknown_context")
        seeds = list(CONTEXT_QUERY_BATCHES[cid])
        return await _from_seeds(seeds, _CONTEXT_LABELS[cid], cid)

    src = SOURCE_REGISTRY.get("hitmotop")
    if isinstance(src, HitmotopCatalogSource):
        try:
            rows = await src.fetch_chart_tracks(client, offset=0, limit=limit)
        except Exception as exc:
            logger.warning("hitmotop charts failed: %s", exc)
            rows = []
        return rows, weekday_mood_query(), None
    return [], weekday_mood_query(), None


async def collect_new_release_candidates(client: httpx.AsyncClient) -> list[ExternalTrack]:
    src = SOURCE_REGISTRY.get("hitmotop")
    if isinstance(src, HitmotopCatalogSource):
        try:
            rows = await src.fetch_chart_tracks(
                client,
                offset=0,
                limit=settings.new_releases_max_collect,
            )
            return dedupe_external(rows)
        except Exception as exc:
            logger.warning("hitmotop new-release chart failed: %s", exc)
    return []


async def refresh_featured_new_releases(db: AsyncSession, client: httpx.AsyncClient) -> int:
    candidates = await collect_new_release_candidates(client)
    if not candidates:
        await db.execute(delete(FeaturedNewRelease))
        await db.commit()
        return 0

    tracks = await upsert_external_tracks(db, candidates[: settings.new_releases_store_limit])
    await db.execute(delete(FeaturedNewRelease))
    for i, tr in enumerate(tracks):
        db.add(FeaturedNewRelease(track_id=tr.id, position=i))
    await db.commit()
    return len(tracks)
