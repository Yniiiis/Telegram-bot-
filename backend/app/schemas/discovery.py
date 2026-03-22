from pydantic import BaseModel, Field

from app.schemas.track import TrackOut


class DailyContextOut(BaseModel):
    id: str
    label: str
    query: str


class DiscoveryMetaResponse(BaseModel):
    contexts: list[DailyContextOut]
    catalog_sources: list[str]
    weekday_mood_query: str


class TrackListResponse(BaseModel):
    tracks: list[TrackOut]


class DiscoveryPicksResponse(BaseModel):
    tracks: list[TrackOut]
    used_query: str
    context_id: str | None = None
    mode: str = Field(description="weekday | context")
