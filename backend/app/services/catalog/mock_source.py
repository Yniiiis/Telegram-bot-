from app.services.catalog.protocol import CatalogSource
from app.services.external_track import ExternalTrack

# Royalty-free demo streams (SoundHelix). Safe fallback when no API keys are configured.
_MOCK: tuple[ExternalTrack, ...] = tuple(
    ExternalTrack(
        source="mock",
        external_id=f"soundhelix-{i}",
        title=f"SoundHelix Song {i}",
        artist="T. Schürger / SoundHelix",
        duration_sec=300 + i * 37,
        audio_url=f"https://www.soundhelix.com/examples/mp3/SoundHelix-Song-{i}.mp3",
        cover_url=None,
        license_url="https://www.soundhelix.com/examples/examples.html",
        license_short="demo",
    )
    for i in range(1, 13)
)


class MockCatalogSource(CatalogSource):
    async def search(
        self,
        _client: object,
        query: str,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> list[ExternalTrack]:
        q = query.strip().lower()
        if not q:
            pool = list(_MOCK)
        else:
            matched = [t for t in _MOCK if q in t.title.lower() or q in t.artist.lower()]
            pool = matched if matched else list(_MOCK)
        start = max(0, offset)
        return pool[start : start + limit]
