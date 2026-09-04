"""
Autonomous Commerce Task Schemas for AgentPay.

Defines schemas for higher-level autonomous commerce tasks (e.g. Flight Booking,
Restaurant Reservations) that operate above the authoritative payment core.

Flow:
  User Request → TaskIntent → TaskOrchestrator → Commerce Tool → Selected Option → TransactionIntent
"""
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from pydantic import BaseModel, Field, field_validator

from app.schemas.agent_types import TransactionIntent


class TaskType(str, Enum):
    """Supported autonomous task types."""
    DIRECT_PAYMENT = "DIRECT_PAYMENT"
    BOOK_FLIGHT = "BOOK_FLIGHT"
    RESERVE_RESTAURANT = "RESERVE_RESTAURANT"


class TaskIntent(BaseModel):
    """
    Structured task intent representing the user's commercial goal.
    Accommodates flight booking, restaurant reservation, and direct payment parameters.
    """
    task_type: TaskType = Field(..., description="Type of commercial task to execute")
    user_message: str = Field(..., description="Original or extracted natural-language command")
    budget: Optional[float] = Field(default=None, description="Exact or target budget")
    max_budget: Optional[float] = Field(default=None, description="Maximum budget ceiling for search")
    date: Optional[str] = Field(default=None, description="Target date (e.g. YYYY-MM-DD, '2026-09-22')")
    time: Optional[str] = Field(default=None, description="Target time (e.g. '8:00 PM', '20:00')")
    origin: Optional[str] = Field(default=None, description="Departure airport or city for flights (e.g. AMD, Ahmedabad)")
    destination: Optional[str] = Field(default=None, description="Arrival airport or city for flights (e.g. BOM, Mumbai)")
    city: Optional[str] = Field(default=None, description="City for restaurant or localized commerce")
    party_size: Optional[int] = Field(default=None, description="Number of guests/seats")
    merchant: Optional[str] = Field(default=None, description="Preferred merchant/airline/restaurant name")
    category: Optional[str] = Field(default=None, description="Category override (e.g. travel, dining, utilities)")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional context or tool constraints")

    @field_validator("budget", "max_budget")
    @classmethod
    def validate_budget_positive(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0:
            raise ValueError("Budget cannot be negative")
        return v

    @field_validator("party_size")
    @classmethod
    def validate_party_size_positive(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValueError("Party size must be greater than zero")
        return v

    def validate_task_requirements(self, strict: bool = False) -> Tuple[bool, List[str]]:
        """
        Validate that all required domain fields are present for the given task type.
        Returns:
            Tuple[bool, List[str]]: (is_valid, list of missing field names)
        """
        missing: List[str] = []

        if self.task_type == TaskType.BOOK_FLIGHT:
            if not self.origin:
                missing.append("origin")
            if not self.destination:
                missing.append("destination")
            if strict and not self.date:
                missing.append("date")
            if self.max_budget is None and self.budget is None:
                missing.append("max_budget")

        elif self.task_type == TaskType.RESERVE_RESTAURANT:
            if not self.city:
                missing.append("city")
            if strict and not self.date:
                missing.append("date")
            if strict and not self.time:
                missing.append("time")
            if strict and not self.party_size:
                missing.append("party_size")
            if self.max_budget is None and self.budget is None:
                missing.append("max_budget")

        elif self.task_type == TaskType.DIRECT_PAYMENT:
            if self.budget is None and self.max_budget is None and not self.merchant:
                missing.append("amount_or_merchant")

        return len(missing) == 0, missing


class SelectedFlightOption(BaseModel):
    """Result from the flight commerce tool."""
    flight_id: str
    airline: str
    flight_number: str
    origin: str
    destination: str
    departure_time: str
    arrival_time: str
    date: str
    price: float = Field(..., gt=0)
    merchant: str = "MakeMyTrip"
    category: str = "travel"
    currency: str = "INR"

    def to_transaction_intent(self) -> TransactionIntent:
        """Convert selected flight option into authoritative TransactionIntent."""
        return TransactionIntent(
            merchant=self.merchant,
            amount=self.price,
            currency=self.currency,
            category=self.category,
            description=f"Flight booking: {self.airline} {self.flight_number} ({self.origin} → {self.destination}) on {self.date}",
            bill_id=None,
        )


class SelectedRestaurantOption(BaseModel):
    """Result from the restaurant reservation commerce tool."""
    restaurant_id: str
    restaurant_name: str
    city: str
    cuisine: str
    date: str
    time_slot: str
    party_size: int = 2
    deposit_amount: float = Field(..., gt=0)
    merchant: str
    category: str = "dining"
    currency: str = "INR"

    def to_transaction_intent(self) -> TransactionIntent:
        """Convert selected restaurant option into authoritative TransactionIntent."""
        return TransactionIntent(
            merchant=self.merchant,
            amount=self.deposit_amount,
            currency=self.currency,
            category=self.category,
            description=f"Table reservation for {self.party_size} at {self.restaurant_name} ({self.city}) on {self.date} at {self.time_slot}",
            bill_id=None,
        )


class TaskResponse(BaseModel):
    """
    Structured outcome of the task execution pipeline.
    Connects the high-level commerce option with the deterministic policy & payment outcome.
    """
    task_type: TaskType
    task_status: str = Field(..., description="COMPLETED, REJECTED_POLICY, TOOL_FAILED, PAYMENT_FAILED, INVALID_INTENT")
    success: bool = Field(..., description="True if task and payment completed successfully")
    message: str
    selected_option: Optional[Dict[str, Any]] = None
    transaction_intent: Optional[TransactionIntent] = None
    decision: str = Field(default="NONE", description="ALLOWED or DENIED by Policy Engine")
    decision_code: Optional[str] = None
    payment_status: Optional[str] = None
    payment_id: Optional[str] = None
    provider_payment_id: Optional[str] = None
    amount: Optional[float] = None
    merchant_name: Optional[str] = None
    rules_checked: Optional[List[Dict[str, Any]]] = None
    remaining_daily_budget: Optional[float] = None
    audit_trail: Optional[List[Dict[str, Any]]] = None
    already_completed: bool = False


class TaskRunRequest(BaseModel):
    """Request payload for POST /api/tasks."""
    message: str = Field(..., min_length=1, description="Natural language request or instruction")
    agent_id: Optional[UUID] = Field(default=None, description="Optional agent UUID")
    force_failure: bool = Field(default=False, description="Force payment provider decline for testing fallback")
    retry_if_failed: bool = Field(default=False, description="Enable automatic payment fallback/retry on rail failure")
    idempotency_key: Optional[str] = Field(default=None, description="Optional deterministic task idempotency key")


class TaskRunResponse(BaseModel):
    """
    Exposes the critical distinction between User Task Constraints
    and AgentPay Deterministic Financial Policy Authorization.
    """
    task_type: TaskType
    interpreted_request: Dict[str, Any] = Field(..., description="Extracted constraints: origin, destination, city, date, party_size, max_budget, etc.")
    selected_option: Optional[Dict[str, Any]] = Field(default=None, description="Deterministic option chosen by tool search")
    task_constraint_result: str = Field(..., description="PASS | FAIL | NOT_APPLICABLE")
    policy_result: str = Field(..., description="APPROVED | REJECTED | NOT_EVALUATED")
    transaction_id: Optional[str] = Field(default=None, description="ID of created payment transaction in database")
    payment_status: str = Field(..., description="SUCCESS | FAILED | NOT_ATTEMPTED | REJECTED")
    task_status: str = Field(..., description="COMPLETED | REJECTED | TOOL_FAILED | INVALID_INTENT | PAYMENT_FAILED")
    final_message: str
    rules_checked: Optional[List[Dict[str, Any]]] = None
    amount: Optional[float] = None
    merchant_name: Optional[str] = None
    audit_trail: Optional[List[Dict[str, Any]]] = None
    already_completed: bool = Field(default=False, description="True if task was already completed by a prior execution")


class TaskPrepareRequest(BaseModel):
    """Request payload for POST /api/tasks/prepare."""
    message: str = Field(..., min_length=1, description="Natural language request or instruction")
    agent_id: Optional[UUID] = Field(default=None, description="Optional agent UUID")


class TaskPrepareResponse(BaseModel):
    """Structured response for prepared task before explicit user execution."""
    task_type: TaskType
    interpreted_request: Dict[str, Any] = Field(..., description="Extracted constraints: origin, destination, city, date, party_size, max_budget, etc.")
    selected_option: Optional[Dict[str, Any]] = Field(default=None, description="Selected option from domain tool")
    idempotency_key: str = Field(..., description="Deterministic idempotency key for this task")
    already_completed: bool = Field(default=False, description="True if task already has a successful transaction")
    existing_transaction_id: Optional[str] = Field(default=None, description="Existing transaction ID if already completed")
    existing_payment_status: Optional[str] = Field(default=None, description="Status of existing payment transaction")
    estimated_amount: Optional[float] = Field(default=None, description="Target transaction amount")
    merchant_name: Optional[str] = Field(default=None, description="Target merchant or airline or restaurant")
    policy_compliant: bool = Field(default=True, description="True if within wallet and policy limits")
    summary: str = Field(..., description="Human readable summary of prepared task")


