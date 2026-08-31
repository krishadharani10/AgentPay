from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.policy import PolicyEvaluateRequest, PolicyEvaluateResponse
from app.services.wallet_service import WalletService

router = APIRouter(prefix="/api/policy", tags=["Policy Engine"])


@router.post("/evaluate", response_model=PolicyEvaluateResponse)
def evaluate_policy(
    request: PolicyEvaluateRequest,
    db: Session = Depends(get_db),
):
    """
    Deterministically evaluate a payment request against agent, wallet, and policy rules.
    Records an immutable AuditLog entry in PostgreSQL for every evaluation attempt.
    """
    try:
        result = WalletService.evaluate_and_audit(
            db,
            merchant_name=request.merchant_name,
            amount=request.amount,
            category=request.category,
            agent_id=request.agent_id,
            idempotency_key=request.idempotency_key,
            metadata_payload=request.metadata,
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
