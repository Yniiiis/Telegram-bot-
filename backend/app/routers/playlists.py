from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.deps import get_current_user
from app.models.playlist import Playlist, PlaylistTrack
from app.models.track import Track
from app.models.user import User
from app.schemas.playlist import (
    PlaylistCreate,
    PlaylistDetailOut,
    PlaylistOut,
    PlaylistTrackAdd,
    PlaylistUpdate,
)
from app.schemas.track import TrackOut

router = APIRouter(prefix="/playlists", tags=["playlists"])


@router.get("", response_model=list[PlaylistOut])
async def list_playlists(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PlaylistOut]:
    result = await db.execute(
        select(Playlist).where(Playlist.user_id == user.id).order_by(Playlist.created_at.desc())
    )
    return [PlaylistOut.model_validate(p) for p in result.scalars().all()]


@router.post("", response_model=PlaylistOut, status_code=status.HTTP_201_CREATED)
async def create_playlist(
    body: PlaylistCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlaylistOut:
    pl = Playlist(user_id=user.id, name=body.name)
    db.add(pl)
    await db.commit()
    await db.refresh(pl)
    return PlaylistOut.model_validate(pl)


@router.get("/{playlist_id}", response_model=PlaylistDetailOut)
async def get_playlist(
    playlist_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlaylistDetailOut:
    result = await db.execute(
        select(Playlist)
        .where(Playlist.id == playlist_id, Playlist.user_id == user.id)
        .options(selectinload(Playlist.tracks).selectinload(PlaylistTrack.track))
    )
    pl = result.scalar_one_or_none()
    if pl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playlist not found")
    links = sorted(pl.tracks, key=lambda x: (x.position, x.added_at))
    tracks = [TrackOut.model_validate(l.track) for l in links if l.track is not None]
    return PlaylistDetailOut(id=pl.id, name=pl.name, tracks=tracks)


@router.patch("/{playlist_id}", response_model=PlaylistOut)
async def rename_playlist(
    playlist_id: UUID,
    body: PlaylistUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlaylistOut:
    result = await db.execute(
        select(Playlist).where(Playlist.id == playlist_id, Playlist.user_id == user.id)
    )
    pl = result.scalar_one_or_none()
    if pl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playlist not found")
    pl.name = body.name
    await db.commit()
    await db.refresh(pl)
    return PlaylistOut.model_validate(pl)


@router.delete("/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playlist(
    playlist_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    result = await db.execute(
        select(Playlist).where(Playlist.id == playlist_id, Playlist.user_id == user.id)
    )
    pl = result.scalar_one_or_none()
    if pl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playlist not found")
    await db.execute(delete(Playlist).where(Playlist.id == pl.id))
    await db.commit()


@router.post("/{playlist_id}/tracks", status_code=status.HTTP_201_CREATED)
async def add_playlist_track(
    playlist_id: UUID,
    body: PlaylistTrackAdd,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    result = await db.execute(
        select(Playlist).where(Playlist.id == playlist_id, Playlist.user_id == user.id)
    )
    pl = result.scalar_one_or_none()
    if pl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playlist not found")
    track = await db.get(Track, body.track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")

    if body.position is not None:
        pos = body.position
    else:
        max_pos = await db.scalar(
            select(func.coalesce(func.max(PlaylistTrack.position), -1)).where(
                PlaylistTrack.playlist_id == playlist_id
            )
        )
        pos = int(max_pos) + 1

    link = PlaylistTrack(playlist_id=playlist_id, track_id=body.track_id, position=pos)
    db.add(link)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Track already in playlist")


@router.delete("/{playlist_id}/tracks/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_playlist_track(
    playlist_id: UUID,
    track_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    result = await db.execute(
        select(Playlist).where(Playlist.id == playlist_id, Playlist.user_id == user.id)
    )
    pl = result.scalar_one_or_none()
    if pl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playlist not found")
    await db.execute(
        delete(PlaylistTrack).where(
            PlaylistTrack.playlist_id == playlist_id, PlaylistTrack.track_id == track_id
        )
    )
    await db.commit()
