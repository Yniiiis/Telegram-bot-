from __future__ import annotations

from typing import Protocol

import httpx

from app.services.external_track import ExternalTrack


class MusicCatalogProvider(Protocol):
    """Search + chart slice against one upstream (mirrors `CatalogSource` for engine wiring)."""

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

    async def chart_tracks_slice(
        self,
        client: httpx.AsyncClient,
        offset: int,
        limit: int,
    ) -> tuple[list[ExternalTrack], bool]:
        ...
