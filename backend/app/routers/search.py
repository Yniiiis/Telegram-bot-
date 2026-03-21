from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas.track import SearchResponse, TrackOut
from app.services.catalog import search_catalog
from app.services.search_cache import get_cached, set_cached
from app.services.track_upsert import upsert_external_tracks

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
async def search_music(
    request: Request,
    q: str = Query(..., min_length=1, description="Song or artist query"),
    offset: int = Query(0, ge=0, le=10_000),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> SearchResponse:
    client = request.app.state.http_client

    cached = await get_cached(q, offset, limit)
    if cached is not None:
        external = cached
    else:
        external = await search_catalog(client, q, offset=offset, limit=limit)
        await set_cached(q, offset, limit, external)

    tracks = await upsert_external_tracks(db, external)
    has_more = len(external) >= limit
    return SearchResponse(
        tracks=[TrackOut.model_validate(t) for t in tracks],
        offset=offset,
        limit=limit,
        has_more=has_more,
    )
