from typing import List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.merchant import Merchant
from app.schemas.merchant import MerchantResponse

router = APIRouter(prefix="/api/merchants", tags=["Merchants"])


@router.get("", response_model=List[MerchantResponse])
def get_merchants(
    category: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    List registered merchants, optionally filtered by category.
    """
    stmt = select(Merchant).where(Merchant.is_active == True)
    if category:
        stmt = stmt.where(Merchant.category.ilike(category))
    stmt = stmt.order_by(Merchant.name.asc())
    merchants = db.execute(stmt).scalars().all()
    return merchants
