import logging

import httpx

from app.config import settings
from app.services.catalog.hitmotop_source import HitmotopCatalogSource
from app.services.catalog.jamendo_source import JamendoCatalogSource
from app.services.catalog.mock_source import MockCatalogSource
from app.services.catalog.protocol import CatalogSource
from app.services.catalog.zaycev_source import ZaycevCatalogSource
from app.services.external_track import ExternalTrack

logger = logging.getLogger(__name__)

# Register additional `CatalogSource` implementations here (e.g. another licensed API).
SOURCE_REGISTRY: dict[str, CatalogSource] = {
    "zaycev": ZaycevCatalogSource(),
    "hitmotop": HitmotopCatalogSource(),
    "jamendo": JamendoCatalogSource(),
    "mock": MockCatalogSource(),
}


def _provider_chain() -> list[str]:
    raw = (settings.catalog_provider_chain or "").strip()
    if not raw:
        return ["zaycev", "hitmotop", "jamendo", "mock"]
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    return parts or ["zaycev", "hitmotop", "jamendo", "mock"]


async def search_catalog(
    client: httpx.AsyncClient, query: str, *, offset: int = 0, limit: int = 20
) -> list[ExternalTrack]:
    q = query.strip()
    chain = _provider_chain()

    if not q:
        mock = SOURCE_REGISTRY.get("mock")
        if mock is None:
            return []
        return await mock.search(client, "", offset=offset, limit=limit)

    for name in chain:
        src = SOURCE_REGISTRY.get(name)
        if src is None:
            logger.warning("unknown catalog provider %r — skipped", name)
            continue
        # MockCatalogSource.search ignores client; Jamendo uses it.
        results = await src.search(client, q, offset=offset, limit=limit)  # type: ignore[union-attr]
        if results:
            return results

    return []
