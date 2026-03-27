from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas.track import SearchResponse, TrackOut
from app.services.catalog import search_catalog
from app.services.catalog.engine import SOURCE_REGISTRY
from app.services.catalog.hitmotop_source import HitmotopCatalogSource
from app.services.search_cache import get_cached, set_cached
from app.services.track_upsert import upsert_external_tracks

router = APIRouter(tags=["search"])

_FEED_CACHE_Q = "__hitmotop_charts_feed__"


@router.get("/search/feed", response_model=SearchResponse)
async def hitmotop_charts_feed(
    request: Request,
    offset: int = Query(0, ge=0, le=10_000),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> SearchResponse:
    """Tracks from Hitmotop list page (see HITMOTOP_CHARTS_PATH, default /2026)."""
    client = request.app.state.http_client

    cached = await get_cached(_FEED_CACHE_Q, offset, limit, artist_focus=False)
    if cached is not None:
        external = cached
        # Cache stores rows only; treat full page as maybe more (same as text search cache).
        has_more = len(external) >= limit
    else:
        src = SOURCE_REGISTRY.get("hitmotop")
        if not isinstance(src, HitmotopCatalogSource):
            return SearchResponse(tracks=[], offset=offset, limit=limit, has_more=False)
        external, has_more = await src.chart_tracks_slice(client, offset, limit)
        await set_cached(_FEED_CACHE_Q, offset, limit, external, artist_focus=False)

    tracks = await upsert_external_tracks(db, external)
    tracks = tracks[:limit]
    return SearchResponse(
        tracks=[TrackOut.model_validate(t) for t in tracks],
        offset=offset,
        limit=limit,
        has_more=has_more,
    )


@router.get("/search", response_model=SearchResponse)
async def search_music(
    request: Request,
    q: str = Query(..., min_length=1, description="Song or artist query"),
    offset: int = Query(0, ge=0, le=10_000),
    limit: int = Query(20, ge=1, le=50),
    artist_focus: bool = Query(
        False,
        description="Reserved for future catalog tuning",
    ),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> SearchResponse:
    client = request.app.state.http_client

    cached = await get_cached(q, offset, limit, artist_focus=artist_focus)
    if cached is not None:
        external = cached
    else:
        external = await search_catalog(
            client, q, offset=offset, limit=limit, artist_focus=artist_focus
        )
        await set_cached(q, offset, limit, external, artist_focus=artist_focus)

    tracks = await upsert_external_tracks(db, external)
    tracks = tracks[:limit]
    has_more = len(external) >= limit
    return SearchResponse(
        tracks=[TrackOut.model_validate(t) for t in tracks],
        offset=offset,
        limit=limit,
        has_more=has_more,
    )
