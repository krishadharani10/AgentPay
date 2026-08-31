import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from sqlalchemy import String, Text, JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, GUID

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.transaction import Transaction


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        default="POLICY_EVALUATION",
        index=True,
        nullable=False,
    )
    action: Mapped[str] = mapped_column(
        String(100),
        default="EVALUATE_POLICY",
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    rules_checked: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON,
        nullable=True,
    )
    metadata_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )

    # Relationships
    agent: Mapped[Optional["Agent"]] = relationship("Agent", back_populates="audit_logs")
    transaction: Mapped[Optional["Transaction"]] = relationship("Transaction", back_populates="audit_logs")
