from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.track import TrackOut


class PlaylistCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class PlaylistUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class PlaylistOut(BaseModel):
    id: UUID
    name: str

    model_config = {"from_attributes": True}


class PlaylistDetailOut(PlaylistOut):
    tracks: list[TrackOut]


class PlaylistTrackAdd(BaseModel):
    track_id: UUID
    position: int | None = None
