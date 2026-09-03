from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class PaymentAttemptBase(BaseModel):
    attempt_number: int = Field(default=1, ge=1)
    status: str = "PENDING"
    provider_payment_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    response_payload: Optional[Dict[str, Any]] = None


class PaymentAttemptCreate(PaymentAttemptBase):
    transaction_id: UUID
    payment_method_id: Optional[UUID] = None


class PaymentAttemptResponse(PaymentAttemptBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_id: UUID
    payment_method_id: Optional[UUID] = None
    payment_method_type: Optional[str] = None
    payment_method_alias: Optional[str] = None
    created_at: datetime
    updated_at: datetime
