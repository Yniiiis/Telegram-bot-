from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import get_current_user
from app.models.track import Track
from app.models.user import User
from app.schemas.track import TrackOut
from app.services.playback_media import PlaybackResolveError, resolve_playback_media

router = APIRouter(tags=["tracks"])


@router.get("/track/{track_id}", response_model=TrackOut)
async def get_track(
    track_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> TrackOut:
    track = await db.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")
    return TrackOut.model_validate(track)


@router.post("/track/{track_id}/prepare", status_code=status.HTTP_204_NO_CONTENT)
async def prepare_track_playback(
    track_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Response:
    """
    Warm resolution (yt-dlp, Zaycev play URL, SoundCloud refresh) before the user taps play.
    Safe to call in parallel from the Mini App after search results arrive.
    """
    track = await db.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")
    client = request.app.state.http_client
    try:
        await resolve_playback_media(db, track, client)
    except PlaybackResolveError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
