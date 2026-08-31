from uuid import UUID
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    message: str = Field(..., description="Natural language prompt/command for agent, e.g. 'Pay my electricity bill'")
    agent_id: Optional[UUID] = None
    bill_id: Optional[UUID] = None
    merchant_name: Optional[str] = None
    amount: Optional[float] = Field(default=None, gt=0)
    category: Optional[str] = None
    force_failure: bool = False
    retry_if_failed: bool = False


class AgentRunResponse(BaseModel):
    success: bool
    decision: str
    decision_code: str
    message: str
    payment_id: Optional[str] = None
    provider_payment_id: Optional[str] = None
    payment_status: Optional[str] = None
    amount: Optional[float] = None
    merchant_name: Optional[str] = None
    rules_checked: Optional[List[Dict[str, Any]]] = None
    remaining_daily_budget: Optional[float] = None
    audit_trail: Optional[List[Dict[str, Any]]] = None
