from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, String, Text, Uuid, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.favorite import Favorite
    from app.models.play_history import PlayHistory
    from app.models.playlist import PlaylistTrack


class Track(Base):
    __tablename__ = "tracks"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_tracks_source_external"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    source: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(256))
    title: Mapped[str] = mapped_column(String(512))
    artist: Mapped[str] = mapped_column(String(512))
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audio_url: Mapped[str] = mapped_column(Text())
    cover_url: Mapped[str | None] = mapped_column(Text(), nullable=True)
    license_url: Mapped[str | None] = mapped_column(Text(), nullable=True)
    license_short: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    favorites: Mapped[list["Favorite"]] = relationship(back_populates="track")
    playlist_links: Mapped[list["PlaylistTrack"]] = relationship(back_populates="track")
    play_history: Mapped[list["PlayHistory"]] = relationship(back_populates="track")
