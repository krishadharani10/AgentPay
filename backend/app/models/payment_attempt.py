import uuid
from typing import Optional, Dict, Any, TYPE_CHECKING
from sqlalchemy import String, Integer, Text, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, GUID

if TYPE_CHECKING:
    from app.models.transaction import Transaction
    from app.models.payment_method import PaymentMethod


class PaymentAttempt(Base, TimestampMixin):
    """
    Persisted entity representing an individual payment provider dispatch attempt.
    Tracks execution status, provider IDs, errors, payloads, and attempt numbering.
    """
    __tablename__ = "payment_attempts"
    __table_args__ = (
        UniqueConstraint("transaction_id", "attempt_number", name="uq_payment_attempts_tx_attempt"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payment_method_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("payment_methods.id", ondelete="SET NULL"),
        nullable=True,
    )
    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="PENDING",  # PENDING, SUCCESS, FAILED, TIMEOUT
        index=True,
    )
    provider_payment_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    error_code: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    response_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )

    # Relationships
    transaction: Mapped["Transaction"] = relationship(
        "Transaction",
        back_populates="payment_attempts",
    )
    payment_method: Mapped[Optional["PaymentMethod"]] = relationship(
        "PaymentMethod",
    )
