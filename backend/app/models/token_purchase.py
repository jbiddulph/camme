from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.naming import table_name


class TokenPurchase(Base):
    """Stripe Checkout completion — one row per credited session (idempotent)."""

    __tablename__ = table_name('token_purchases')

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey(f'{table_name("users")}.id'), index=True)
    stripe_checkout_session_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    tokens_granted: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
