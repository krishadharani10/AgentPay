import uuid
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import String, Float, Boolean, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, GUID

if TYPE_CHECKING:
    from app.models.agent import Agent


class Policy(Base, TimestampMixin):
    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        default="Default Spending Policy",
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    max_transaction_amount: Mapped[float] = mapped_column(
        Float,
        default=8000.0,
        nullable=False,
    )
    daily_spending_limit: Mapped[float] = mapped_column(
        Float,
        default=15000.0,
        nullable=False,
    )
    allowed_categories: Mapped[List[str]] = mapped_column(
        JSON,
        default=lambda: ["utilities", "subscriptions", "travel"],
        nullable=False,
    )
    blocked_categories: Mapped[List[str]] = mapped_column(
        JSON,
        default=lambda: ["gambling", "crypto"],
        nullable=False,
    )
    allowed_merchants: Mapped[List[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    blocked_merchants: Mapped[List[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    wallet_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    agent: Mapped["Agent"] = relationship("Agent", back_populates="policies")
