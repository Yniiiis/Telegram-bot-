from uuid import UUID

from sqlalchemy import ForeignKey, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FeaturedNewRelease(Base):
    """Curated «new on platforms» rows for the home screen; refreshed periodically."""

    __tablename__ = "featured_new_releases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    track_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tracks.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
