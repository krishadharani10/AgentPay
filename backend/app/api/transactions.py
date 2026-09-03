from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.transaction import Transaction
from app.models.payment_method import PaymentMethod
from app.models.payment_attempt import PaymentAttempt
from app.models.audit_log import AuditLog
from app.models.merchant import Merchant
from app.schemas.transaction import TransactionResponse, TransactionDetailResponse
from app.schemas.payment_attempt import PaymentAttemptResponse
from app.schemas.audit_log import AuditLogResponse

router = APIRouter(prefix="/api/transactions", tags=["Transactions"])


def _enrich_transaction(tx: Transaction, db: Session) -> dict:
    pm_type = None
    pm_alias = None
    if tx.payment_method_id:
        pm = db.get(PaymentMethod, tx.payment_method_id)
        if pm:
            pm_type = pm.type
            pm_alias = pm.token_or_alias

    return {
        "id": tx.id,
        "idempotency_key": tx.idempotency_key,
        "agent_id": tx.agent_id,
        "wallet_id": tx.wallet_id,
        "merchant_id": tx.merchant_id,
        "merchant_name": tx.merchant_name,
        "category": tx.category,
        "amount": tx.amount,
        "currency": tx.currency,
        "status": tx.status,
        "decision_reason": tx.decision_reason,
        "payment_method_id": tx.payment_method_id,
        "payment_method_type": pm_type,
        "payment_method_alias": pm_alias,
        "payment_provider": tx.payment_provider,
        "provider_payment_id": tx.provider_payment_id,
        "created_at": tx.created_at,
        "updated_at": tx.updated_at,
    }


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
    return [_enrich_transaction(tx, db) for tx in transactions]


@router.get("/{transaction_id}", response_model=TransactionDetailResponse)
def get_transaction_by_id(
    transaction_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Get full explainability details for a single transaction.
    Includes payment attempts, audit trail, and payment method details.
    Guarantees no payment secrets are exposed.
    """
    tx = db.get(Transaction, transaction_id)
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction with ID '{transaction_id}' not found.",
        )

    enriched = _enrich_transaction(tx, db)

    # Fetch and sanitize PaymentAttempts
    attempts_stmt = (
        select(PaymentAttempt)
        .where(PaymentAttempt.transaction_id == tx.id)
        .order_by(PaymentAttempt.attempt_number.asc())
    )
    attempts = db.execute(attempts_stmt).scalars().all()
    attempts_data = []
    for att in attempts:
        att_pm_type = None
        att_pm_alias = None
        if att.payment_method_id:
            att_pm = db.get(PaymentMethod, att.payment_method_id)
            if att_pm:
                att_pm_type = att_pm.type
                att_pm_alias = att_pm.token_or_alias

        attempts_data.append(
            PaymentAttemptResponse(
                id=att.id,
                transaction_id=att.transaction_id,
                payment_method_id=att.payment_method_id,
                payment_method_type=att_pm_type,
                payment_method_alias=att_pm_alias,
                attempt_number=att.attempt_number,
                status=att.status,
                provider_payment_id=att.provider_payment_id,
                error_code=att.error_code,
                error_message=att.error_message,
                response_payload=att.response_payload,
                created_at=att.created_at,
                updated_at=att.updated_at,
            )
        )

    # Fetch associated AuditLogs
    audit_stmt = (
        select(AuditLog)
        .where(AuditLog.transaction_id == tx.id)
        .order_by(AuditLog.created_at.asc())
    )
    audit_logs = db.execute(audit_stmt).scalars().all()
    audit_data = [AuditLogResponse.model_validate(log) for log in audit_logs]

    # Fetch optional merchant details
    merchant_desc = None
    merchant_web = None
    if tx.merchant_id:
        merchant = db.get(Merchant, tx.merchant_id)
        if merchant:
            merchant_desc = merchant.description
            merchant_web = merchant.website

    return TransactionDetailResponse(
        **enriched,
        payment_attempts=attempts_data,
        audit_logs=audit_data,
        merchant_description=merchant_desc,
        merchant_website=merchant_web,
    )
