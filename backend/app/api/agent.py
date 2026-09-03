from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.agent import AgentRunRequest, AgentRunResponse
from app.agents.orchestrator import AgentOrchestrator
from app.services.payment_adapter import get_payment_provider, MockPaymentProvider, MockPaymentMode

router = APIRouter(prefix="/api/agent", tags=["AI Agent"])


@router.post("/run", response_model=AgentRunResponse)
def run_agent(
    request: AgentRunRequest,
    db: Session = Depends(get_db),
):
    """
    Run Agent Orchestrator to process a user payment request.
    Orchestrates tools (get_bill, get_wallet_policy, evaluate_payment, create_payment).
    Guaranteed: Policy engine determines authorization deterministically.
    Provider is selected via PAYMENT_PROVIDER environment variable.
    """
    try:
        # Select provider via factory; if force_failure, override to Mock DECLINED mode
        if request.force_failure:
            adapter = MockPaymentProvider(mode=MockPaymentMode.DECLINED)
        else:
            adapter = get_payment_provider()
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

