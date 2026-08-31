from uuid import UUID
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class PaymentMethodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    wallet_id: UUID
    type: str
    provider: str
    token_or_alias: str
    is_primary: bool
    is_active: bool
    priority: int
    created_at: datetime
    updated_at: datetime


class WalletBase(BaseModel):
    status: str = "ACTIVE"
    daily_spending_limit: float = Field(default=10000.0, ge=0)
    per_transaction_limit: float = Field(default=5000.0, ge=0)
    currency: str = "INR"


class WalletUpdate(BaseModel):
    status: Optional[str] = None
    daily_spending_limit: Optional[float] = Field(default=None, ge=0)
    per_transaction_limit: Optional[float] = Field(default=None, ge=0)


class WalletResponse(WalletBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID
    payment_methods: List[PaymentMethodResponse] = []
    created_at: datetime
    updated_at: datetime


class WalletSummaryResponse(WalletResponse):
    current_daily_spent: float
    remaining_daily_budget: float
