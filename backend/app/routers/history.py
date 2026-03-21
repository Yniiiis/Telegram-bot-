from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import get_current_user
from app.models.play_history import PlayHistory
from app.models.track import Track
from app.models.user import User
from app.schemas.history import RecentTracksResponse, RecordPlayRequest
from app.schemas.track import TrackOut

router = APIRouter(prefix="/history", tags=["history"])


@router.post("/play", status_code=status.HTTP_204_NO_CONTENT)
async def record_play(
    body: RecordPlayRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    track = await db.get(Track, body.track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")
    db.add(PlayHistory(user_id=user.id, track_id=body.track_id))
    await db.commit()


@router.get("/recent", response_model=RecentTracksResponse)
async def recent_tracks(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RecentTracksResponse:
    subq = (
        select(PlayHistory.track_id, func.max(PlayHistory.played_at).label("last_played"))
        .where(PlayHistory.user_id == user.id)
        .group_by(PlayHistory.track_id)
        .subquery()
    )
    stmt = (
        select(Track)
        .join(subq, Track.id == subq.c.track_id)
        .order_by(desc(subq.c.last_played))
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return RecentTracksResponse(tracks=[TrackOut.model_validate(t) for t in rows])
