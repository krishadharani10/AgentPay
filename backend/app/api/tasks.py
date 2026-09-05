"""
API router for AgentPay Autonomous Tasks (`POST /api/tasks`).

Exposes clean, structured endpoints for autonomous commerce tasks (Flight Booking,
Restaurant Reservations, and Direct Payment requests).

Highlights the critical distinction between:
- USER TASK CONSTRAINTS (evaluated by domain commerce tools)
- DETERMINISTIC FINANCIAL AUTHORIZATION (evaluated by AgentPay Policy Engine)
"""
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import get_settings, Settings
from app.schemas.task_types import (
    TaskType,
    TaskIntent,
    TaskRunRequest,
    TaskRunResponse,
    TaskPrepareRequest,
    TaskPrepareResponse,
)
from app.agents.task_orchestrator import TaskOrchestrator
from app.agents.llm_provider import MockLLMProvider
from app.services.payment_adapter import (
    get_payment_provider,
    MockPaymentProvider,
    MockPaymentMode,
)

router = APIRouter(prefix="/api/tasks", tags=["Autonomous Tasks"])


@router.post("/prepare", response_model=TaskPrepareResponse)
def prepare_autonomous_task(
    request: TaskPrepareRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TaskPrepareResponse:
    """
    Prepares an autonomous commercial task without executing payment:
    1. Parse natural-language message into structured TaskIntent
    2. Run deterministic domain tool search (flight / restaurant)
    3. Check deterministic task idempotency key against existing database transactions
    4. Provide preview details of option, merchant, estimated amount, and policy limit compliance
    """
    if not request.message or not request.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task message cannot be empty",
        )

    try:
        adapter = get_payment_provider(settings=settings)
        llm_provider = MockLLMProvider()
        orchestrator = TaskOrchestrator(adapter=adapter, llm_provider=llm_provider)
        prep_data = orchestrator.prepare_task(
            db,
            message=request.message,
            agent_id=request.agent_id,
            demo_run_id=request.demo_run_id,
        )
        return TaskPrepareResponse(**prep_data)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )


@router.post("", response_model=TaskRunResponse)
def execute_autonomous_task(
    request: TaskRunRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TaskRunResponse:
    """
    Execute a natural-language autonomous commercial task:
    1. Parse natural-language message into structured TaskIntent
    2. Run deterministic domain tool (flight search / restaurant reservation)
    3. Generate authoritative TransactionIntent
    4. Run deterministic Policy Engine evaluation
    5. Execute PaymentService if authorized
    6. Return structured response highlighting Task Constraint vs Policy Authorization
    """
    if not request.message or not request.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task message cannot be empty",
        )

    try:
        # Select adapter (or decline mode if forced)
        if request.force_failure:
            adapter = MockPaymentProvider(mode=MockPaymentMode.DECLINED)
        else:
            adapter = get_payment_provider(settings=settings)

        llm_provider = MockLLMProvider()
        task_intent: TaskIntent = llm_provider.parse_task_intent(request.message)

        orchestrator = TaskOrchestrator(adapter=adapter, llm_provider=llm_provider)
        task_result = orchestrator.execute_task(
            db,
            task_intent=task_intent,
            agent_id=request.agent_id,
            force_failure=request.force_failure,
            retry_if_failed=request.retry_if_failed,
            idempotency_key=request.idempotency_key,
            demo_run_id=request.demo_run_id,
        )

        # ── Map Task Constraint Result ──
        if task_result.task_status in ["TOOL_FAILED", "INVALID_INTENT"]:
            task_constraint_result = "FAIL"
        elif task_result.task_type == TaskType.DIRECT_PAYMENT:
            task_constraint_result = "NOT_APPLICABLE"
        else:
            task_constraint_result = "PASS"

        # ── Map Policy Result ──
        if task_result.task_status in ["TOOL_FAILED", "INVALID_INTENT"]:
            policy_result = "NOT_EVALUATED"
        elif task_result.decision == "ALLOWED":
            policy_result = "APPROVED"
        else:
            policy_result = "REJECTED"

        # ── Map Payment Status ──
        if task_result.task_status in ["TOOL_FAILED", "INVALID_INTENT"]:
            payment_status = "NOT_ATTEMPTED"
        elif task_result.task_status == "REJECTED_POLICY":
            payment_status = "NOT_ATTEMPTED"
        elif task_result.payment_status == "SUCCESS":
            payment_status = "SUCCESS"
        elif task_result.payment_status == "FAILED":
            payment_status = "FAILED"
        else:
            payment_status = task_result.payment_status or "NOT_ATTEMPTED"

        # ── Map Final Task Status ──
        if task_result.task_status == "COMPLETED":
            task_status_out = "COMPLETED"
        elif task_result.task_status == "REJECTED_POLICY":
            task_status_out = "REJECTED"
        elif task_result.task_status == "TOOL_FAILED":
            task_status_out = "TOOL_FAILED"
        elif task_result.task_status == "INVALID_INTENT":
            task_status_out = "INVALID_INTENT"
        elif task_result.task_status == "PAYMENT_FAILED":
            task_status_out = "PAYMENT_FAILED"
        else:
            task_status_out = "REJECTED"

        # Format interpreted request dict
        interpreted_dict = task_intent.model_dump(
            mode="json",
            exclude_none=True,
            exclude={"user_message", "metadata"},
        )
        if task_intent.metadata:
            interpreted_dict["metadata"] = task_intent.metadata

        return TaskRunResponse(
            task_type=task_result.task_type,
            interpreted_request=interpreted_dict,
            selected_option=task_result.selected_option,
            task_constraint_result=task_constraint_result,
            policy_result=policy_result,
            transaction_id=task_result.payment_id,
            payment_status=payment_status,
            task_status=task_status_out,
            final_message=task_result.message,
            rules_checked=task_result.rules_checked,
            amount=task_result.amount,
            merchant_name=task_result.merchant_name,
            audit_trail=task_result.audit_trail,
            already_completed=getattr(task_result, "already_completed", False),
            payment_provider=getattr(task_result, "payment_provider", None),
            order_id=getattr(task_result, "order_id", None) or getattr(task_result, "provider_payment_id", None),
            provider_payment_id=getattr(task_result, "provider_payment_id", None),
        )

    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )
