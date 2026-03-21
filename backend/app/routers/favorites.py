from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.deps import get_current_user
from app.models.favorite import Favorite
from app.models.track import Track
from app.models.user import User
from app.schemas.favorite import FavoriteCreate, FavoritesResponse
from app.schemas.track import TrackOut

router = APIRouter(prefix="/favorites", tags=["favorites"])


@router.get("", response_model=FavoritesResponse)
async def list_favorites(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FavoritesResponse:
    result = await db.execute(
        select(Favorite)
        .where(Favorite.user_id == user.id)
        .options(selectinload(Favorite.track))
        .order_by(Favorite.created_at.desc())
    )
    rows = result.scalars().all()
    tracks = [TrackOut.model_validate(f.track) for f in rows if f.track is not None]
    return FavoritesResponse(tracks=tracks)


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_favorite(
    body: FavoriteCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    track = await db.get(Track, body.track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")
    fav = Favorite(user_id=user.id, track_id=body.track_id)
    db.add(fav)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already in favorites")


@router.delete("/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite(
    track_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    await db.execute(delete(Favorite).where(Favorite.user_id == user.id, Favorite.track_id == track_id))
    await db.commit()
