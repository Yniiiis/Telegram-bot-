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
    """Creative Commons / license info page when provided by the catalog (e.g. Jamendo)."""
    license_url: str | None = None
    """Short license label for display (e.g. cc-by-nc)."""
    license_short: str | None = None
