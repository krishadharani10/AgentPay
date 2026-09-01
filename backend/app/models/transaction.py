import uuid
from enum import Enum
from typing import Optional, List, Dict, Set, Union, TYPE_CHECKING
from sqlalchemy import String, Float, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, GUID

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.wallet import Wallet
    from app.models.merchant import Merchant
    from app.models.payment_method import PaymentMethod
    from app.models.audit_log import AuditLog
    from app.models.payment_attempt import PaymentAttempt


class InvalidPaymentStateError(Exception):
    """
    Raised when an illegal transaction state transition is attempted
    or an operation is invalid for current payment state.
    """
    pass


class MaxRetriesExceededError(InvalidPaymentStateError):
    """
    Raised when an attempt to retry a transaction exceeds the authoritative MAX_RETRIES limit.
    """
    pass


class TransactionStatus(str, Enum):
    """
    Authoritative state machine definitions for AgentPay transactions.
    Lifecycle:
      REQUESTED → POLICY_CHECK → APPROVED → PAYMENT_PENDING → SUCCESS / FAILED
                              ↘ REJECTED
    """
    REQUESTED = "REQUESTED"
    POLICY_CHECK = "POLICY_CHECK"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


# Authoritative State Transition Matrix
VALID_STATE_TRANSITIONS: Dict[TransactionStatus, Set[TransactionStatus]] = {
    TransactionStatus.REQUESTED: {TransactionStatus.POLICY_CHECK},
    TransactionStatus.POLICY_CHECK: {TransactionStatus.APPROVED, TransactionStatus.REJECTED},
    TransactionStatus.APPROVED: {TransactionStatus.PAYMENT_PENDING},
    TransactionStatus.PAYMENT_PENDING: {TransactionStatus.SUCCESS, TransactionStatus.FAILED},
    TransactionStatus.SUCCESS: set(),   # Terminal state
    TransactionStatus.REJECTED: set(),  # Terminal state
    TransactionStatus.FAILED: set(),    # Terminal state (retries handled in subsequent phases)
}


def validate_transition(
    current_status: Union[TransactionStatus, str],
    target_status: Union[TransactionStatus, str],
) -> None:
    """
    Centralized validation guard for transaction state transitions.
    Raises InvalidPaymentStateError on illegal or unrecognized transitions.
    """
    try:
        curr_enum = current_status if isinstance(current_status, TransactionStatus) else TransactionStatus(str(current_status).upper())
    except ValueError:
        raise InvalidPaymentStateError(f"Current transaction status '{current_status}' is not a valid TransactionStatus.")

    try:
        tgt_enum = target_status if isinstance(target_status, TransactionStatus) else TransactionStatus(str(target_status).upper())
    except ValueError:
        raise InvalidPaymentStateError(f"Target transaction status '{target_status}' is not a valid TransactionStatus.")

    allowed_targets = VALID_STATE_TRANSITIONS.get(curr_enum, set())
    if tgt_enum not in allowed_targets:
        raise InvalidPaymentStateError(
            f"Illegal transaction state transition: cannot transition from {curr_enum.value} to {tgt_enum.value}."
        )


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("wallets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    merchant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("merchants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    merchant_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    amount: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(10),
        default="INR",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=TransactionStatus.REQUESTED.value,
        index=True,
        nullable=False,
    )
    decision_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    payment_method_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("payment_methods.id", ondelete="SET NULL"),
        nullable=True,
    )
    payment_provider: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    provider_payment_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # Relationships
    agent: Mapped["Agent"] = relationship("Agent", back_populates="transactions")
    wallet: Mapped["Wallet"] = relationship("Wallet", back_populates="transactions")
    merchant: Mapped[Optional["Merchant"]] = relationship("Merchant")
    payment_method: Mapped[Optional["PaymentMethod"]] = relationship("PaymentMethod")
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="transaction",
    )
    payment_attempts: Mapped[List["PaymentAttempt"]] = relationship(
        "PaymentAttempt",
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="PaymentAttempt.attempt_number",
    )

    def transition_to(
        self,
        target_status: Union[TransactionStatus, str],
        *,
        allow_retry: bool = False,
    ) -> None:
        """
        Authoritative instance method for advancing transaction state.
        All lifecycle transitions MUST pass through this method.
        If allow_retry=True (authorized only by PaymentService.retry_payment after
        validating attempt counts), FAILED -> PAYMENT_PENDING is permitted.
        """
        tgt_enum = target_status if isinstance(target_status, TransactionStatus) else TransactionStatus(str(target_status).upper())
        if allow_retry and self.status == TransactionStatus.FAILED.value and tgt_enum == TransactionStatus.PAYMENT_PENDING:
            self.status = TransactionStatus.PAYMENT_PENDING.value
            return

        validate_transition(self.status, target_status)
        self.status = tgt_enum.value
