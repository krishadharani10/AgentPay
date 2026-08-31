from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.policy import Policy
from app.schemas.policy import PolicyResponse

router = APIRouter(prefix="/api/policies", tags=["Policies"])


@router.get("", response_model=List[PolicyResponse])
def get_policies(
    agent_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
):
    """
    List all policies, optionally filtered by agent_id.
    """
    stmt = select(Policy)
    if agent_id:
        stmt = stmt.where(Policy.agent_id == agent_id)
    stmt = stmt.order_by(Policy.created_at.desc())
    policies = db.execute(stmt).scalars().all()
    return policies
