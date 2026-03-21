from uuid import UUID

from pydantic import BaseModel

from app.schemas.track import TrackOut


class RecordPlayRequest(BaseModel):
    track_id: UUID


class RecentTracksResponse(BaseModel):
    tracks: list[TrackOut]
