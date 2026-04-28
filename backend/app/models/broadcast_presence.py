from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.naming import table_name


class BroadcastPresence(Base):
    __tablename__ = table_name('broadcast_presence')

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    room_name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey(f'{table_name("users")}.id'), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    thumbnail_data_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_live: Mapped[bool] = mapped_column(Boolean, default=True)
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
