"""Pluggable music providers (Hitmotop today; same interface for future sources)."""

from app.services.music_provider.protocol import MusicCatalogProvider

__all__ = ["MusicCatalogProvider"]
