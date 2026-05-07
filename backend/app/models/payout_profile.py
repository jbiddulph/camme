from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.naming import table_name


class PayoutProfile(Base):
    __tablename__ = table_name('payout_profiles')

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey(table_name('users') + '.id'), unique=True, index=True)
    legal_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    id_verification_status: Mapped[str] = mapped_column(String(24), nullable=False, server_default='pending')
    payout_method: Mapped[str | None] = mapped_column(String(24), nullable=True)
    payout_destination: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_connect_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
