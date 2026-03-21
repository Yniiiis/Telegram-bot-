from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import get_current_user
from app.models.track import Track
from app.models.user import User
from app.schemas.track import TrackOut

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
