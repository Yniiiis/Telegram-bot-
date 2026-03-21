from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.track import Track
    from app.models.user import User


class PlayHistory(Base):
    __tablename__ = "play_history"
    __table_args__ = (Index("ix_play_history_user_played", "user_id", "played_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    track_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tracks.id", ondelete="CASCADE"), index=True)
    played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="play_history")
    track: Mapped["Track"] = relationship(back_populates="play_history")
