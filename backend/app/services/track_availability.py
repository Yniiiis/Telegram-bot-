"""Track availability probing — disabled; re-implement when adding list filters."""

from __future__ import annotations

import httpx

from app.models.track import Track


async def filter_tracks_by_availability(
    client: httpx.AsyncClient,
    tracks: list[Track],
) -> list[Track]:
    return list(tracks)
