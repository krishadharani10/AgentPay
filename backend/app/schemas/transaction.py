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


from app.schemas.payment_attempt import PaymentAttemptResponse
from app.schemas.audit_log import AuditLogResponse
from typing import List


class TransactionResponse(TransactionBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    idempotency_key: str
    agent_id: UUID
    wallet_id: UUID
    merchant_id: Optional[UUID] = None
    payment_method_id: Optional[UUID] = None
    payment_method_type: Optional[str] = None
    payment_method_alias: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class TransactionDetailResponse(TransactionResponse):
    payment_attempts: List[PaymentAttemptResponse] = []
    audit_logs: List[AuditLogResponse] = []
    merchant_description: Optional[str] = None
    merchant_website: Optional[str] = None
