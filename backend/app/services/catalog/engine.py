import logging

import httpx

from app.services.catalog.hitmotop_source import HitmotopCatalogSource
from app.services.catalog.protocol import CatalogSource
from app.services.catalog.request_coalesce import coalesce
from app.services.external_track import ExternalTrack

logger = logging.getLogger(__name__)

_hitmotop = HitmotopCatalogSource()

SOURCE_REGISTRY: dict[str, CatalogSource] = {
    "hitmotop": _hitmotop,
}


def get_catalog_provider_chain() -> list[str]:
    return ["hitmotop"]


def _search_coalesce_key(query: str, offset: int, limit: int, *, artist_focus: bool, quick: bool) -> str:
    af = "1" if artist_focus else "0"
    qk = "1" if quick else "0"
    return f"hitmotop\t{query.strip().lower()}\t{offset}\t{limit}\t{af}\t{qk}"


async def search_catalog(
    client: httpx.AsyncClient,
    query: str,
    *,
    offset: int = 0,
    limit: int = 20,
    artist_focus: bool = False,
    quick: bool = False,
) -> list[ExternalTrack]:
    _ = artist_focus
    key = _search_coalesce_key(query, offset, limit, artist_focus=artist_focus, quick=quick)

    async def _run() -> list[ExternalTrack]:
        try:
            return await _hitmotop.search(
                client, query.strip(), offset=offset, limit=limit, quick=quick
            )
        except Exception as exc:
            logger.warning("hitmotop search failed: %s", exc)
            return []

    return await coalesce(key, _run)
