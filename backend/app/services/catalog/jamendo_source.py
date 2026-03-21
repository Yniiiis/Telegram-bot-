import httpx

from app.config import settings
from app.services.catalog.protocol import CatalogSource
from app.services.external_track import ExternalTrack

JAMENDO_TRACKS_URL = "https://api.jamendo.com/v3.0/tracks/"


def _license_short_from_item(item: dict) -> str | None:
    raw = item.get("license_shortname") or item.get("license_short")
    if raw:
        return str(raw).strip() or None
    cc = item.get("license_ccurl")
    if isinstance(cc, str) and "/" in cc.rstrip("/"):
        return cc.rstrip("/").rsplit("/", 1)[-1] or None
    return None


class JamendoCatalogSource(CatalogSource):
    """Official Jamendo API only — stream URLs from the `audio` field (not download endpoints)."""

    async def search(
        self,
        client: httpx.AsyncClient,
        query: str,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> list[ExternalTrack]:
        cid = settings.jamendo_client_id
        if not cid:
            return []

        params = {
            "client_id": cid,
            "format": "json",
            "limit": min(limit, 50),
            "offset": max(0, offset),
            "search": query,
            "audioformat": "mp32",
        }
        r = await client.get(JAMENDO_TRACKS_URL, params=params, timeout=30.0)
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or []
        out: list[ExternalTrack] = []
        for item in results:
            tid = str(item.get("id", ""))
            # Use progressive stream URL only; avoid `audiodownload` (distribution / ToS differ).
            audio = item.get("audio")
            if not tid or not audio:
                continue
            duration = item.get("duration")
            duration_sec = int(duration) if duration is not None else None
            lic_url = item.get("license_ccurl")
            license_url = str(lic_url).strip() if lic_url else None
            out.append(
                ExternalTrack(
                    source="jamendo",
                    external_id=tid,
                    title=str(item.get("name") or "Unknown"),
                    artist=str(item.get("artist_name") or "Unknown"),
                    duration_sec=duration_sec,
                    audio_url=str(audio),
                    cover_url=item.get("image") or item.get("album_image"),
                    license_url=license_url,
                    license_short=_license_short_from_item(item),
                )
            )
        return out
