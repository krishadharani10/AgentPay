"""
Day 3 Phase 1 Step 7: Automatic & Policy-Controlled Fallback Payment Tests
Verifies that:
1. Primary failure/timeout -> secondary PaymentMethod fallback execution.
2. Fallback strictly consumes the single retry budget (MAX_RETRIES = 1). Total provider attempts = 2.
3. Fallback MUST be evaluated and approved by Policy Engine before provider invocation.
4. Attempt #1 remains immutable; Attempt #2 records the secondary PaymentMethod ID.
5. Inactive methods and cross-wallet payment methods are blocked before provider execution.
6. Complete audit trail records fallback identification, policy evaluation, and result.
"""
import uuid
import pytest
from sqlalchemy import select

from app.models.transaction import (
    Transaction,
    TransactionStatus,
    InvalidPaymentStateError,
    MaxRetriesExceededError,
)
from app.models.payment_method import PaymentMethod
from app.models.payment_attempt import PaymentAttempt
from app.models.audit_log import AuditLog
from app.models.policy import Policy
from app.models.wallet import Wallet
from app.models.agent import Agent
from app.services.payment_adapter import (
    MockPaymentProvider,
    MockPaymentMode,
    PaymentFailureReason,
)
from app.services.payment_service import (
    PaymentService,
    PolicyViolationError,
    MAX_RETRIES,
)


class TestFallbackPaymentExecution:
    """Comprehensive test suite for policy-controlled fallback payments."""

    def test_1_primary_network_error_fallback_success(self, db_session, test_seed_data):
        """
        Test 1: Primary fails with NETWORK_ERROR -> Fallback succeeds with CARD.
        - Attempt #1 = primary / FAILED / NETWORK_ERROR
        - Attempt #2 = fallback / SUCCESS
        - Transaction = SUCCESS
        """
        provider = MockPaymentProvider(
            mode_sequence=[MockPaymentMode.NETWORK_ERROR, MockPaymentMode.SUCCESS]
        )
        service = PaymentService(provider=provider)
        wallet = test_seed_data["wallet"]

        # 1. Primary Attempt fails
        res1 = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=f"fb_net_succ_{uuid.uuid4().hex[:8]}",
        )
        assert res1["success"] is False
        assert res1["status"] == "FAILED"
        assert res1["failure_reason"] == "NETWORK_ERROR"
        payment_id = uuid.UUID(res1["payment_id"])

        # Fetch secondary payment method
        fallback_pm = db_session.execute(
            select(PaymentMethod).where(PaymentMethod.wallet_id == wallet.id, PaymentMethod.is_primary == False)
        ).scalar_one()

        # 2. Fallback Execution
        res2 = service.execute_fallback_payment(
            db_session,
            payment_id=payment_id,
            fallback_method_id=fallback_pm.id,
        )
        assert res2["success"] is True
        assert res2["status"] == "SUCCESS"
        assert res2["attempt_number"] == 2
        assert res2["payment_method_id"] == str(fallback_pm.id)
        assert res2["fallback_executed"] is True

        # 3. Verify Database Integrity
        tx = db_session.get(Transaction, payment_id)
        assert tx.status == "SUCCESS"
        assert tx.payment_method_id == fallback_pm.id

        attempts = db_session.execute(
            select(PaymentAttempt)
            .where(PaymentAttempt.transaction_id == payment_id)
            .order_by(PaymentAttempt.attempt_number.asc())
        ).scalars().all()

        assert len(attempts) == 2
        # Attempt #1 (Primary UPI)
        assert attempts[0].attempt_number == 1
        assert attempts[0].status == "FAILED"
        assert attempts[0].error_code == "NETWORK_ERROR"
        assert attempts[0].payment_method_id != fallback_pm.id

        # Attempt #2 (Fallback Card)
        assert attempts[1].attempt_number == 2
        assert attempts[1].status == "SUCCESS"
        assert attempts[1].error_code is None
        assert attempts[1].payment_method_id == fallback_pm.id

    def test_2_primary_timeout_fallback_success(self, db_session, test_seed_data):
        """
        Test 2: Primary fails with TIMEOUT -> Fallback succeeds.
        """
        provider = MockPaymentProvider(
            mode_sequence=[MockPaymentMode.TIMEOUT, MockPaymentMode.SUCCESS]
        )
        service = PaymentService(provider=provider)

        res1 = service.process_payment(
            db_session,
            merchant_name="Netflix",
            amount=499.0,
            category="subscriptions",
            idempotency_key=f"fb_time_succ_{uuid.uuid4().hex[:8]}",
        )
        assert res1["status"] == "FAILED"
        payment_id = uuid.UUID(res1["payment_id"])

        res2 = service.execute_fallback_payment(db_session, payment_id=payment_id)
        assert res2["success"] is True
        assert res2["status"] == "SUCCESS"
        assert res2["attempt_number"] == 2

        tx = db_session.get(Transaction, payment_id)
        assert tx.status == "SUCCESS"

    def test_3_primary_provider_error_fallback_success(self, db_session, test_seed_data):
        """
        Test 3: Primary fails with PROVIDER_ERROR -> Fallback succeeds.
        """
        provider = MockPaymentProvider(
            mode_sequence=[MockPaymentMode.PROVIDER_ERROR, MockPaymentMode.SUCCESS]
        )
        service = PaymentService(provider=provider)

        res1 = service.process_payment(
            db_session,
            merchant_name="MakeMyTrip",
            amount=4500.0,
            category="travel",
            idempotency_key=f"fb_prov_succ_{uuid.uuid4().hex[:8]}",
        )
        assert res1["status"] == "FAILED"
        payment_id = uuid.UUID(res1["payment_id"])

        res2 = service.execute_fallback_payment(db_session, payment_id=payment_id)
        assert res2["success"] is True
        assert res2["status"] == "SUCCESS"
        assert res2["attempt_number"] == 2

    def test_4_policy_rejects_fallback(self, db_session, test_seed_data):
        """
        Test 4: Primary fails. Fallback candidate exists, but Policy Engine rejects fallback.
        - Provider is NEVER called for fallback
        - Only Attempt #1 exists in DB
        - Transaction remains FAILED
        - AuditLog records fallback rejection
        """
        provider = MockPaymentProvider(mode=MockPaymentMode.NETWORK_ERROR)
        service = PaymentService(provider=provider)

        res1 = service.process_payment(
            db_session,
            merchant_name="Amazon",
            amount=899.0,
            category="shopping",
            idempotency_key=f"fb_pol_rej_{uuid.uuid4().hex[:8]}",
        )
        payment_id = uuid.UUID(res1["payment_id"])
        provider_calls_after_1 = provider.call_count

        # Deactivate policy or lower daily limit to force policy rejection on fallback
        policy = db_session.execute(
            select(Policy).where(Policy.agent_id == test_seed_data["agent"].id)
        ).scalar_one()
        policy.daily_spending_limit = 100.0  # ₹100 limit, transaction is ₹899
        db_session.commit()

        # Execute fallback -> must raise PolicyViolationError
        with pytest.raises(PolicyViolationError) as exc_info:
            service.execute_fallback_payment(db_session, payment_id=payment_id)

        assert "daily spending limit exceeded" in str(exc_info.value).lower()

        # Invariant: Payment Provider was NEVER called for fallback
        assert provider.call_count == provider_calls_after_1

        # Only Attempt #1 exists
        attempts = db_session.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == payment_id)
        ).scalars().all()
        assert len(attempts) == 1
        assert attempts[0].attempt_number == 1

        # Transaction remains FAILED
        tx = db_session.get(Transaction, payment_id)
        assert tx.status == "FAILED"

        # Verify Fallback Rejection Audit Log exists
        logs = db_session.execute(
            select(AuditLog)
            .where(AuditLog.transaction_id == payment_id, AuditLog.event_type == "FALLBACK_REJECTED")
        ).scalars().all()
        assert len(logs) == 1
        assert logs[0].decision == "REJECTED"

    def test_5_fallback_also_fails_terminal(self, db_session, test_seed_data):
        """
        Test 5: Primary fails (NETWORK_ERROR), Fallback also fails (PROVIDER_ERROR).
        - Attempt #1 = FAILED (NETWORK_ERROR)
        - Attempt #2 = FAILED (PROVIDER_ERROR)
        - Transaction = FAILED
        - No Attempt #3 can be created
        """
        provider = MockPaymentProvider(
            mode_sequence=[MockPaymentMode.NETWORK_ERROR, MockPaymentMode.PROVIDER_ERROR]
        )
        service = PaymentService(provider=provider)

        res1 = service.process_payment(
            db_session,
            merchant_name="Netflix",
            amount=499.0,
            category="subscriptions",
            idempotency_key=f"fb_double_fail_{uuid.uuid4().hex[:8]}",
        )
        payment_id = uuid.UUID(res1["payment_id"])

        res2 = service.execute_fallback_payment(db_session, payment_id=payment_id)
        assert res2["success"] is False
        assert res2["status"] == "FAILED"
        assert res2["failure_reason"] == "PROVIDER_ERROR"
        assert res2["attempt_number"] == 2

        tx = db_session.get(Transaction, payment_id)
        assert tx.status == "FAILED"

        attempts = db_session.execute(
            select(PaymentAttempt)
            .where(PaymentAttempt.transaction_id == payment_id)
            .order_by(PaymentAttempt.attempt_number.asc())
        ).scalars().all()
        assert len(attempts) == 2
        assert attempts[0].error_code == "NETWORK_ERROR"
        assert attempts[1].error_code == "PROVIDER_ERROR"

        # 3rd attempt is rejected
        with pytest.raises(MaxRetriesExceededError):
            service.execute_fallback_payment(db_session, payment_id=payment_id)

    def test_6_attempt_3_impossible_after_fallback(self, db_session, test_seed_data):
        """
        Test 6: Attempt #3 is impossible. MAX_RETRIES = 1 is strictly shared.
        """
        provider = MockPaymentProvider(
            mode_sequence=[MockPaymentMode.TIMEOUT, MockPaymentMode.DECLINED]
        )
        service = PaymentService(provider=provider)

        res1 = service.process_payment(
            db_session,
            merchant_name="Spotify",
            amount=699.0,
            category="subscriptions",
            idempotency_key=f"fb_no_three_{uuid.uuid4().hex[:8]}",
        )
        payment_id = uuid.UUID(res1["payment_id"])

        # Fallback (Attempt #2)
        service.execute_fallback_payment(db_session, payment_id=payment_id)
        provider_calls = provider.call_count
        assert provider_calls == 2

        # Additional retry or fallback attempts must raise MaxRetriesExceededError
        with pytest.raises(MaxRetriesExceededError):
            service.retry_payment(db_session, payment_id=payment_id)

        with pytest.raises(MaxRetriesExceededError):
            service.execute_fallback_payment(db_session, payment_id=payment_id)

        # Provider was not called
        assert provider.call_count == provider_calls

        # Attempts count in DB remains 2
        attempts = db_session.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == payment_id)
        ).scalars().all()
        assert len(attempts) == 2

    def test_7_cross_wallet_payment_method_protection(self, db_session, test_seed_data):
        """
        Test 7: Attempting to use a fallback PaymentMethod belonging to another wallet/user is blocked.
        """
        provider = MockPaymentProvider(mode=MockPaymentMode.NETWORK_ERROR)
        service = PaymentService(provider=provider)

        res1 = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=f"fb_cross_wallet_{uuid.uuid4().hex[:8]}",
        )
        payment_id = uuid.UUID(res1["payment_id"])

        # Create another wallet and payment method belonging to a different agent/user
        other_wallet = Wallet(
            id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            status="ACTIVE",
            daily_spending_limit=10000.0,
            per_transaction_limit=5000.0,
        )
        db_session.add(other_wallet)
        db_session.flush()

        foreign_pm = PaymentMethod(
            id=uuid.uuid4(),
            wallet_id=other_wallet.id,
            type="CARD_TOKEN",
            provider="mock",
            token_or_alias="foreign_user_card_tok",
            is_primary=False,
            is_active=True,
            priority=2,
        )
        db_session.add(foreign_pm)
        db_session.commit()

        # Attempt fallback using foreign payment method -> must raise PolicyViolationError
        with pytest.raises(PolicyViolationError, match="Unauthorized payment method"):
            service.execute_fallback_payment(
                db_session,
                payment_id=payment_id,
                fallback_method_id=foreign_pm.id,
            )

    def test_8_inactive_fallback_method_rejected(self, db_session, test_seed_data):
        """
        Test 8: Inactive fallback PaymentMethod cannot be executed.
        """
        provider = MockPaymentProvider(mode=MockPaymentMode.NETWORK_ERROR)
        service = PaymentService(provider=provider)
        wallet = test_seed_data["wallet"]

        res1 = service.process_payment(
            db_session,
            merchant_name="Netflix",
            amount=499.0,
            category="subscriptions",
            idempotency_key=f"fb_inactive_pm_{uuid.uuid4().hex[:8]}",
        )
        payment_id = uuid.UUID(res1["payment_id"])

        # Create inactive payment method
        inactive_pm = PaymentMethod(
            id=uuid.uuid4(),
            wallet_id=wallet.id,
            type="CARD_TOKEN",
            provider="mock",
            token_or_alias="inactive_card_tok",
            is_primary=False,
            is_active=False,  # INACTIVE
            priority=3,
        )
        db_session.add(inactive_pm)
        db_session.commit()

        with pytest.raises(InvalidPaymentStateError, match="is inactive"):
            service.execute_fallback_payment(
                db_session,
                payment_id=payment_id,
                fallback_method_id=inactive_pm.id,
            )

    def test_9_successful_transaction_cannot_fallback(self, db_session, test_seed_data):
        """
        Test 9: SUCCESS transaction cannot execute fallback.
        """
        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        res = service.process_payment(
            db_session,
            merchant_name="Spotify",
            amount=699.0,
            category="subscriptions",
            idempotency_key=f"fb_succ_no_fb_{uuid.uuid4().hex[:8]}",
        )
        payment_id = uuid.UUID(res["payment_id"])

        with pytest.raises(InvalidPaymentStateError, match="already completed successfully"):
            service.execute_fallback_payment(db_session, payment_id=payment_id)

    def test_10_complete_fallback_audit_trail(self, db_session, test_seed_data):
        """
        Test 10: Audit trail records the full lifecycle:
        1. Primary PAYMENT_ATTEMPT
        2. Primary PAYMENT_RESULT (FAILED)
        3. FALLBACK_IDENTIFIED
        4. FALLBACK_APPROVED (Policy Engine)
        5. Fallback PAYMENT_RESULT (SUCCESS)
        """
        provider = MockPaymentProvider(
            mode_sequence=[MockPaymentMode.NETWORK_ERROR, MockPaymentMode.SUCCESS]
        )
        service = PaymentService(provider=provider)

        res1 = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=f"fb_audit_trail_{uuid.uuid4().hex[:8]}",
        )
        payment_id = uuid.UUID(res1["payment_id"])

        service.execute_fallback_payment(db_session, payment_id=payment_id)

        # Query all audit logs for this transaction
        logs = db_session.execute(
            select(AuditLog)
            .where(AuditLog.transaction_id == payment_id)
            .order_by(AuditLog.created_at.asc())
        ).scalars().all()

        event_types = [l.event_type for l in logs]
        assert "PAYMENT_ATTEMPT" in event_types
        assert "PAYMENT_RESULT" in event_types
        assert "FALLBACK_SELECTED" in event_types
        assert "FALLBACK_POLICY_CHECKED" in event_types
        assert "FALLBACK_APPROVED" in event_types

        # Verify fallback approval log
        approval_log = next(l for l in logs if l.event_type == "FALLBACK_APPROVED")
        assert approval_log.decision == "APPROVED"
        assert approval_log.rules_checked is not None

    def test_11_deterministic_primary_upi_fallback_card_success(self, db_session, test_seed_data):
        """
        Day 3 Phase 2 Step 2: Dedicated deterministic Primary UPI -> Fallback Card Success scenario.
        Scenario:
        - Merchant: Torrent Power
        - Category: utilities
        - Amount: ₹1,240.0
        - Primary method: UPI_VPA (declines deterministically)
        - Fallback method: CARD_TOKEN (succeeds deterministically)
        - Verifications:
          * amount = 1240
          * merchant = Torrent Power
          * attempt #1 = UPI
          * attempt #1 = DECLINED
          * fallback method = Corporate Card (CARD_TOKEN)
          * fallback policy evaluated
          * fallback approved
          * attempt #2 = Card
          * attempt #2 = SUCCESS
          * final transaction = SUCCESS
          * exactly 2 PaymentAttempt rows
          * no provider call #3
        """
        wallet = test_seed_data["wallet"]

        # Fetch seeded primary and fallback payment methods
        primary_pm = db_session.execute(
            select(PaymentMethod).where(PaymentMethod.wallet_id == wallet.id, PaymentMethod.is_primary == True)
        ).scalar_one()
        assert primary_pm.type == "UPI_VPA"

        fallback_pm = db_session.execute(
            select(PaymentMethod).where(PaymentMethod.wallet_id == wallet.id, PaymentMethod.is_primary == False)
        ).scalar_one()
        assert fallback_pm.type == "CARD_TOKEN"

        # 1. Configure MockPaymentProvider deterministically: Attempt 1 = DECLINED, Attempt 2 = SUCCESS
        provider = MockPaymentProvider(
            mode_sequence=[MockPaymentMode.DECLINED, MockPaymentMode.SUCCESS]
        )
        service = PaymentService(provider=provider)

        # 2. Process Primary Payment (Torrent Power, ₹1240)
        res1 = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=f"torrent_power_fallback_{uuid.uuid4().hex[:8]}",
        )
        assert res1["success"] is False
        assert res1["status"] == "FAILED"
        assert res1["failure_reason"] == "DECLINED"
        assert res1["attempt_number"] == 1
        assert res1["amount"] == 1240.0
        assert res1["merchant_name"] == "Torrent Power"
        payment_id = uuid.UUID(res1["payment_id"])

        # Check Attempt #1 in DB
        attempts_after_1 = db_session.execute(
            select(PaymentAttempt)
            .where(PaymentAttempt.transaction_id == payment_id)
            .order_by(PaymentAttempt.attempt_number.asc())
        ).scalars().all()
        assert len(attempts_after_1) == 1
        assert attempts_after_1[0].attempt_number == 1
        assert attempts_after_1[0].payment_method_id == primary_pm.id
        assert attempts_after_1[0].status == "FAILED"
        assert attempts_after_1[0].error_code == "DECLINED"

        # 3. Execute Fallback Payment via Corporate Card
        res2 = service.execute_fallback_payment(
            db_session,
            payment_id=payment_id,
            fallback_method_id=fallback_pm.id,
        )
        assert res2["success"] is True
        assert res2["status"] == "SUCCESS"
        assert res2["attempt_number"] == 2
        assert res2["payment_method_id"] == str(fallback_pm.id)
        assert res2["payment_method_type"] == "CARD_TOKEN"
        assert res2["amount"] == 1240.0
        assert res2["merchant_name"] == "Torrent Power"

        # 4. Verify Final Transaction Status & Provider Call Count
        tx = db_session.get(Transaction, payment_id)
        assert tx.status == "SUCCESS"
        assert tx.amount == 1240.0
        assert tx.merchant_name == "Torrent Power"
        assert tx.payment_method_id == fallback_pm.id
        assert provider.call_count == 2

        # 5. Verify exactly 2 PaymentAttempt records in DB
        attempts_final = db_session.execute(
            select(PaymentAttempt)
            .where(PaymentAttempt.transaction_id == payment_id)
            .order_by(PaymentAttempt.attempt_number.asc())
        ).scalars().all()
        assert len(attempts_final) == 2

        # Attempt #1 details
        assert attempts_final[0].attempt_number == 1
        assert attempts_final[0].payment_method_id == primary_pm.id
        assert attempts_final[0].status == "FAILED"
        assert attempts_final[0].error_code == "DECLINED"

        # Attempt #2 details
        assert attempts_final[1].attempt_number == 2
        assert attempts_final[1].payment_method_id == fallback_pm.id
        assert attempts_final[1].status == "SUCCESS"
        assert attempts_final[1].error_code is None

        # 6. Verify audit logs record the complete fallback lifecycle:
        # FALLBACK_SELECTED, FALLBACK_POLICY_CHECKED, FALLBACK_APPROVED
        audit_logs = db_session.execute(
            select(AuditLog)
            .where(AuditLog.transaction_id == payment_id)
            .order_by(AuditLog.created_at.asc())
        ).scalars().all()
        event_types = [l.event_type for l in audit_logs]

        assert "FALLBACK_SELECTED" in event_types
        assert "FALLBACK_POLICY_CHECKED" in event_types
        assert "FALLBACK_APPROVED" in event_types

        # Verify FALLBACK_SELECTED log
        selected_log = next(l for l in audit_logs if l.event_type == "FALLBACK_SELECTED")
        assert selected_log.decision == "SELECTED"
        assert selected_log.metadata_payload.get("fallback_method_id") == str(fallback_pm.id)
        assert selected_log.metadata_payload.get("fallback_type") == "CARD_TOKEN"

        # Verify FALLBACK_POLICY_CHECKED log
        checked_log = next(l for l in audit_logs if l.event_type == "FALLBACK_POLICY_CHECKED")
        assert checked_log.decision == "APPROVED"
        assert checked_log.rules_checked is not None

        # Verify FALLBACK_APPROVED log
        approved_log = next(l for l in audit_logs if l.event_type == "FALLBACK_APPROVED")
        assert approved_log.decision == "APPROVED"

        # 7. Invariant verification: No Attempt #3 can be created, and provider is not called a 3rd time
        with pytest.raises(InvalidPaymentStateError, match="already completed successfully"):
            service.execute_fallback_payment(db_session, payment_id=payment_id)

        assert provider.call_count == 2

    def test_12_deterministic_fallback_policy_rejection_scenario(self, db_session, test_seed_data):
        """
        Day 3 Phase 2 Step 3: Dedicated deterministic Fallback Policy Rejection scenario.
        Verifies:
        1. Original transaction created (₹1,240 Torrent Power).
        2. Original transaction passes Policy Engine (APPROVED).
        3. Primary payment method = UPI_VPA.
        4. UPI executes as PaymentAttempt #1.
        5. Primary payment fails (DECLINED).
        6. Fallback Corporate Card (CARD_TOKEN) is selected.
        7. Record audit event: FALLBACK_SELECTED.
        8. Run fallback through Policy Engine AGAIN.
        9. Policy condition causes fallback to be rejected (e.g. daily spending limit budget exhausted).
        10. Record: FALLBACK_POLICY_CHECKED and FALLBACK_REJECTED.
        11. DO NOT invoke payment provider for fallback.
        12. Do NOT create PaymentAttempt #2.
        13. Final transaction remains FAILED with explainable decision_reason.
        14. No Attempt #3 can be created.
        """
        wallet = test_seed_data["wallet"]
        agent = test_seed_data["agent"]

        # Fetch seeded primary and fallback payment methods
        primary_pm = db_session.execute(
            select(PaymentMethod).where(PaymentMethod.wallet_id == wallet.id, PaymentMethod.is_primary == True)
        ).scalar_one()
        assert primary_pm.type == "UPI_VPA"

        fallback_pm = db_session.execute(
            select(PaymentMethod).where(PaymentMethod.wallet_id == wallet.id, PaymentMethod.is_primary == False)
        ).scalar_one()
        assert fallback_pm.type == "CARD_TOKEN"

        # 1. Configure MockPaymentProvider: Primary = DECLINED
        provider = MockPaymentProvider(mode=MockPaymentMode.DECLINED)
        service = PaymentService(provider=provider)

        # 2. Process Primary Payment (passes initial policy, fails at gateway)
        res1 = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=f"torrent_power_rej_{uuid.uuid4().hex[:8]}",
        )
        assert res1["success"] is False
        assert res1["status"] == "FAILED"
        assert res1["failure_reason"] == "DECLINED"
        assert res1["attempt_number"] == 1
        assert provider.call_count == 1
        payment_id = uuid.UUID(res1["payment_id"])

        # Verify Attempt #1 persisted in DB
        attempts_after_1 = db_session.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == payment_id)
        ).scalars().all()
        assert len(attempts_after_1) == 1
        assert attempts_after_1[0].attempt_number == 1
        assert attempts_after_1[0].status == "FAILED"
        assert attempts_after_1[0].error_code == "DECLINED"

        # 3. Modify policy deterministically to simulate budget exhaustion before fallback
        policy = db_session.execute(
            select(Policy).where(Policy.agent_id == agent.id)
        ).scalar_one()
        policy.daily_spending_limit = 500.0  # Limit is now ₹500, bill is ₹1,240
        db_session.commit()

        # 4. Attempt Fallback Execution -> MUST BE REJECTED BY POLICY
        with pytest.raises(PolicyViolationError) as exc_info:
            service.execute_fallback_payment(
                db_session,
                payment_id=payment_id,
                fallback_method_id=fallback_pm.id,
            )

        assert "daily spending limit exceeded" in str(exc_info.value).lower()
        assert exc_info.value.decision_code in ["DAILY_LIMIT_EXCEEDED", "MULTIPLE_POLICY_VIOLATIONS"]

        # 5. Invariant Checks:
        # A. Primary provider was called exactly once; fallback provider was called ZERO times
        assert provider.call_count == 1

        # B. No PaymentAttempt #2 created (total attempts in DB remains exactly 1)
        attempts_final = db_session.execute(
            select(PaymentAttempt)
            .where(PaymentAttempt.transaction_id == payment_id)
            .order_by(PaymentAttempt.attempt_number.asc())
        ).scalars().all()
        assert len(attempts_final) == 1
        assert attempts_final[0].attempt_number == 1
        assert attempts_final[0].status == "FAILED"

        # C. Final Transaction.status remains FAILED with explainable reason
        tx = db_session.get(Transaction, payment_id)
        assert tx.status == "FAILED"
        assert "Fallback blocked by policy" in tx.decision_reason
        assert "daily spending limit" in tx.decision_reason.lower()

        # D. Audit Log Verification
        audit_logs = db_session.execute(
            select(AuditLog)
            .where(AuditLog.transaction_id == payment_id)
            .order_by(AuditLog.created_at.asc())
        ).scalars().all()
        event_types = [l.event_type for l in audit_logs]

        assert "FALLBACK_SELECTED" in event_types
        assert "FALLBACK_POLICY_CHECKED" in event_types
        assert "FALLBACK_REJECTED" in event_types
        assert "FALLBACK_APPROVED" not in event_types

        # Verify FALLBACK_SELECTED log
        selected_log = next(l for l in audit_logs if l.event_type == "FALLBACK_SELECTED")
        assert selected_log.decision == "SELECTED"
        assert selected_log.metadata_payload.get("fallback_method_id") == str(fallback_pm.id)
        assert selected_log.metadata_payload.get("fallback_type") == "CARD_TOKEN"

        # Verify FALLBACK_POLICY_CHECKED log
        checked_log = next(l for l in audit_logs if l.event_type == "FALLBACK_POLICY_CHECKED")
        assert checked_log.decision == "REJECTED"
        assert checked_log.rules_checked is not None

        # Verify FALLBACK_REJECTED log
        rejected_log = next(l for l in audit_logs if l.event_type == "FALLBACK_REJECTED")
        assert rejected_log.decision == "REJECTED"
        assert "daily spending limit exceeded" in rejected_log.reason.lower()

        # E. No Attempt #3 or automatic retry is possible
        with pytest.raises(PolicyViolationError):
            service.execute_fallback_payment(db_session, payment_id=payment_id)

        assert provider.call_count == 1

    def test_13_deterministic_fallback_policy_rejection_wallet_disabled(self, db_session, test_seed_data):
        """
        Test 13: Fallback rejected when policy wallet_enabled is turned off before fallback.
        Verifies policy rejection on disabled wallet without invoking payment provider.
        """
        provider = MockPaymentProvider(mode=MockPaymentMode.TIMEOUT)
        service = PaymentService(provider=provider)
        wallet = test_seed_data["wallet"]
        agent = test_seed_data["agent"]

        # Primary payment fails with TIMEOUT
        res1 = service.process_payment(
            db_session,
            merchant_name="Netflix",
            amount=499.0,
            category="subscriptions",
            idempotency_key=f"netflix_wallet_disabled_{uuid.uuid4().hex[:8]}",
        )
        payment_id = uuid.UUID(res1["payment_id"])
        assert provider.call_count == 1

        # Disable wallet in policy before fallback
        policy = db_session.execute(
            select(Policy).where(Policy.agent_id == agent.id)
        ).scalar_one()
        policy.wallet_enabled = False
        db_session.commit()

        # Execute fallback -> must be rejected
        with pytest.raises(PolicyViolationError) as exc_info:
            service.execute_fallback_payment(db_session, payment_id=payment_id)

        assert "wallet is inactive or disabled" in str(exc_info.value).lower()
        assert exc_info.value.decision_code == "WALLET_DISABLED"

        # Provider was called zero times for fallback
        assert provider.call_count == 1

        # Only Attempt #1 exists in DB
        attempts = db_session.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == payment_id)
        ).scalars().all()
        assert len(attempts) == 1

        # Transaction remains FAILED
        tx = db_session.get(Transaction, payment_id)
        assert tx.status == "FAILED"
        assert "WALLET_DISABLED" in tx.decision_reason or "disabled" in tx.decision_reason.lower()


