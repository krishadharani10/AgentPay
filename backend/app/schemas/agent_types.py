"""
Day 2 Phase 1 — Structured Agent Schemas.

These schemas represent the internal data flow within the AI Agent:
  User Message → TransactionIntent → AgentDecision → PaymentRequest → AgentResponse

They complement (not duplicate) the existing AgentRunRequest/AgentRunResponse
API schemas in schemas/agent.py.
"""
from uuid import UUID
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class TransactionIntent(BaseModel):
    """
    Structured output from the LLM's interpretation of a natural-language payment request.
    The LLM converts user messages like 'Pay my electricity bill of ₹1,240'
    or 'Pay my Netflix subscription' into this deterministic schema for downstream processing.
    """
    merchant: str = Field(..., description="Merchant/vendor name")
    amount: Optional[float] = Field(default=None, description="Payment amount if specified by user")
    currency: str = Field(default="INR", description="Currency code")
    category: str = Field(..., description="Spending category (e.g. utilities, subscriptions)")
    description: str = Field(default="", description="Purpose or description of the payment")
    bill_id: Optional[str] = Field(default=None, description="Bill/invoice UUID if available")


class AgentDecision(BaseModel):
    """
    Result of the deterministic Policy Engine evaluation.
    This is NEVER produced by the LLM — always by PolicyEngine.evaluate().
    """
    allowed: bool = Field(..., description="Whether the payment is authorized")
    decision_code: str = Field(..., description="Machine-readable decision code (e.g. APPROVED, TX_LIMIT_EXCEEDED)")
    reason: str = Field(..., description="Human-readable explanation of the decision")
    policy_checks: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Individual rule check results from the policy engine",
    )


class PaymentRequest(BaseModel):
    """
    Validated payment request that is allowed to reach PaymentService.
    Only created when AgentDecision.allowed is True.
    INVARIANT: A PaymentRequest must never exist without a preceding APPROVED AgentDecision.
    """
    merchant_name: str
    amount: float = Field(..., gt=0)
    currency: str = "INR"
    category: str
    agent_id: Optional[UUID] = None
    bill_id: Optional[UUID] = None
    idempotency_key: str
    metadata: Optional[Dict[str, Any]] = None


class AgentResponse(BaseModel):
    """
    Clean API-facing response from the agent orchestration pipeline.
    Provides the user with a complete summary of what happened.
    """
    success: bool
    decision: str = Field(..., description="ALLOWED or DENIED")
    message: str = Field(..., description="Human-readable explanation for the user")
    payment_status: Optional[str] = Field(default=None, description="PENDING, SUCCESS, FAILED, REJECTED")
    payment_id: Optional[str] = Field(default=None, description="Transaction UUID when payment was attempted")
    explanation: str = Field(default="", description="Detailed explanation of the decision or result")
    decision_code: Optional[str] = None
    amount: Optional[float] = None
    merchant_name: Optional[str] = None
    provider_payment_id: Optional[str] = None
    rules_checked: Optional[List[Dict[str, Any]]] = None
    remaining_daily_budget: Optional[float] = None
    audit_trail: Optional[List[Dict[str, Any]]] = None
