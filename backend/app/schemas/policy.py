from uuid import UUID
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class PolicyBase(BaseModel):
    name: str = "Default Spending Policy"
    description: Optional[str] = None
    max_transaction_amount: float = Field(default=5000.0, ge=0)
    daily_spending_limit: float = Field(default=10000.0, ge=0)
    allowed_categories: List[str] = Field(default_factory=lambda: ["utilities", "subscriptions", "travel"])
    blocked_categories: List[str] = Field(default_factory=lambda: ["gambling", "crypto"])
    allowed_merchants: List[str] = Field(default_factory=list)
    blocked_merchants: List[str] = Field(default_factory=list)
    wallet_enabled: bool = True
    is_active: bool = True


class PolicyCreate(PolicyBase):
    agent_id: UUID


class PolicyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    max_transaction_amount: Optional[float] = Field(default=None, ge=0)
    daily_spending_limit: Optional[float] = Field(default=None, ge=0)
    allowed_categories: Optional[List[str]] = None
    blocked_categories: Optional[List[str]] = None
    allowed_merchants: Optional[List[str]] = None
    blocked_merchants: Optional[List[str]] = None
    wallet_enabled: Optional[bool] = None
    is_active: Optional[bool] = None


class PolicyResponse(PolicyBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID
    created_at: datetime
    updated_at: datetime


class PolicyEvaluateRequest(BaseModel):
    agent_id: Optional[UUID] = None
    merchant_name: str
    amount: float = Field(..., gt=0, description="Transaction amount to evaluate")
    category: str
    currency: str = "INR"
    idempotency_key: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class RuleCheckResult(BaseModel):
    rule: str
    passed: bool
    details: str


class PolicyEvaluateResponse(BaseModel):
    approved: bool
    decision_code: str
    reason: str
    rules_checked: List[RuleCheckResult]
    remaining_daily_budget: float
    current_daily_spent: float
    audit_log_id: Optional[UUID] = None
