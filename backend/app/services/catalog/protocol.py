from typing import Protocol

import httpx

from app.services.external_track import ExternalTrack


class CatalogSource(Protocol):
    """Pluggable music catalog: add a provider and register it in `engine.SOURCE_REGISTRY`."""

    async def search(
        self,
        client: httpx.AsyncClient,
        query: str,
        *,
        offset: int,
        limit: int,
        quick: bool = False,
    ) -> list[ExternalTrack]:
        ...
