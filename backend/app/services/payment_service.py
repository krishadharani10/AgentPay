import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent import Agent
from app.models.wallet import Wallet
from app.models.policy import Policy
from app.models.merchant import Merchant
from app.models.payment_method import PaymentMethod
from app.models.transaction import Transaction
from app.models.audit_log import AuditLog
from app.services.wallet_service import WalletService
from app.services.payment_adapter import (
    PaymentProvider,
    MockPaymentProvider,
    PaymentExecutionRequest,
    PaymentExecutionResult,
)


class PolicyViolationError(Exception):
    """Raised when a payment operation violates policy rules."""
    def __init__(self, reason: str, decision_code: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(reason)
        self.reason = reason
        self.decision_code = decision_code
        self.details = details or {}


class InvalidPaymentStateError(Exception):
    """Raised when an operation is invalid for current payment state (e.g. retrying a successful payment)."""
    pass


class PaymentService:
    """
    Core Payment Management Service.
    Enforces the security boundary that all payments MUST pass through the Policy Engine
    prior to any payment provider dispatch.
    """

    def __init__(
        self,
        provider: Optional[PaymentProvider] = None,
        adapter: Optional[PaymentProvider] = None,
    ):
        self.provider = provider or adapter or MockPaymentProvider()

    @property
    def adapter(self) -> PaymentProvider:
        """Backward-compatible property alias."""
        return self.provider

    @adapter.setter
    def adapter(self, value: PaymentProvider) -> None:
        self.provider = value

    def process_payment(
        self,
        db: Session,
        *,
        merchant_name: str,
        amount: float,
        category: str,
        idempotency_key: Optional[str] = None,
        agent_id: Optional[uuid.UUID] = None,
        bill_id: Optional[uuid.UUID] = None,
        currency: str = "INR",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Processes a payment with mandatory deterministic policy evaluation.
        Invariant: If policy rejects the payment, the payment provider is NEVER called.
        """
        # Resolve Agent
        if agent_id:
            agent = db.get(Agent, agent_id)
        else:
            agent = db.execute(select(Agent).limit(1)).scalar_one_or_none()

        if not agent:
            raise ValueError("No active Agent found.")

        # Resolve Wallet & Active Payment Method
        wallet = db.execute(select(Wallet).where(Wallet.agent_id == agent.id)).scalar_one_or_none()
        if not wallet:
            raise ValueError("No Wallet associated with Agent.")

        primary_pm = db.execute(
            select(PaymentMethod).where(PaymentMethod.wallet_id == wallet.id, PaymentMethod.is_primary == True)
        ).scalar_one_or_none()
        pm_alias = primary_pm.token_or_alias if primary_pm else "mock_default_vpa"
        pm_id = primary_pm.id if primary_pm else None

        # Check for existing transaction if bill_id or idempotency_key provided
        key = idempotency_key or f"tx_{uuid.uuid4().hex[:16]}"
        existing_tx = None
        if bill_id:
            existing_tx = db.get(Transaction, bill_id)
        if not existing_tx and idempotency_key:
            existing_tx = db.execute(
                select(Transaction).where(Transaction.idempotency_key == idempotency_key)
            ).scalar_one_or_none()

        if existing_tx and existing_tx.status == "SUCCESS":
            return {
                "success": True,
                "status": "SUCCESS",
                "payment_id": str(existing_tx.id),
                "provider_payment_id": existing_tx.provider_payment_id,
                "amount": existing_tx.amount,
                "currency": existing_tx.currency,
                "merchant_name": existing_tx.merchant_name,
                "decision": "ALLOWED",
                "decision_reason": "Payment was already completed successfully (idempotent response).",
                "attempt_number": 1,
            }

        # 1. MANDATORY POLICY EVALUATION (Zero LLM involvement)
        eval_result = WalletService.evaluate_and_audit(
            db,
            merchant_name=merchant_name,
            amount=amount,
            category=category,
            agent_id=agent.id,
            idempotency_key=key,
            metadata_payload=metadata,
        )

        if not eval_result["approved"]:
            # Record/Update transaction as REJECTED in database
            tx_record = existing_tx or Transaction(
                id=uuid.uuid4(),
                idempotency_key=key,
                agent_id=agent.id,
                wallet_id=wallet.id,
                merchant_name=merchant_name,
                category=category,
                amount=amount,
                currency=currency,
                status="REJECTED",
                decision_reason=eval_result["reason"],
                payment_method_id=pm_id,
                payment_provider=self.provider.__class__.__name__,
            )
            if not existing_tx:
                db.add(tx_record)
            else:
                tx_record.status = "REJECTED"
                tx_record.decision_reason = eval_result["reason"]
            db.commit()

            # INVARIANT: Do NOT invoke payment provider!
            raise PolicyViolationError(
                reason=eval_result["reason"],
                decision_code=eval_result["decision_code"],
                details=eval_result,
            )

        # 2. INITIATE TRANSACTION RECORD
        if not existing_tx:
            tx_record = Transaction(
                id=uuid.uuid4(),
                idempotency_key=key,
                agent_id=agent.id,
                wallet_id=wallet.id,
                merchant_name=merchant_name,
                category=category,
                amount=amount,
                currency=currency,
                status="PENDING",
                decision_reason=eval_result["reason"],
                payment_method_id=pm_id,
                payment_provider="mock",
            )
            db.add(tx_record)
            db.flush()
        else:
            tx_record = existing_tx
            tx_record.status = "PENDING"
            db.flush()

        # Audit attempt
        audit_attempt = AuditLog(
            agent_id=agent.id,
            transaction_id=tx_record.id,
            event_type="PAYMENT_ATTEMPT",
            action="EXECUTE_PAYMENT",
            decision="PROCESSING",
            reason=f"Initiating payment execution via {self.provider.__class__.__name__}",
            metadata_payload={"amount": amount, "merchant_name": merchant_name, "attempt": 1},
        )
        db.add(audit_attempt)
        db.commit()

        # 3. DISPATCH TO PAYMENT PROVIDER
        exec_request = PaymentExecutionRequest(
            transaction_id=str(tx_record.id),
            idempotency_key=tx_record.idempotency_key,
            amount=tx_record.amount,
            currency=tx_record.currency,
            merchant_name=tx_record.merchant_name,
            category=tx_record.category,
            attempt_number=1,
            payment_method_alias=pm_alias,
            metadata=metadata,
        )
        provider_result: PaymentExecutionResult = self.provider.create_payment(exec_request)

        # 4. PERSIST PAYMENT RESULT
        tx_record.status = provider_result.status
        tx_record.provider_payment_id = provider_result.provider_payment_id
        if not provider_result.success:
            tx_record.decision_reason = f"Payment Gateway Error: {provider_result.error_message}"

        audit_result = AuditLog(
            agent_id=agent.id,
            transaction_id=tx_record.id,
            event_type="PAYMENT_RESULT",
            action="EXECUTE_PAYMENT",
            decision=provider_result.status,
            reason=provider_result.error_message or "Payment processed successfully.",
            metadata_payload={
                "provider_payment_id": provider_result.provider_payment_id,
                "attempt_number": provider_result.attempt_number,
                "success": provider_result.success,
            },
        )
        db.add(audit_result)
        db.commit()
        db.refresh(tx_record)

        return {
            "success": provider_result.success,
            "status": provider_result.status,
            "payment_id": str(tx_record.id),
            "provider_payment_id": provider_result.provider_payment_id,
            "amount": tx_record.amount,
            "currency": tx_record.currency,
            "merchant_name": tx_record.merchant_name,
            "category": tx_record.category,
            "attempt_number": provider_result.attempt_number,
            "decision": "ALLOWED",
            "decision_reason": eval_result["reason"],
            "error_message": provider_result.error_message,
        }

    def retry_payment(
        self,
        db: Session,
        *,
        payment_id: uuid.UUID,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Safely retries a failed or timed-out payment.
        Guards:
        - Rejects retry if status is already SUCCESS.
        - Re-checks policy engine before retry execution.
        """
        tx = db.get(Transaction, payment_id)
        if not tx:
            raise ValueError(f"Transaction with ID {payment_id} not found.")

        if tx.status == "SUCCESS":
            raise InvalidPaymentStateError(
                f"Cannot retry transaction {payment_id}: payment was already completed successfully."
            )

        if tx.status not in ["FAILED", "TIMEOUT", "REJECTED", "PENDING"]:
            raise InvalidPaymentStateError(
                f"Cannot retry transaction {payment_id} with current status '{tx.status}'."
            )

        # Get Agent & Wallet
        agent = db.get(Agent, tx.agent_id)
        wallet = db.get(Wallet, tx.wallet_id)
        primary_pm = db.execute(
            select(PaymentMethod).where(PaymentMethod.wallet_id == wallet.id, PaymentMethod.is_primary == True)
        ).scalar_one_or_none()
        pm_alias = primary_pm.token_or_alias if primary_pm else "mock_default_vpa"

        # Calculate attempt number from audit logs
        attempt_count = db.execute(
            select(AuditLog).where(
                AuditLog.transaction_id == tx.id,
                AuditLog.event_type.in_(["PAYMENT_ATTEMPT", "PAYMENT_RETRY"]),
            )
        ).scalars().all()
        next_attempt = len(attempt_count) + 1

        # Re-evaluate policy for retry
        eval_result = WalletService.evaluate_and_audit(
            db,
            merchant_name=tx.merchant_name,
            amount=tx.amount,
            category=tx.category,
            agent_id=agent.id,
            idempotency_key=f"{tx.idempotency_key}_retry_{next_attempt}",
            metadata_payload=metadata,
        )

        if not eval_result["approved"]:
            tx.status = "REJECTED"
            tx.decision_reason = f"Retry blocked by policy: {eval_result['reason']}"
            db.commit()
            raise PolicyViolationError(
                reason=eval_result["reason"],
                decision_code=eval_result["decision_code"],
                details=eval_result,
            )

        # Audit Retry Attempt
        audit_retry = AuditLog(
            agent_id=agent.id,
            transaction_id=tx.id,
            event_type="PAYMENT_RETRY",
            action="RETRY_PAYMENT",
            decision="PROCESSING",
            reason=f"Initiating retry attempt #{next_attempt}",
            metadata_payload={"attempt": next_attempt},
        )
        db.add(audit_retry)
        db.commit()

        # Dispatch Retry to Provider
        exec_request = PaymentExecutionRequest(
            transaction_id=str(tx.id),
            idempotency_key=tx.idempotency_key,
            amount=tx.amount,
            currency=tx.currency,
            merchant_name=tx.merchant_name,
            category=tx.category,
            attempt_number=next_attempt,
            payment_method_alias=pm_alias,
            metadata=metadata,
        )
        provider_result = self.provider.retry(exec_request)

        # Update Transaction
        tx.status = provider_result.status
        tx.provider_payment_id = provider_result.provider_payment_id
        if not provider_result.success:
            tx.decision_reason = f"Retry Failed: {provider_result.error_message}"
        else:
            tx.decision_reason = f"Payment succeeded on attempt #{next_attempt}"

        audit_result = AuditLog(
            agent_id=agent.id,
            transaction_id=tx.id,
            event_type="PAYMENT_RESULT",
            action="RETRY_PAYMENT",
            decision=provider_result.status,
            reason=provider_result.error_message or f"Retry attempt #{next_attempt} succeeded.",
            metadata_payload={
                "provider_payment_id": provider_result.provider_payment_id,
                "attempt_number": provider_result.attempt_number,
                "success": provider_result.success,
            },
        )
        db.add(audit_result)
        db.commit()
        db.refresh(tx)

        return {
            "success": provider_result.success,
            "status": provider_result.status,
            "payment_id": str(tx.id),
            "provider_payment_id": provider_result.provider_payment_id,
            "amount": tx.amount,
            "currency": tx.currency,
            "merchant_name": tx.merchant_name,
            "attempt_number": provider_result.attempt_number,
            "decision": "ALLOWED",
            "decision_reason": tx.decision_reason,
            "error_message": provider_result.error_message,
        }

    def get_payment_status(self, db: Session, payment_id: uuid.UUID) -> Dict[str, Any]:
        """Retrieves structured payment status from database."""
        tx = db.get(Transaction, payment_id)
        if not tx:
            raise ValueError(f"Transaction with ID {payment_id} not found.")

        # Count total attempts from audit log
        attempts = db.execute(
            select(AuditLog).where(
                AuditLog.transaction_id == tx.id,
                AuditLog.event_type.in_(["PAYMENT_ATTEMPT", "PAYMENT_RETRY"]),
            )
        ).scalars().all()
        attempt_count = max(1, len(attempts))

        return {
            "payment_id": str(tx.id),
            "idempotency_key": tx.idempotency_key,
            "status": tx.status,
            "amount": tx.amount,
            "currency": tx.currency,
            "merchant_name": tx.merchant_name,
            "category": tx.category,
            "decision_reason": tx.decision_reason,
            "provider_payment_id": tx.provider_payment_id,
            "payment_provider": tx.payment_provider,
            "attempt": attempt_count,
            "created_at": tx.created_at,
            "updated_at": tx.updated_at,
        }
