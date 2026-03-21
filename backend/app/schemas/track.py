from uuid import UUID

from pydantic import BaseModel, Field


class TrackOut(BaseModel):
    id: UUID
    title: str
    artist: str
    duration_sec: int | None = None
    audio_url: str
    cover_url: str | None = None
    license_url: str | None = None
    license_short: str | None = None
    source: str
    external_id: str

    model_config = {"from_attributes": True}


class SearchResponse(BaseModel):
    tracks: list[TrackOut]
    offset: int = 0
    limit: int = 20
    has_more: bool = False
