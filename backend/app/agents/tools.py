import uuid
from typing import Optional, Dict, Any, List
from sqlalchemy import select, or_, case
from sqlalchemy.orm import Session

from app.models.agent import Agent
from app.models.wallet import Wallet
from app.models.policy import Policy
from app.models.transaction import Transaction
from app.models.merchant import Merchant
from app.services.wallet_service import WalletService
from app.services.payment_adapter import PaymentAdapter
from app.services.payment_service import (
    PaymentService,
    PolicyViolationError,
    InvalidPaymentStateError,
)


def get_wallet_policy(
    db: Session,
    agent_id: Optional[uuid.UUID] = None,
) -> Dict[str, Any]:
    """
    Retrieves the current wallet and payment policy constraints for the agent.
    Exposes spending limits, categories, merchant rules, and budget metrics.
    """
    if agent_id:
        agent = db.get(Agent, agent_id)
    else:
        agent = db.execute(select(Agent).limit(1)).scalar_one_or_none()

    if not agent:
        raise ValueError("No active Agent found.")

    wallet = db.execute(select(Wallet).where(Wallet.agent_id == agent.id)).scalar_one_or_none()
    policy = db.execute(
        select(Policy).where(Policy.agent_id == agent.id, Policy.is_active == True)
    ).scalar_one_or_none()

    if not wallet or not policy:
        raise ValueError("Wallet or Policy not configured for Agent.")

    current_spent = WalletService.get_current_daily_spent(db, wallet.id)
    effective_daily_limit = min(wallet.daily_spending_limit, policy.daily_spending_limit)
    remaining_budget = max(0.0, effective_daily_limit - current_spent)

    return {
        "agent_id": str(agent.id),
        "agent_name": agent.name,
        "wallet_id": str(wallet.id),
        "wallet_status": wallet.status,
        "currency": wallet.currency,
        "per_transaction_limit": min(wallet.per_transaction_limit, policy.max_transaction_amount),
        "daily_limit": effective_daily_limit,
        "current_daily_spent": round(current_spent, 2),
        "remaining_daily_budget": round(remaining_budget, 2),
        "allowed_categories": policy.allowed_categories,
        "blocked_categories": policy.blocked_categories,
        "allowed_merchants": policy.allowed_merchants,
        "blocked_merchants": policy.blocked_merchants,
        "wallet_enabled": policy.wallet_enabled and (wallet.status.upper() == "ACTIVE"),
    }


def get_bill(
    db: Session,
    bill_id: Optional[uuid.UUID] = None,
    merchant_name: Optional[str] = None,
    query: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Retrieves a bill / payment request using the existing database transaction records.
    Supports lookup by UUID, merchant name match, or general search string.
    Prioritizes PENDING demo bills.
    """
    stmt = select(Transaction)

    if bill_id:
        stmt = stmt.where(Transaction.id == bill_id)
    elif merchant_name:
        stmt = stmt.where(Transaction.merchant_name.ilike(f"%{merchant_name.strip()}%"))
    elif query:
        clean_q = query.strip()
        stmt = stmt.where(
            or_(
                Transaction.merchant_name.ilike(f"%{clean_q}%"),
                Transaction.category.ilike(f"%{clean_q}%"),
                Transaction.idempotency_key.ilike(f"%{clean_q}%"),
                Transaction.decision_reason.ilike(f"%{clean_q}%"),
            )
        )

    # Prioritize pending/requested demo bills, then newest
    stmt = stmt.order_by(
        case((Transaction.status.in_(["PAYMENT_PENDING", "REQUESTED", "PENDING"]), 0), else_=1),
        Transaction.created_at.desc(),
    )

    tx = db.execute(stmt.limit(1)).scalar_one_or_none()
    if not tx:
        return None

    return {
        "bill_id": str(tx.id),
        "merchant_name": tx.merchant_name,
        "amount": tx.amount,
        "currency": tx.currency,
        "category": tx.category,
        "description": tx.decision_reason or f"Bill for {tx.merchant_name}",
        "status": tx.status,
        "idempotency_key": tx.idempotency_key,
        "provider_payment_id": tx.provider_payment_id,
        "created_at": tx.created_at.isoformat() if tx.created_at else None,
    }


def evaluate_payment(
    db: Session,
    payment_request: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Evaluates a payment request against the deterministic Policy Engine.
    Critical boundary: The LLM delegates authorization entirely to the engine.
    """
    merchant_name = payment_request.get("merchant_name")
    amount = float(payment_request.get("amount", 0))
    category = payment_request.get("category", "")
    agent_id_raw = payment_request.get("agent_id")
    agent_id = uuid.UUID(str(agent_id_raw)) if agent_id_raw else None
    idempotency_key = payment_request.get("idempotency_key")
    metadata = payment_request.get("metadata")

    eval_result = WalletService.evaluate_and_audit(
        db,
        merchant_name=merchant_name,
        amount=amount,
        category=category,
        agent_id=agent_id,
        idempotency_key=idempotency_key,
        metadata_payload=metadata,
    )

    # Convert rules list to simplified checks map
    checks_map = {}
    for r in eval_result.get("rules_checked", []):
        rule_key = r.get("rule", "").lower()
        checks_map[rule_key] = r.get("passed", False)

    return {
        "allowed": eval_result["approved"],
        "decision_code": eval_result["decision_code"],
        "reason": eval_result["reason"],
        "checks": checks_map,
        "remaining_daily_budget": eval_result["remaining_daily_budget"],
        "current_daily_spent": eval_result["current_daily_spent"],
        "rules_checked": eval_result["rules_checked"],
        "audit_log_id": str(eval_result["audit_log_id"]) if eval_result.get("audit_log_id") else None,
    }


def create_payment(
    db: Session,
    payment_request: Dict[str, Any],
    adapter: Optional[PaymentAdapter] = None,
) -> Dict[str, Any]:
    """
    Creates and executes a payment via the PaymentService and PaymentAdapter.
    Invariant: Policy engine is verified and enforced before adapter is invoked.
    """
    service = PaymentService(adapter=adapter)

    merchant_name = payment_request.get("merchant_name")
    amount = float(payment_request.get("amount", 0))
    category = payment_request.get("category", "")
    idempotency_key = payment_request.get("idempotency_key")
    currency = payment_request.get("currency", "INR")
    metadata = payment_request.get("metadata")

    agent_id_raw = payment_request.get("agent_id")
    agent_id = uuid.UUID(str(agent_id_raw)) if agent_id_raw else None

    bill_id_raw = payment_request.get("bill_id")
    bill_id = uuid.UUID(str(bill_id_raw)) if bill_id_raw else None

    try:
        result = service.process_payment(
            db,
            merchant_name=merchant_name,
            amount=amount,
            category=category,
            idempotency_key=idempotency_key,
            agent_id=agent_id,
            bill_id=bill_id,
            currency=currency,
            metadata=metadata,
        )
        return result
    except PolicyViolationError as pve:
        return {
            "success": False,
            "status": "REJECTED",
            "decision": "DENIED",
            "decision_code": pve.decision_code,
            "reason": pve.reason,
            "error_message": f"Payment authorization denied: {pve.reason}",
        }


def get_payment_status(
    db: Session,
    payment_id: uuid.UUID,
) -> Dict[str, Any]:
    """
    Retrieves the current status and attempt count for a payment.
    """
    service = PaymentService()
    return service.get_payment_status(db, payment_id)


def retry_payment(
    db: Session,
    payment_id: uuid.UUID,
    adapter: Optional[PaymentAdapter] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Retries an eligible failed payment. Rejects retry if already successful.
    """
    service = PaymentService(adapter=adapter)
    try:
        return service.retry_payment(db, payment_id=payment_id, metadata=metadata)
    except (InvalidPaymentStateError, PolicyViolationError) as err:
        return {
            "success": False,
            "status": "RETRY_REJECTED",
            "decision": "DENIED",
            "reason": str(err),
            "error_message": str(err),
        }


def fallback_payment(
    db: Session,
    payment_id: uuid.UUID,
    fallback_method_id: Optional[uuid.UUID] = None,
    adapter: Optional[PaymentAdapter] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Executes a policy-controlled fallback payment using a secondary PaymentMethod.
    """
    service = PaymentService(adapter=adapter)
    try:
        return service.execute_fallback_payment(
            db,
            payment_id=payment_id,
            fallback_method_id=fallback_method_id,
            metadata=metadata,
        )
    except (InvalidPaymentStateError, PolicyViolationError, ValueError) as err:
        return {
            "success": False,
            "status": "FALLBACK_REJECTED",
            "decision": "DENIED",
            "reason": str(err),
            "error_message": str(err),
        }

