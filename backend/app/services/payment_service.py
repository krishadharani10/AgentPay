import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent import Agent
from app.models.wallet import Wallet
from app.models.policy import Policy
from app.models.merchant import Merchant
from app.models.payment_method import PaymentMethod
from app.models.transaction import (
    Transaction,
    TransactionStatus,
    InvalidPaymentStateError,
    MaxRetriesExceededError,
    validate_transition,
)
from app.models.payment_attempt import PaymentAttempt
from app.models.audit_log import AuditLog
from app.services.wallet_service import WalletService
from app.services.payment_adapter import (
    PaymentProvider,
    MockPaymentProvider,
    PaymentFailureReason,
    PaymentExecutionRequest,
    PaymentExecutionResult,
    get_payment_provider,
)

# Authoritative Retry & Fallback Constraint: Maximum secondary attempts permitted after the initial attempt.
# Total allowed provider attempts for a transaction = MAX_RETRIES + 1 (i.e. attempt #1 primary + attempt #2 retry/fallback = 2 total)
MAX_RETRIES: int = 1


class PolicyViolationError(Exception):
    """Raised when a payment operation violates policy rules."""
    def __init__(self, reason: str, decision_code: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(reason)
        self.reason = reason
        self.decision_code = decision_code
        self.details = details or {}


class PaymentService:
    """
    Core Payment Management Service.
    Enforces the security boundary that all payments MUST pass through the Policy Engine
    prior to any payment provider dispatch, with strict transaction state machine guards,
    MAX_RETRIES = 1 enforcement, persistent PaymentAttempt recording, and policy-controlled fallback.
    """

    def __init__(
        self,
        provider: Optional[PaymentProvider] = None,
        adapter: Optional[PaymentProvider] = None,
    ):
        self.provider = provider or adapter or get_payment_provider()

    @property
    def adapter(self) -> PaymentProvider:
        """Backward-compatible property alias."""
        return self.provider

    @adapter.setter
    def adapter(self, value: PaymentProvider) -> None:
        self.provider = value

    def get_fallback_payment_method(
        self,
        db: Session,
        wallet_id: uuid.UUID,
        custom_fallback_id: Optional[uuid.UUID] = None,
    ) -> Optional[PaymentMethod]:
        """
        Retrieves and validates a fallback PaymentMethod for a wallet.
        Enforces cross-wallet and active-status security guards.
        """
        if custom_fallback_id:
            pm = db.get(PaymentMethod, custom_fallback_id)
            if not pm:
                raise ValueError(f"PaymentMethod with ID {custom_fallback_id} not found.")
            if pm.wallet_id != wallet_id:
                raise PolicyViolationError(
                    reason="Unauthorized payment method: does not belong to the transaction wallet.",
                    decision_code="UNAUTHORIZED_PAYMENT_METHOD",
                )
            if not pm.is_active:
                raise InvalidPaymentStateError(
                    f"Payment method {custom_fallback_id} ({pm.type}) is inactive and cannot be used for fallback."
                )
            return pm

        # Query secondary payment method by priority for this wallet
        fallback_pm = db.execute(
            select(PaymentMethod)
            .where(
                PaymentMethod.wallet_id == wallet_id,
                PaymentMethod.is_primary == False,
                PaymentMethod.is_active == True,
            )
            .order_by(PaymentMethod.priority.asc())
        ).scalars().first()

        return fallback_pm

    def check_retry_eligibility(
        self,
        db: Session,
        payment_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Authoritative centralized retry/fallback eligibility check.
        Uses persisted PaymentAttempt records in the database as the sole source of truth.
        """
        tx = db.get(Transaction, payment_id)
        if not tx:
            raise ValueError(f"Transaction with ID {payment_id} not found.")

        # Invariant 1: Successful transactions can never be retried or fallback
        if tx.status == TransactionStatus.SUCCESS.value:
            raise InvalidPaymentStateError(
                f"Cannot retry transaction {payment_id}: payment was already completed successfully."
            )

        # Invariant 2: Policy-rejected transactions can never be retried
        if tx.status == TransactionStatus.REJECTED.value:
            raise InvalidPaymentStateError(
                f"Cannot retry transaction {payment_id}: transaction was REJECTED by policy."
            )

        # Invariant 3: Transaction must be in FAILED state
        if tx.status != TransactionStatus.FAILED.value:
            raise InvalidPaymentStateError(
                f"Cannot retry transaction {payment_id} with current status '{tx.status}'. Must be FAILED."
            )

        # Invariant 4: Source of truth is persisted PaymentAttempt records
        attempts = db.execute(
            select(PaymentAttempt)
            .where(PaymentAttempt.transaction_id == tx.id)
            .order_by(PaymentAttempt.attempt_number.asc())
        ).scalars().all()

        total_attempts = len(attempts)

        # Check retry limit: MAX_RETRIES = 1 means max total attempts = 2
        max_total_attempts = MAX_RETRIES + 1
        if total_attempts >= max_total_attempts:
            raise MaxRetriesExceededError(
                f"Cannot retry transaction {payment_id}: retry limit reached. "
                f"Attempted {total_attempts} of {max_total_attempts} maximum allowed attempts (MAX_RETRIES={MAX_RETRIES})."
            )

        if total_attempts == 0:
            raise InvalidPaymentStateError(
                f"Cannot retry transaction {payment_id}: no initial payment attempt exists."
            )

        # Invariant 5: The previous attempt must have a failure result
        last_attempt = attempts[-1]
        if last_attempt.status == "SUCCESS":
            raise InvalidPaymentStateError(
                f"Cannot retry transaction {payment_id}: previous attempt #{last_attempt.attempt_number} was successful."
            )

        return {
            "eligible": True,
            "transaction": tx,
            "current_attempts": total_attempts,
            "next_attempt_number": total_attempts + 1,
            "last_failure_reason": last_attempt.error_code,
        }

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
        enable_auto_fallback: bool = False,
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

        # Resolve Wallet & Active Primary Payment Method
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

        if existing_tx:
            existing_attempts = db.execute(
                select(PaymentAttempt)
                .where(PaymentAttempt.transaction_id == existing_tx.id)
                .order_by(PaymentAttempt.attempt_number.asc())
            ).scalars().all()

            # CASE 2 & 3: Already completed with SUCCESS (primary or fallback)
            if existing_tx.status == TransactionStatus.SUCCESS.value:
                last_att_num = existing_attempts[-1].attempt_number if existing_attempts else 1
                return {
                    "success": True,
                    "status": TransactionStatus.SUCCESS.value,
                    "payment_id": str(existing_tx.id),
                    "provider_payment_id": existing_tx.provider_payment_id,
                    "amount": existing_tx.amount,
                    "currency": existing_tx.currency,
                    "merchant_name": existing_tx.merchant_name,
                    "category": existing_tx.category,
                    "decision": "ALLOWED",
                    "decision_reason": existing_tx.decision_reason or "Payment was already completed successfully (idempotent response).",
                    "attempt_number": last_att_num,
                    "failure_reason": None,
                }

            # CASE 4: Already REJECTED by policy
            if existing_tx.status == TransactionStatus.REJECTED.value:
                raise PolicyViolationError(
                    reason=existing_tx.decision_reason or "Transaction was previously rejected by policy.",
                    decision_code="PREVIOUSLY_REJECTED",
                    details={"idempotent_replay": True, "transaction_id": str(existing_tx.id)},
                )

            # Previously FAILED with executed provider attempts (duplicate initial request replay)
            if existing_tx.status == TransactionStatus.FAILED.value and len(existing_attempts) > 0:
                last_att = existing_attempts[-1]
                return {
                    "success": False,
                    "status": TransactionStatus.FAILED.value,
                    "payment_id": str(existing_tx.id),
                    "provider_payment_id": existing_tx.provider_payment_id or last_att.provider_payment_id,
                    "amount": existing_tx.amount,
                    "currency": existing_tx.currency,
                    "merchant_name": existing_tx.merchant_name,
                    "category": existing_tx.category,
                    "attempt_number": last_att.attempt_number,
                    "decision": "ALLOWED",
                    "decision_reason": existing_tx.decision_reason,
                    "failure_reason": last_att.error_code,
                    "error_code": last_att.error_code,
                    "error_message": last_att.error_message or existing_tx.decision_reason,
                }

        # 0. RESOLVE OR INITIALIZE TRANSACTION IN REQUESTED STATE
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
                status=TransactionStatus.REQUESTED.value,
                payment_method_id=pm_id,
                payment_provider=self.provider.__class__.__name__,
            )
            db.add(tx_record)
            db.flush()
        else:
            tx_record = existing_tx

        # 1. TRANSITION TO POLICY_CHECK
        if tx_record.status == TransactionStatus.REQUESTED.value:
            tx_record.transition_to(TransactionStatus.POLICY_CHECK)
            db.flush()
        elif tx_record.status == TransactionStatus.PAYMENT_PENDING.value:
            # Seeded demo bill in PAYMENT_PENDING state
            pass

        # 2. MANDATORY POLICY EVALUATION (Zero LLM involvement)
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
            # Record/Update transaction as REJECTED in database via state machine
            tx_record.decision_reason = eval_result["reason"]
            tx_record.payment_provider = self.provider.__class__.__name__
            if tx_record.status == TransactionStatus.REQUESTED.value:
                tx_record.transition_to(TransactionStatus.POLICY_CHECK)
            if tx_record.status == TransactionStatus.POLICY_CHECK.value:
                tx_record.transition_to(TransactionStatus.REJECTED)
            else:
                # If seeded bill was in PAYMENT_PENDING
                tx_record.status = TransactionStatus.REJECTED.value
            db.commit()

            # INVARIANT: Do NOT invoke payment provider!
            raise PolicyViolationError(
                reason=eval_result["reason"],
                decision_code=eval_result["decision_code"],
                details=eval_result,
            )

        # 3. POLICY APPROVED: ADVANCE STATE (POLICY_CHECK -> APPROVED -> PAYMENT_PENDING)
        tx_record.decision_reason = eval_result["reason"]
        if tx_record.status == TransactionStatus.POLICY_CHECK.value:
            tx_record.transition_to(TransactionStatus.APPROVED)
            tx_record.transition_to(TransactionStatus.PAYMENT_PENDING)
        elif tx_record.status == TransactionStatus.APPROVED.value:
            tx_record.transition_to(TransactionStatus.PAYMENT_PENDING)
        elif tx_record.status == TransactionStatus.FAILED.value:
            tx_record.transition_to(TransactionStatus.PAYMENT_PENDING, allow_retry=True)
        db.flush()

        # Determine attempt number for this payment execution from DB
        existing_attempts = db.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == tx_record.id)
        ).scalars().all()
        attempt_num = len(existing_attempts) + 1

        # Audit attempt
        audit_attempt = AuditLog(
            agent_id=agent.id,
            transaction_id=tx_record.id,
            event_type="PAYMENT_ATTEMPT",
            action="EXECUTE_PAYMENT",
            decision="PROCESSING",
            reason=f"Initiating payment execution via {self.provider.__class__.__name__} (Attempt #{attempt_num})",
            metadata_payload={"amount": amount, "merchant_name": merchant_name, "attempt": attempt_num, "payment_method": pm_alias},
        )
        db.add(audit_attempt)
        db.commit()

        # 4. DISPATCH TO PAYMENT PROVIDER
        exec_request = PaymentExecutionRequest(
            transaction_id=str(tx_record.id),
            idempotency_key=tx_record.idempotency_key,
            amount=tx_record.amount,
            currency=tx_record.currency,
            merchant_name=tx_record.merchant_name,
            category=tx_record.category,
            attempt_number=attempt_num,
            payment_method_alias=pm_alias,
            metadata=metadata,
        )
        provider_result: PaymentExecutionResult = self.provider.create_payment(exec_request)

        # 5. PERSIST PAYMENT ATTEMPT ENTITY
        attempt_status = "SUCCESS" if provider_result.success else "FAILED"
        payment_attempt = PaymentAttempt(
            id=uuid.uuid4(),
            transaction_id=tx_record.id,
            payment_method_id=pm_id,
            attempt_number=attempt_num,
            status=attempt_status,
            provider_payment_id=provider_result.provider_payment_id,
            error_code=provider_result.error_code if not provider_result.success else None,
            error_message=provider_result.error_message if not provider_result.success else None,
            response_payload=provider_result.raw_response or provider_result.response_payload,
        )
        db.add(payment_attempt)

        # 6. PERSIST PAYMENT RESULT ON TRANSACTION (PAYMENT_PENDING -> SUCCESS / FAILED)
        if provider_result.success:
            tx_record.transition_to(TransactionStatus.SUCCESS)
        else:
            tx_record.transition_to(TransactionStatus.FAILED)
            tx_record.decision_reason = (
                f"Payment Gateway Error [{provider_result.error_code}]: {provider_result.error_message}"
                if provider_result.error_code
                else f"Payment Gateway Error: {provider_result.error_message}"
            )

        tx_record.provider_payment_id = provider_result.provider_payment_id
        tx_record.payment_provider = self.provider.__class__.__name__

        # 7. RECORD PAYMENT_RESULT AUDIT LOG
        audit_result = AuditLog(
            agent_id=agent.id,
            transaction_id=tx_record.id,
            event_type="PAYMENT_RESULT",
            action="EXECUTE_PAYMENT",
            decision=tx_record.status,
            reason=provider_result.error_message or "Payment processed successfully.",
            metadata_payload={
                "provider_payment_id": provider_result.provider_payment_id,
                "attempt_number": attempt_num,
                "success": provider_result.success,
                "error_code": provider_result.error_code,
            },
        )
        db.add(audit_result)
        db.commit()
        db.refresh(tx_record)

        # 8. AUTOMATIC FALLBACK EXECUTION (if enabled and Attempt #1 failed)
        should_auto_fallback = enable_auto_fallback or (metadata and metadata.get("auto_fallback") is True)
        if not provider_result.success and should_auto_fallback and attempt_num == 1:
            fallback_pm = self.get_fallback_payment_method(db, wallet.id)
            if fallback_pm:
                return self.execute_fallback_payment(
                    db,
                    payment_id=tx_record.id,
                    fallback_method_id=fallback_pm.id,
                    metadata=metadata,
                )

        return {
            "success": provider_result.success,
            "status": tx_record.status,
            "payment_id": str(tx_record.id),
            "provider_payment_id": provider_result.provider_payment_id,
            "amount": tx_record.amount,
            "currency": tx_record.currency,
            "merchant_name": tx_record.merchant_name,
            "category": tx_record.category,
            "attempt_number": attempt_num,
            "decision": "ALLOWED",
            "decision_reason": eval_result["reason"],
            "failure_reason": provider_result.error_code if not provider_result.success else None,
            "error_code": provider_result.error_code,
            "error_message": provider_result.error_message,
        }

    def execute_fallback_payment(
        self,
        db: Session,
        *,
        payment_id: uuid.UUID,
        fallback_method_id: Optional[uuid.UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes a policy-controlled fallback payment using a secondary PaymentMethod.
        Guards:
        - Centralized retry/fallback eligibility check via check_retry_eligibility (MAX_RETRIES=1).
        - Fallback PaymentMethod validation (wallet security, active status).
        - Mandatory Policy Engine evaluation of the fallback transaction prior to provider execution.
        - Controlled state machine transition: FAILED -> PAYMENT_PENDING -> SUCCESS / FAILED.
        - Creates a new PaymentAttempt with attempt_number = 2 (never #3).
        - Comprehensive audit logging of the entire fallback lifecycle.
        """
        # Step 1: Centralized eligibility check
        eligibility = self.check_retry_eligibility(db, payment_id)
        tx: Transaction = eligibility["transaction"]
        next_attempt = eligibility["next_attempt_number"]  # must be 2

        agent = db.get(Agent, tx.agent_id)
        wallet = db.get(Wallet, tx.wallet_id)

        # Step 2: Identify and validate fallback PaymentMethod
        fallback_pm = self.get_fallback_payment_method(db, wallet.id, custom_fallback_id=fallback_method_id)
        if not fallback_pm:
            audit_no_fallback = AuditLog(
                agent_id=agent.id,
                transaction_id=tx.id,
                event_type="FALLBACK_EVALUATION",
                action="IDENTIFY_FALLBACK",
                decision="UNAVAILABLE",
                reason="No active fallback payment method configured for wallet.",
                metadata_payload={"wallet_id": str(wallet.id)},
            )
            db.add(audit_no_fallback)
            db.commit()
            raise InvalidPaymentStateError("No active fallback payment method available for wallet.")

        # Step 3: Record Fallback Candidate Selection in AuditLog
        audit_selected = AuditLog(
            agent_id=agent.id,
            transaction_id=tx.id,
            event_type="FALLBACK_SELECTED",
            action="SELECT_FALLBACK",
            decision="SELECTED",
            reason=f"Selected secondary fallback payment method: {fallback_pm.type} ({fallback_pm.token_or_alias})",
            metadata_payload={
                "fallback_method_id": str(fallback_pm.id),
                "fallback_type": fallback_pm.type,
                "fallback_token": fallback_pm.token_or_alias,
                "previous_failure_reason": eligibility["last_failure_reason"],
            },
        )
        db.add(audit_selected)
        db.commit()

        # Step 4: Mandatory Policy Engine Evaluation for Fallback
        eval_result = WalletService.evaluate_and_audit(
            db,
            merchant_name=tx.merchant_name,
            amount=tx.amount,
            category=tx.category,
            agent_id=agent.id,
            idempotency_key=f"{tx.idempotency_key}_fallback_{next_attempt}",
            metadata_payload={
                "fallback": True,
                "fallback_method_id": str(fallback_pm.id),
                "fallback_type": fallback_pm.type,
                "previous_failure_reason": eligibility["last_failure_reason"],
            },
        )

        # Record FALLBACK_POLICY_CHECKED in AuditLog
        audit_policy_checked = AuditLog(
            agent_id=agent.id,
            transaction_id=tx.id,
            event_type="FALLBACK_POLICY_CHECKED",
            action="EVALUATE_POLICY",
            decision="APPROVED" if eval_result["approved"] else "REJECTED",
            reason=eval_result["reason"],
            rules_checked=eval_result.get("rules_checked"),
            metadata_payload={
                "fallback_method_id": str(fallback_pm.id),
                "fallback_type": fallback_pm.type,
                "decision_code": eval_result.get("decision_code"),
                "remaining_daily_budget": eval_result.get("remaining_daily_budget"),
            },
        )
        db.add(audit_policy_checked)
        db.commit()

        if not eval_result["approved"]:
            # Fallback Rejected by Policy
            audit_fallback_rej = AuditLog(
                agent_id=agent.id,
                transaction_id=tx.id,
                event_type="FALLBACK_REJECTED",
                action="EVALUATE_FALLBACK",
                decision="REJECTED",
                reason=f"Fallback payment of ₹{tx.amount:,.2f} via {fallback_pm.type} was DENIED by policy: {eval_result['reason']}",
                rules_checked=eval_result.get("rules_checked"),
                metadata_payload={
                    "fallback_method_id": str(fallback_pm.id),
                    "fallback_type": fallback_pm.type,
                    "decision_code": eval_result.get("decision_code"),
                    "reason": eval_result.get("reason"),
                    "audit_log_id": str(eval_result.get("audit_log_id")) if eval_result.get("audit_log_id") else None,
                },
            )
            db.add(audit_fallback_rej)
            tx.decision_reason = f"Fallback blocked by policy: {eval_result['reason']}"
            db.commit()

            # INVARIANT: Provider is NEVER called on policy rejection
            raise PolicyViolationError(
                reason=eval_result["reason"],
                decision_code=eval_result["decision_code"],
                details=eval_result,
            )

        # Fallback Approved by Policy
        audit_fallback_app = AuditLog(
            agent_id=agent.id,
            transaction_id=tx.id,
            event_type="FALLBACK_APPROVED",
            action="EVALUATE_FALLBACK",
            decision="APPROVED",
            reason=f"Fallback payment of ₹{tx.amount:,.2f} via {fallback_pm.type} APPROVED by policy.",
            rules_checked=eval_result.get("rules_checked"),
            metadata_payload={"fallback_method_id": str(fallback_pm.id), "fallback_type": fallback_pm.type},
        )
        db.add(audit_fallback_app)
        db.commit()

        # Step 5: Controlled state machine transition: FAILED -> PAYMENT_PENDING
        tx.transition_to(TransactionStatus.PAYMENT_PENDING, allow_retry=True)
        db.flush()

        # Step 6: Dispatch Fallback Execution to Provider
        exec_request = PaymentExecutionRequest(
            transaction_id=str(tx.id),
            idempotency_key=tx.idempotency_key,
            amount=tx.amount,
            currency=tx.currency,
            merchant_name=tx.merchant_name,
            category=tx.category,
            attempt_number=next_attempt,
            payment_method_alias=fallback_pm.token_or_alias,
            metadata=metadata,
        )
        provider_result = self.provider.create_payment(exec_request)

        # Step 7: Persist new PaymentAttempt entity for Fallback (Attempt #2)
        attempt_status = "SUCCESS" if provider_result.success else "FAILED"
        payment_attempt = PaymentAttempt(
            id=uuid.uuid4(),
            transaction_id=tx.id,
            payment_method_id=fallback_pm.id,
            attempt_number=next_attempt,
            status=attempt_status,
            provider_payment_id=provider_result.provider_payment_id,
            error_code=provider_result.error_code if not provider_result.success else None,
            error_message=provider_result.error_message if not provider_result.success else None,
            response_payload=provider_result.raw_response or provider_result.response_payload,
        )
        db.add(payment_attempt)

        # Step 8: Transition Transaction status: PAYMENT_PENDING -> SUCCESS / FAILED
        if provider_result.success:
            tx.transition_to(TransactionStatus.SUCCESS)
            tx.payment_method_id = fallback_pm.id
            tx.decision_reason = f"Payment succeeded via fallback method ({fallback_pm.type}) on attempt #{next_attempt}"
        else:
            tx.transition_to(TransactionStatus.FAILED)
            tx.decision_reason = (
                f"Fallback Attempt #{next_attempt} Failed [{provider_result.error_code}]: {provider_result.error_message}"
                if provider_result.error_code
                else f"Fallback Attempt #{next_attempt} Failed: {provider_result.error_message}"
            )

        tx.provider_payment_id = provider_result.provider_payment_id
        tx.payment_provider = self.provider.__class__.__name__

        # Step 9: Record Fallback Payment Result Audit Log
        audit_result = AuditLog(
            agent_id=agent.id,
            transaction_id=tx.id,
            event_type="PAYMENT_RESULT",
            action="EXECUTE_FALLBACK",
            decision=tx.status,
            reason=provider_result.error_message or f"Fallback attempt #{next_attempt} succeeded via {fallback_pm.type}.",
            metadata_payload={
                "provider_payment_id": provider_result.provider_payment_id,
                "attempt_number": next_attempt,
                "success": provider_result.success,
                "error_code": provider_result.error_code,
                "fallback_method_id": str(fallback_pm.id),
                "fallback_type": fallback_pm.type,
            },
        )
        db.add(audit_result)
        db.commit()
        db.refresh(tx)

        return {
            "success": provider_result.success,
            "status": tx.status,
            "payment_id": str(tx.id),
            "provider_payment_id": provider_result.provider_payment_id,
            "amount": tx.amount,
            "currency": tx.currency,
            "merchant_name": tx.merchant_name,
            "category": tx.category,
            "attempt_number": next_attempt,
            "payment_method_id": str(fallback_pm.id),
            "payment_method_type": fallback_pm.type,
            "fallback_executed": True,
            "decision": "ALLOWED",
            "decision_reason": tx.decision_reason,
            "failure_reason": provider_result.error_code if not provider_result.success else None,
            "error_code": provider_result.error_code,
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
        Safely retries an eligible failed payment.
        Guards:
        - Centralized retry eligibility check via check_retry_eligibility (MAX_RETRIES=1).
        - Source of truth: persisted PaymentAttempt records in DB.
        - Controlled state machine transition: FAILED -> PAYMENT_PENDING -> SUCCESS / FAILED.
        - Re-checks policy engine before executing provider retry.
        - Creates a new PaymentAttempt with attempt_number = 2 (never #3).
        """
        eligibility = self.check_retry_eligibility(db, payment_id)
        tx: Transaction = eligibility["transaction"]
        next_attempt = eligibility["next_attempt_number"]

        # Get Agent & Wallet
        agent = db.get(Agent, tx.agent_id)
        wallet = db.get(Wallet, tx.wallet_id)
        primary_pm = db.execute(
            select(PaymentMethod).where(PaymentMethod.wallet_id == wallet.id, PaymentMethod.is_primary == True)
        ).scalar_one_or_none()
        pm_alias = primary_pm.token_or_alias if primary_pm else "mock_default_vpa"

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
            reason=f"Initiating retry attempt #{next_attempt} (MAX_RETRIES={MAX_RETRIES})",
            metadata_payload={"attempt": next_attempt, "max_retries": MAX_RETRIES},
        )
        db.add(audit_retry)

        # Controlled state machine transition: FAILED -> PAYMENT_PENDING
        tx.transition_to(TransactionStatus.PAYMENT_PENDING, allow_retry=True)
        db.flush()

        # Dispatch Retry to Provider (Real second provider execution)
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

        # Persist new PaymentAttempt entity for this retry
        attempt_status = "SUCCESS" if provider_result.success else "FAILED"
        payment_attempt = PaymentAttempt(
            id=uuid.uuid4(),
            transaction_id=tx.id,
            payment_method_id=primary_pm.id if primary_pm else None,
            attempt_number=next_attempt,
            status=attempt_status,
            provider_payment_id=provider_result.provider_payment_id,
            error_code=provider_result.error_code if not provider_result.success else None,
            error_message=provider_result.error_message if not provider_result.success else None,
            response_payload=provider_result.raw_response or provider_result.response_payload,
        )
        db.add(payment_attempt)

        # Transition Transaction status: PAYMENT_PENDING -> SUCCESS / FAILED
        if provider_result.success:
            tx.transition_to(TransactionStatus.SUCCESS)
            tx.decision_reason = f"Payment succeeded on retry attempt #{next_attempt}"
        else:
            tx.transition_to(TransactionStatus.FAILED)
            tx.decision_reason = (
                f"Retry Attempt #{next_attempt} Failed [{provider_result.error_code}]: {provider_result.error_message}"
                if provider_result.error_code
                else f"Retry Attempt #{next_attempt} Failed: {provider_result.error_message}"
            )

        tx.provider_payment_id = provider_result.provider_payment_id
        tx.payment_provider = self.provider.__class__.__name__

        # Record Audit Log
        audit_result = AuditLog(
            agent_id=agent.id,
            transaction_id=tx.id,
            event_type="PAYMENT_RESULT",
            action="RETRY_PAYMENT",
            decision=tx.status,
            reason=provider_result.error_message or f"Retry attempt #{next_attempt} succeeded.",
            metadata_payload={
                "provider_payment_id": provider_result.provider_payment_id,
                "attempt_number": next_attempt,
                "success": provider_result.success,
                "error_code": provider_result.error_code,
            },
        )
        db.add(audit_result)
        db.commit()
        db.refresh(tx)

        return {
            "success": provider_result.success,
            "status": tx.status,
            "payment_id": str(tx.id),
            "provider_payment_id": provider_result.provider_payment_id,
            "amount": tx.amount,
            "currency": tx.currency,
            "merchant_name": tx.merchant_name,
            "attempt_number": next_attempt,
            "decision": "ALLOWED",
            "decision_reason": tx.decision_reason,
            "failure_reason": provider_result.error_code if not provider_result.success else None,
            "error_code": provider_result.error_code,
            "error_message": provider_result.error_message,
        }

    def get_payment_status(self, db: Session, payment_id: uuid.UUID) -> Dict[str, Any]:
        """Retrieves structured payment status from database."""
        tx = db.get(Transaction, payment_id)
        if not tx:
            raise ValueError(f"Transaction with ID {payment_id} not found.")

        # Count total attempts from PaymentAttempt records
        attempts = db.execute(
            select(PaymentAttempt)
            .where(PaymentAttempt.transaction_id == tx.id)
            .order_by(PaymentAttempt.attempt_number.asc())
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
            "attempts": [
                {
                    "attempt_number": a.attempt_number,
                    "payment_method_id": str(a.payment_method_id) if a.payment_method_id else None,
                    "status": a.status,
                    "provider_payment_id": a.provider_payment_id,
                    "error_code": a.error_code,
                    "error_message": a.error_message,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in attempts
            ],
            "created_at": tx.created_at,
            "updated_at": tx.updated_at,
        }
