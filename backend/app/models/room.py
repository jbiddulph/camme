from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.naming import table_name


class Room(Base):
    __tablename__ = table_name('rooms')

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey(f'{table_name("users")}.id'),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    creator: Mapped['User | None'] = relationship('User', back_populates='rooms')
