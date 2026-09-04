from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.wallet import Wallet
from app.models.agent import Agent
from app.schemas.wallet import WalletSummaryResponse
from app.services.wallet_service import WalletService

router = APIRouter(prefix="/api/wallet", tags=["Wallet"])


@router.get("", response_model=WalletSummaryResponse)
def get_wallet(
    agent_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
):
    """
    Get wallet details, payment methods, current daily spent, and remaining daily budget.
    """
    if agent_id:
        agent = db.get(Agent, agent_id)
    else:
        agent = db.execute(select(Agent).limit(1)).scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Agent configured in the system.",
        )

    wallet = db.execute(
        select(Wallet).where(Wallet.agent_id == agent.id)
    ).scalar_one_or_none()

    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Wallet found for the agent.",
        )

    current_daily_spent = WalletService.get_current_daily_spent(db, wallet.id)
    remaining_daily_budget = max(0.0, wallet.daily_spending_limit - current_daily_spent)

    return {
        "id": wallet.id,
        "agent_id": wallet.agent_id,
        "status": wallet.status,
        "daily_spending_limit": wallet.daily_spending_limit,
        "per_transaction_limit": wallet.per_transaction_limit,
        "currency": wallet.currency,
        "payment_methods": wallet.payment_methods,
        "created_at": wallet.created_at,
        "updated_at": wallet.updated_at,
        "current_daily_spent": round(current_daily_spent, 2),
        "remaining_daily_budget": round(remaining_daily_budget, 2),
    }


@router.post("/reset-daily-spend", response_model=WalletSummaryResponse)
def reset_wallet_daily_spend(
    agent_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
):
    """
    Renew / reset the daily spending amount for testing purposes.
    Allows re-running authorized payments without hitting daily spending limit ceilings.
    """
    if agent_id:
        agent = db.get(Agent, agent_id)
    else:
        agent = db.execute(select(Agent).limit(1)).scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Agent configured in the system.",
        )

    wallet = db.execute(
        select(Wallet).where(Wallet.agent_id == agent.id)
    ).scalar_one_or_none()

    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Wallet found for the agent.",
        )

    WalletService.reset_daily_spent(db, wallet.id)
    current_daily_spent = WalletService.get_current_daily_spent(db, wallet.id)
    remaining_daily_budget = max(0.0, wallet.daily_spending_limit - current_daily_spent)

    return {
        "id": wallet.id,
        "agent_id": wallet.agent_id,
        "status": wallet.status,
        "daily_spending_limit": wallet.daily_spending_limit,
        "per_transaction_limit": wallet.per_transaction_limit,
        "currency": wallet.currency,
        "payment_methods": wallet.payment_methods,
        "created_at": wallet.created_at,
        "updated_at": wallet.updated_at,
        "current_daily_spent": round(current_daily_spent, 2),
        "remaining_daily_budget": round(remaining_daily_budget, 2),
    }
