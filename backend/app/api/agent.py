from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.agent import AgentRunRequest, AgentRunResponse
from app.schemas.task_types import TaskIntent, TaskResponse
from app.agents.orchestrator import AgentOrchestrator
from app.agents.task_orchestrator import TaskOrchestrator
from app.services.payment_adapter import get_payment_provider, MockPaymentProvider, MockPaymentMode

router = APIRouter(prefix="/api/agent", tags=["AI Agent"])


@router.post("/run", response_model=AgentRunResponse)
def run_agent(
    request: AgentRunRequest,
    db: Session = Depends(get_db),
):
    """
    Run Agent Orchestrator to process a user payment or autonomous commerce request.
    Orchestrates tools (flight search, restaurant reservation, bill lookup, policy evaluation, payment execution).
    Guaranteed: Policy engine determines authorization deterministically.
    """
    try:
        # Select provider via factory; if force_failure, override to Mock DECLINED mode
        if request.force_failure:
            adapter = MockPaymentProvider(mode=MockPaymentMode.DECLINED)
        else:
            adapter = get_payment_provider()

        # Check if natural language request is an autonomous commerce task (flight/restaurant)
        msg_lower = request.message.lower()
        is_commerce_task = any(
            w in msg_lower
            for w in [
                "flight", "fly", "plane", "airline", "book ticket",
                "restaurant", "table", "reserve table", "reservation",
                "dinner", "lunch", "bukhara", "trishna", "gajalee", "karavalli"
            ]
        )

        if is_commerce_task and not request.bill_id:
            task_orchestrator = TaskOrchestrator(adapter=adapter)
            task_result = task_orchestrator.process_natural_language(
                db,
                message=request.message,
                agent_id=request.agent_id,
                force_failure=request.force_failure,
                retry_if_failed=request.retry_if_failed,
            )
            return AgentRunResponse(
                success=task_result.success,
                decision=task_result.decision,
                decision_code=task_result.decision_code or "PROCESSED",
                message=task_result.message,
                payment_id=task_result.payment_id,
                provider_payment_id=task_result.provider_payment_id,
                payment_status=task_result.payment_status,
                amount=task_result.amount,
                merchant_name=task_result.merchant_name,
                rules_checked=task_result.rules_checked,
                remaining_daily_budget=task_result.remaining_daily_budget,
                audit_trail=task_result.audit_trail,
            )

        orchestrator = AgentOrchestrator(adapter=adapter)
        result = orchestrator.process_request(
            db,
            message=request.message,
            agent_id=request.agent_id,
            bill_id=request.bill_id,
            merchant_name=request.merchant_name,
            amount=request.amount,
            category=request.category,
            force_failure=request.force_failure,
            retry_if_failed=request.retry_if_failed,
        )
        return result
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )


@router.post("/task", response_model=TaskResponse)
def execute_task(
    intent: TaskIntent,
    force_failure: bool = False,
    retry_if_failed: bool = False,
    db: Session = Depends(get_db),
):
    """
    Direct endpoint for autonomous commerce tasks (DIRECT_PAYMENT, BOOK_FLIGHT, RESERVE_RESTAURANT).
    Executes domain commerce tool, translates to TransactionIntent, and processes through Policy Engine.
    """
    try:
        if force_failure:
            adapter = MockPaymentProvider(mode=MockPaymentMode.DECLINED)
        else:
            adapter = get_payment_provider()

        orchestrator = TaskOrchestrator(adapter=adapter)
        return orchestrator.execute_task(
            db,
            task_intent=intent,
            force_failure=force_failure,
            retry_if_failed=retry_if_failed,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )
