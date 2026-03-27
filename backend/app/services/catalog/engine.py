import asyncio
import logging

import httpx

from app.config import settings
from app.services.catalog.hitmotop_source import HitmotopCatalogSource
from app.services.catalog.protocol import CatalogSource
from app.services.external_track import ExternalTrack

logger = logging.getLogger(__name__)

_hitmotop = HitmotopCatalogSource()

SOURCE_REGISTRY: dict[str, CatalogSource] = {
    "hitmotop": _hitmotop,
}

_DEFAULT_CHAIN: list[str] = ["hitmotop"]


def _provider_chain() -> list[str]:
    raw = (settings.catalog_provider_chain or "").strip()
    if not raw:
        return list(_DEFAULT_CHAIN)
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    return parts or list(_DEFAULT_CHAIN)


def get_catalog_provider_chain() -> list[str]:
    return _provider_chain()


async def search_catalog(
    client: httpx.AsyncClient,
    query: str,
    *,
    offset: int = 0,
    limit: int = 20,
    artist_focus: bool = False,
) -> list[ExternalTrack]:
    _ = artist_focus
    if not SOURCE_REGISTRY:
        return []

    chain = _provider_chain()
    if not chain:
        return []

    async def _one(name: str) -> list[ExternalTrack]:
        src = SOURCE_REGISTRY.get(name)
        if src is None:
            logger.warning("unknown catalog provider %r — skipped", name)
            return []
        try:
            return await src.search(client, query.strip(), offset=offset, limit=limit)
        except Exception as exc:
            logger.warning("catalog provider %s search failed: %s", name, exc)
            return []

    chunks = await asyncio.gather(*[_one(n) for n in chain])
    out: list[ExternalTrack] = []
    seen: set[tuple[str, str]] = set()
    for chunk in chunks:
        for t in chunk:
            k = (t.source, t.external_id)
            if k not in seen:
                seen.add(k)
                out.append(t)
    return out[:limit]
