"""Home discovery: daily contexts, new-release feed refresh, search filter helpers."""

from __future__ import annotations

import datetime
import logging
from collections.abc import Iterable

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.featured_new_release import FeaturedNewRelease
from app.models.track import Track
from app.services.catalog import search_catalog
from app.services.catalog.engine import SOURCE_REGISTRY
from app.services.catalog.jamendo_source import JamendoCatalogSource
from app.services.external_track import ExternalTrack
from app.services.track_upsert import upsert_external_tracks

logger = logging.getLogger(__name__)

# Several catalog searches per activity so results are varied and closer to real use cases.
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

# Presets for /discovery/meta (first seed = default hint).
DAILY_CONTEXTS: list[dict[str, str]] = [
    {
        "id": cid,
        "label": _CONTEXT_LABELS[cid],
        "query": CONTEXT_QUERY_BATCHES[cid][0],
    }
    for cid in _CONTEXT_ORDER
]

_WEEKDAY_MOOD_QUERIES = [
    "monday motivation energy pop",
    "tuesday calm acoustic",
    "wednesday electronic focus",
    "thursday indie rock",
    "friday dance weekend",
    "saturday chill beats",
    "sunday jazz relax",
]

# Second search per weekday to widen the pool (same index as weekday).
_WEEKDAY_ALT_QUERIES = [
    "indie pop fresh start upbeat",
    "piano ambient soft background",
    "synth electronic productive flow",
    "alternative rock energetic",
    "disco funk friday night",
    "reggae chill saturday lazy",
    "bossa nova sunday relax",
]


def catalog_source_ids() -> list[str]:
    return sorted(SOURCE_REGISTRY.keys())


def weekday_mood_query() -> str:
    wd = datetime.date.today().weekday()
    return _WEEKDAY_MOOD_QUERIES[wd % len(_WEEKDAY_MOOD_QUERIES)]


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
    """
    Merge several `search_catalog` calls so home picks are not two duplicate mock rows.
    Re-rank by the primary seed; dedupe by cross-source fingerprint where possible.
    """
    from app.services.catalog.relevance import rank_by_relevance
    from app.services.catalog.search_pipeline import (
        normalize_track_metadata,
        sanitize_track,
        track_fingerprint,
    )

    m = (mode or "weekday").strip().lower()
    ctx_id: str | None = None
    display_name: str
    seeds: list[str]

    if m == "context":
        if not context or not context.strip():
            raise ValueError("context_required")
        cid = context.strip()
        if cid not in CONTEXT_QUERY_BATCHES:
            raise ValueError("unknown_context")
        seeds = list(CONTEXT_QUERY_BATCHES[cid])
        display_name = _CONTEXT_LABELS[cid]
        ctx_id = cid
    else:
        wd = datetime.date.today().weekday()
        i = wd % len(_WEEKDAY_MOOD_QUERIES)
        primary = _WEEKDAY_MOOD_QUERIES[i]
        alt = _WEEKDAY_ALT_QUERIES[i % len(_WEEKDAY_ALT_QUERIES)]
        seeds = [primary, alt, f"{primary} mix"]
        display_name = primary
        m = "weekday"

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
    if not merged:
        return [], display_name, ctx_id

    rank_key = seeds[0]
    ranked = rank_by_relevance(rank_key, merged)
    ranked.sort(key=lambda x: (-x[0], x[1].title.casefold()))

    out: list[ExternalTrack] = []
    seen_fp: set[str] = set()
    for _, t in ranked:
        fp = track_fingerprint(t)
        if fp in seen_fp:
            continue
        seen_fp.add(fp)
        fixed = sanitize_track(normalize_track_metadata(t, query=rank_key))
        out.append(fixed)
        if len(out) >= limit:
            break

    return out, display_name, ctx_id


async def collect_new_release_candidates(client: httpx.AsyncClient) -> list[ExternalTrack]:
    """Pull recent-style tracks from Jamendo tags + one merged catalog search."""
    merged: list[ExternalTrack] = []

    jamendo = JamendoCatalogSource()
    tags = ["pop", "electronic", "hiphop", "rock", "indie", "jazz"]
    merged.extend(await jamendo.recent_by_tags(client, tags=tags, per_tag=7))

    try:
        merged.extend(await search_catalog(client, "new single", offset=0, limit=22))
    except Exception as exc:
        logger.warning("discovery broad search failed: %s", exc)

    try:
        merged.extend(await search_catalog(client, settings.discovery_new_seed_query, offset=0, limit=18))
    except Exception as exc:
        logger.warning("discovery seed search failed: %s", exc)

    mock = SOURCE_REGISTRY.get("mock")
    if mock is not None:
        try:
            merged.extend(await mock.search(client, "", offset=0, limit=6))  # type: ignore[union-attr]
        except Exception:
            pass

    return dedupe_external(merged)[: settings.new_releases_max_collect]


async def refresh_featured_new_releases(db: AsyncSession, client: httpx.AsyncClient) -> int:
    """Replace featured_new_releases from fresh catalog pulls. Returns number of rows."""
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
