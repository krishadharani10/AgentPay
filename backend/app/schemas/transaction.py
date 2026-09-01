from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.transaction import TransactionStatus


class TransactionBase(BaseModel):
    merchant_name: str
    category: str
    amount: float = Field(..., gt=0)
    currency: str = "INR"
    status: str = TransactionStatus.REQUESTED.value
    decision_reason: Optional[str] = None
    payment_provider: Optional[str] = None
    provider_payment_id: Optional[str] = None


class TransactionCreate(TransactionBase):
    idempotency_key: str
    agent_id: UUID
    wallet_id: UUID
    merchant_id: Optional[UUID] = None
    payment_method_id: Optional[UUID] = None


class TransactionResponse(TransactionBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    idempotency_key: str
    agent_id: UUID
    wallet_id: UUID
    merchant_id: Optional[UUID] = None
    payment_method_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
