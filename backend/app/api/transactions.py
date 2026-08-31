from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionResponse

router = APIRouter(prefix="/api/transactions", tags=["Transactions"])


@router.get("", response_model=List[TransactionResponse])
def get_transactions(
    agent_id: Optional[UUID] = None,
    wallet_id: Optional[UUID] = None,
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """
    List transactions with optional filters.
    """
    stmt = select(Transaction)
    if agent_id:
        stmt = stmt.where(Transaction.agent_id == agent_id)
    if wallet_id:
        stmt = stmt.where(Transaction.wallet_id == wallet_id)
    if status:
        stmt = stmt.where(Transaction.status == status.upper())

    stmt = stmt.order_by(Transaction.created_at.desc()).limit(limit)
    transactions = db.execute(stmt).scalars().all()
    return transactions
