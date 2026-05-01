from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.naming import table_name


class Tip(Base):
    __tablename__ = table_name('tips')

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    from_user_id: Mapped[int] = mapped_column(ForeignKey(f'{table_name("users")}.id'), index=True)
    to_user_id: Mapped[int] = mapped_column(ForeignKey(f'{table_name("users")}.id'), index=True)
    room_name: Mapped[str] = mapped_column(String(80), index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    vibrate_strength: Mapped[int] = mapped_column(Integer, nullable=False)
    vibrate_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
