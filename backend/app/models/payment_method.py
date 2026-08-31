import uuid
from typing import TYPE_CHECKING
from sqlalchemy import String, Boolean, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, GUID

if TYPE_CHECKING:
    from app.models.wallet import Wallet


class PaymentMethod(Base, TimestampMixin):
    __tablename__ = "payment_methods"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("wallets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(
        String(50),
        default="MOCK",  # MOCK, UPI_VPA, CARD_TOKEN
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(
        String(50),
        default="mock",  # mock, razorpay
        nullable=False,
    )
    token_or_alias: Mapped[str] = mapped_column(
        String(255),
        default="mock_primary_vpa",  # Masked or alias representation - NEVER real PAN or card secret
        nullable=False,
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

    # Relationships
    wallet: Mapped["Wallet"] = relationship("Wallet", back_populates="payment_methods")
