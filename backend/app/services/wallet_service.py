import uuid
from datetime import datetime, timezone, time
from typing import Optional, Dict, Any, List
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.agent import Agent
from app.models.wallet import Wallet
from app.models.policy import Policy
from app.models.transaction import Transaction
from app.models.audit_log import AuditLog
from app.models.merchant import Merchant
from app.policies.engine import PolicyEngine, PolicyDecision


class WalletService:
    @staticmethod
    def get_current_daily_spent(db: Session, wallet_id: uuid.UUID) -> float:
        """Calculate total amount spent by the wallet during the current UTC calendar day."""
        now = datetime.now(timezone.utc)
        start_of_day = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)

        stmt = select(func.coalesce(func.sum(Transaction.amount), 0.0)).where(
            Transaction.wallet_id == wallet_id,
            Transaction.status.in_(["SUCCESS", "APPROVED"]),
            Transaction.created_at >= start_of_day,
        )
        total_spent = db.execute(stmt).scalar_one_or_none() or 0.0
        return float(total_spent)

    @staticmethod
    def get_or_create_default_context(db: Session) -> Dict[str, Any]:
        """Fetch default agent, wallet, and active policy for demo scenarios."""
        agent = db.execute(select(Agent).limit(1)).scalar_one_or_none()
        if not agent:
            return {}

        wallet = db.execute(select(Wallet).where(Wallet.agent_id == agent.id)).scalar_one_or_none()
        policy = db.execute(
            select(Policy).where(Policy.agent_id == agent.id, Policy.is_active == True)
        ).scalar_one_or_none()

        return {
            "agent": agent,
            "wallet": wallet,
            "policy": policy,
        }

    @staticmethod
    def evaluate_and_audit(
        db: Session,
        *,
        merchant_name: str,
        amount: float,
        category: str,
        agent_id: Optional[uuid.UUID] = None,
        idempotency_key: Optional[str] = None,
        metadata_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate policy using PolicyEngine and record immutable AuditLog entry in database.
        """
        # Resolve Agent
        if agent_id:
            agent = db.get(Agent, agent_id)
        else:
            agent = db.execute(select(Agent).limit(1)).scalar_one_or_none()

        if not agent:
            raise ValueError("No active Agent found in the system.")

        # Resolve Wallet & Active Policy
        wallet = db.execute(select(Wallet).where(Wallet.agent_id == agent.id)).scalar_one_or_none()
        policy = db.execute(
            select(Policy).where(Policy.agent_id == agent.id, Policy.is_active == True)
        ).scalar_one_or_none()

        wallet_status = wallet.status if wallet else "DISABLED"
        wallet_per_tx = wallet.per_transaction_limit if wallet else 0.0
        wallet_daily = wallet.daily_spending_limit if wallet else 0.0

        policy_wallet_enabled = policy.wallet_enabled if policy else False
        policy_max_tx = policy.max_transaction_amount if policy else 0.0
        policy_daily = policy.daily_spending_limit if policy else 0.0
        allowed_cats = policy.allowed_categories if policy else []
        blocked_cats = policy.blocked_categories if policy else []
        allowed_merchs = policy.allowed_merchants if policy else []
        blocked_merchs = policy.blocked_merchants if policy else []

        current_daily_spent = 0.0
        if wallet:
            current_daily_spent = WalletService.get_current_daily_spent(db, wallet.id)

        # Run Deterministic Policy Engine
        decision: PolicyDecision = PolicyEngine.evaluate(
            amount=amount,
            category=category,
            merchant_name=merchant_name,
            current_daily_spent=current_daily_spent,
            wallet_status=wallet_status,
            wallet_per_tx_limit=wallet_per_tx,
            wallet_daily_limit=wallet_daily,
            policy_wallet_enabled=policy_wallet_enabled,
            policy_max_tx_amount=policy_max_tx,
            policy_daily_limit=policy_daily,
            allowed_categories=allowed_cats,
            blocked_categories=blocked_cats,
            allowed_merchants=allowed_merchs,
            blocked_merchants=blocked_merchs,
        )

        # Audit Log Entry - Immutable record of evaluation
        audit_meta = {
            "merchant_name": merchant_name,
            "amount": amount,
            "category": category,
            "wallet_id": str(wallet.id) if wallet else None,
            "policy_id": str(policy.id) if policy else None,
            "idempotency_key": idempotency_key,
            **(metadata_payload or {}),
        }

        audit_entry = AuditLog(
            agent_id=agent.id,
            transaction_id=None,
            event_type="POLICY_EVALUATION",
            action="EVALUATE_POLICY",
            decision="APPROVED" if decision.approved else "REJECTED",
            reason=decision.reason,
            rules_checked=decision.rules_checked,
            metadata_payload=audit_meta,
        )
        db.add(audit_entry)
        db.commit()
        db.refresh(audit_entry)

        return {
            "approved": decision.approved,
            "decision_code": decision.decision_code,
            "reason": decision.reason,
            "rules_checked": decision.rules_checked,
            "remaining_daily_budget": decision.remaining_daily_budget,
            "current_daily_spent": decision.current_daily_spent,
            "audit_log_id": audit_entry.id,
        }
