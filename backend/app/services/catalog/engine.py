import asyncio
import logging

import httpx

from app.config import settings
from app.services.catalog.bandcamp_source import BandcampCatalogSource
from app.services.catalog.hitmotop_source import HitmotopCatalogSource
from app.services.catalog.jamendo_source import JamendoCatalogSource
from app.services.catalog.lastfm_source import LastFmCatalogSource
from app.services.catalog.mock_source import MockCatalogSource
from app.services.catalog.protocol import CatalogSource
from app.services.catalog.relevance import rank_by_relevance
from app.services.catalog.rotation import diversify_search_results
from app.services.catalog.search_pipeline import (
    deep_query_variants,
    merge_dedupe_cross_source,
    normalize_track_metadata,
    sanitize_track,
)
from app.services.catalog.soundcloud_source import SoundCloudCatalogSource
from app.services.catalog.youtube_music_source import YoutubeMusicCatalogSource
from app.services.catalog.zaycev_source import ZaycevCatalogSource
from app.services.external_track import ExternalTrack

logger = logging.getLogger(__name__)

# Register additional `CatalogSource` implementations here (e.g. another licensed API).
SOURCE_REGISTRY: dict[str, CatalogSource] = {
    "zaycev": ZaycevCatalogSource(),
    "hitmotop": HitmotopCatalogSource(),
    "jamendo": JamendoCatalogSource(),
    "lastfm": LastFmCatalogSource(),
    "bandcamp": BandcampCatalogSource(),
    "youtube_music": YoutubeMusicCatalogSource(),
    "soundcloud": SoundCloudCatalogSource(),
    "mock": MockCatalogSource(),
}


def _provider_chain() -> list[str]:
    raw = (settings.catalog_provider_chain or "").strip()
    if not raw:
        return ["zaycev", "hitmotop", "jamendo", "soundcloud", "lastfm", "bandcamp", "youtube_music", "mock"]
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    return parts or ["zaycev", "hitmotop", "jamendo", "soundcloud", "lastfm", "bandcamp", "youtube_music", "mock"]


def _dedupe_best_score(
    ranked_batches: list[list[tuple[float, ExternalTrack]]],
) -> list[tuple[float, ExternalTrack]]:
    best: dict[tuple[str, str], tuple[float, ExternalTrack]] = {}
    for batch in ranked_batches:
        for score, track in batch:
            key = (track.source, track.external_id)
            if key not in best or score > best[key][0]:
                best[key] = (score, track)
    merged = list(best.values())
    merged.sort(key=lambda x: (-x[0], x[1].title.casefold()))
    return merged


async def search_catalog(
    client: httpx.AsyncClient,
    query: str,
    *,
    offset: int = 0,
    limit: int = 20,
    artist_focus: bool = False,
) -> list[ExternalTrack]:
    q = query.strip()
    chain = _provider_chain()
    min_keep = settings.search_relevance_min_keep

    if not q:
        mock = SOURCE_REGISTRY.get("mock")
        if mock is None:
            return []
        return await mock.search(client, "", offset=offset, limit=limit)

    async def _search_one(name: str) -> list[ExternalTrack]:
        src = SOURCE_REGISTRY.get(name)
        if src is None:
            logger.warning("unknown catalog provider %r — skipped", name)
            return []

        use_deep = settings.search_deep_variants and not artist_focus
        if use_deep:
            variants = deep_query_variants(q, max_variants=settings.search_deep_max_variants)
        else:
            variants = [q]

        seen_keys: set[tuple[str, str]] = set()
        merged_raw: list[ExternalTrack] = []

        for vq in variants:
            try:
                chunk = await src.search(client, vq, offset=offset, limit=limit)  # type: ignore[union-attr]
            except Exception as exc:
                logger.warning("catalog provider %s search failed (%r): %s", name, vq, exc)
                continue
            for t in chunk:
                key = (t.source, t.external_id)
                if key not in seen_keys:
                    seen_keys.add(key)
                    merged_raw.append(t)

        return merged_raw

    timeout_sec = settings.catalog_search_provider_timeout_sec

    async def _search_one_maybe_timed(name: str) -> list[ExternalTrack]:
        if timeout_sec is None or timeout_sec <= 0:
            return await _search_one(name)
        try:
            return await asyncio.wait_for(_search_one(name), timeout=timeout_sec)
        except asyncio.TimeoutError:
            logger.warning(
                "catalog provider %s search exceeded %.1fs — skipped for this request",
                name,
                timeout_sec,
            )
            return []

    per_provider = await asyncio.gather(*[_search_one_maybe_timed(n) for n in chain])

    collected_batches: list[list[tuple[float, ExternalTrack]]] = []
    for raw in per_provider:
        if raw:
            collected_batches.append(rank_by_relevance(q, raw))

    if not collected_batches:
        return []

    merged = _dedupe_best_score(collected_batches)
    merged = merge_dedupe_cross_source(merged)

    pool_cap = min(90, max(limit * 4, limit + 20))
    kept_scored = [(s, t) for s, t in merged if s >= min_keep][:pool_cap]
    if kept_scored:
        raw = [sanitize_track(normalize_track_metadata(t, query=q)) for _, t in kept_scored]
    else:
        raw = [sanitize_track(normalize_track_metadata(t, query=q)) for _, t in merged[:pool_cap]]
    rotated = diversify_search_results(raw, q, offset=offset)
    return rotated[:limit]
