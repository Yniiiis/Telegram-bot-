from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExternalTrack:
    source: str
    external_id: str
    title: str
    artist: str
    duration_sec: int | None
    audio_url: str
    cover_url: str | None
    """License / terms URL when provided by the catalog source."""
    license_url: str | None = None
    """Short license label for display (e.g. cc-by-nc)."""
    license_short: str | None = None
    """Last.fm listeners (popularity hint for ranking / rotation)."""
    listeners: int | None = None
    """Unix time of release when known (novelty hint)."""
    released_ts: int | None = None
