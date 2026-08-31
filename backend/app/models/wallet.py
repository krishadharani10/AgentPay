import uuid
from typing import List, TYPE_CHECKING
from sqlalchemy import String, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, GUID

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.payment_method import PaymentMethod
    from app.models.transaction import Transaction


class Wallet(Base, TimestampMixin):
    __tablename__ = "wallets"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("agents.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="ACTIVE",  # ACTIVE, DISABLED, FROZEN
        nullable=False,
    )
    daily_spending_limit: Mapped[float] = mapped_column(
        Float,
        default=10000.0,
        nullable=False,
    )
    per_transaction_limit: Mapped[float] = mapped_column(
        Float,
        default=5000.0,
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(10),
        default="INR",
        nullable=False,
    )

    # Relationships
    agent: Mapped["Agent"] = relationship("Agent", back_populates="wallet")
    payment_methods: Mapped[List["PaymentMethod"]] = relationship(
        "PaymentMethod",
        back_populates="wallet",
        cascade="all, delete-orphan",
        order_by="PaymentMethod.priority",
    )
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction",
        back_populates="wallet",
    )
