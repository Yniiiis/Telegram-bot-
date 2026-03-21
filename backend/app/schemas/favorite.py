from uuid import UUID

from pydantic import BaseModel

from app.schemas.track import TrackOut


class FavoriteCreate(BaseModel):
    track_id: UUID


class FavoritesResponse(BaseModel):
    tracks: list[TrackOut]
