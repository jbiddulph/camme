from datetime import datetime

from sqlalchemy import DateTime, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.naming import table_name


class Report(Base):
    __tablename__ = table_name('reports')

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    room_name: Mapped[str] = mapped_column(String(80), index=True)
    reported_user: Mapped[str] = mapped_column(String(255))
    reason: Mapped[str] = mapped_column(Text())
    status: Mapped[str] = mapped_column(String(32), server_default=text("'queued'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
