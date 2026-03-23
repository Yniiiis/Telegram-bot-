import logging
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import get_current_user
from app.models.track import Track
from app.models.user import User
from app.schemas.discovery import TrackListResponse
from app.schemas.track import TrackOut
from app.services.similar_tracks import collect_similar_catalog_tracks
from app.services.track_availability import filter_tracks_by_availability
from app.services.track_upsert import upsert_external_tracks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/similar", response_model=TrackListResponse)
async def similar_to_track(
    request: Request,
    track_id: UUID = Query(..., description="Currently playing track UUID"),
    limit: int = Query(16, ge=1, le=40),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> TrackListResponse:
    """Tracks from catalog search ranked like the seed artist/title (for radio / auto-queue)."""
    track = await db.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")

    client: httpx.AsyncClient = request.app.state.http_client
    try:
        external = await collect_similar_catalog_tracks(client, track, pool=max(limit * 3, 36))
    except Exception as exc:
        logger.warning("collect_similar_catalog_tracks failed: %s", exc)
        external = []

    if not external:
        return TrackListResponse(tracks=[])

    upserted = await upsert_external_tracks(db, external)
    filtered = await filter_tracks_by_availability(client, upserted)
    ordered = [t for t in filtered if t.id != track.id][:limit]
    return TrackListResponse(tracks=[TrackOut.model_validate(t) for t in ordered])
