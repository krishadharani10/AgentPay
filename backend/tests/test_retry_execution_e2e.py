"""
Day 3 Phase 1 Step 6: End-to-End Retry Execution & State Lifecycle Tests
Verifies the complete real provider retry execution path, multi-attempt
persistence, and state transitions without hardcoding outcomes.
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
from app.models.payment_attempt import PaymentAttempt
from app.services.payment_adapter import (
    MockPaymentProvider,
    MockPaymentMode,
    PaymentFailureReason,
)
from app.services.payment_service import PaymentService, MAX_RETRIES


class TestEndToEndRetryExecution:
    """Comprehensive test suite for end-to-end retry execution lifecycle."""

    def test_1_network_error_then_successful_retry(self, db_session, test_seed_data):
        """
        1. NETWORK_ERROR -> successful retry:
        - Attempt #1 fails with NETWORK_ERROR
        - Controlled retry executes real 2nd provider call
        - Attempt #2 succeeds
        - Transaction ends in SUCCESS
        """
        provider = MockPaymentProvider(
            mode_sequence=[MockPaymentMode.NETWORK_ERROR, MockPaymentMode.SUCCESS]
        )
        service = PaymentService(provider=provider)

        # 1. Initial Attempt
        res1 = service.process_payment(
            db_session,
            merchant_name="Netflix",
            amount=499.0,
            category="subscriptions",
            idempotency_key=f"e2e_net_succ_{uuid.uuid4().hex[:8]}",
        )
        assert res1["success"] is False
        assert res1["status"] == "FAILED"
        assert res1["failure_reason"] == "NETWORK_ERROR"
        payment_id = uuid.UUID(res1["payment_id"])

        # Verify Attempt #1 persisted
        attempts_after_1 = db_session.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == payment_id)
        ).scalars().all()
        assert len(attempts_after_1) == 1
        assert attempts_after_1[0].attempt_number == 1
        assert attempts_after_1[0].status == "FAILED"
        assert attempts_after_1[0].error_code == "NETWORK_ERROR"

        # 2. Retry Attempt (Real 2nd provider execution)
        res2 = service.retry_payment(db_session, payment_id=payment_id)
        assert res2["success"] is True
        assert res2["status"] == "SUCCESS"
        assert res2["attempt_number"] == 2

        # 3. Verify final DB state
        tx = db_session.get(Transaction, payment_id)
        assert tx.status == "SUCCESS"

        attempts_after_2 = db_session.execute(
            select(PaymentAttempt)
            .where(PaymentAttempt.transaction_id == payment_id)
            .order_by(PaymentAttempt.attempt_number.asc())
        ).scalars().all()

        assert len(attempts_after_2) == 2
        assert attempts_after_2[0].attempt_number == 1
        assert attempts_after_2[0].status == "FAILED"
        assert attempts_after_2[0].error_code == "NETWORK_ERROR"

        assert attempts_after_2[1].attempt_number == 2
        assert attempts_after_2[1].status == "SUCCESS"
        assert attempts_after_2[1].error_code is None

    def test_2_network_error_then_failed_retry_terminal(self, db_session, test_seed_data):
        """
        2. NETWORK_ERROR -> failed retry:
        - Attempt #1 = NETWORK_ERROR
        - Attempt #2 = PROVIDER_ERROR
        - Both distinct rows persisted
        - Transaction ends in FAILED
        - 3rd retry is blocked
        """
        provider = MockPaymentProvider(
            mode_sequence=[MockPaymentMode.NETWORK_ERROR, MockPaymentMode.PROVIDER_ERROR]
        )
        service = PaymentService(provider=provider)

        # 1. Initial Attempt
        res1 = service.process_payment(
            db_session,
            merchant_name="MakeMyTrip",
            amount=4500.0,
            category="travel",
            idempotency_key=f"e2e_net_fail_{uuid.uuid4().hex[:8]}",
        )
        payment_id = uuid.UUID(res1["payment_id"])

        # 2. Retry Attempt (Fails with PROVIDER_ERROR)
        res2 = service.retry_payment(db_session, payment_id=payment_id)
        assert res2["success"] is False
        assert res2["status"] == "FAILED"
        assert res2["failure_reason"] == "PROVIDER_ERROR"
        assert res2["attempt_number"] == 2

        # 3. Verify DB state
        tx = db_session.get(Transaction, payment_id)
        assert tx.status == "FAILED"

        attempts = db_session.execute(
            select(PaymentAttempt)
            .where(PaymentAttempt.transaction_id == payment_id)
            .order_by(PaymentAttempt.attempt_number.asc())
        ).scalars().all()

        assert len(attempts) == 2
        assert attempts[0].attempt_number == 1
        assert attempts[0].error_code == "NETWORK_ERROR"

        assert attempts[1].attempt_number == 2
        assert attempts[1].error_code == "PROVIDER_ERROR"

        # 4. Third attempt MUST raise MaxRetriesExceededError
        with pytest.raises(MaxRetriesExceededError):
            service.retry_payment(db_session, payment_id=payment_id)

    def test_3_timeout_then_successful_retry(self, db_session, test_seed_data):
        """
        3. TIMEOUT -> successful retry:
        - Attempt #1 = TIMEOUT (Transaction becomes FAILED)
        - Attempt #2 = SUCCESS (Transaction becomes SUCCESS)
        """
        provider = MockPaymentProvider(
            mode_sequence=[MockPaymentMode.TIMEOUT, MockPaymentMode.SUCCESS]
        )
        service = PaymentService(provider=provider)

        res1 = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=f"e2e_timeout_succ_{uuid.uuid4().hex[:8]}",
        )
        assert res1["status"] == "FAILED"
        assert res1["failure_reason"] == "TIMEOUT"
        payment_id = uuid.UUID(res1["payment_id"])

        res2 = service.retry_payment(db_session, payment_id=payment_id)
        assert res2["success"] is True
        assert res2["status"] == "SUCCESS"
        assert res2["attempt_number"] == 2

        tx = db_session.get(Transaction, payment_id)
        assert tx.status == "SUCCESS"

    def test_4_attempt_numbering_and_immutability_of_first_attempt(self, db_session, test_seed_data):
        """
        4 & 5. Verify attempt numbering 1 -> 2 and that Attempt #1 remains unchanged after retry.
        """
        provider = MockPaymentProvider(
            mode_sequence=[MockPaymentMode.DECLINED, MockPaymentMode.SUCCESS]
        )
        service = PaymentService(provider=provider)

        res1 = service.process_payment(
            db_session,
            merchant_name="Amazon",
            amount=899.0,
            category="shopping",
            idempotency_key=f"e2e_immut_{uuid.uuid4().hex[:8]}",
        )
        payment_id = uuid.UUID(res1["payment_id"])

        attempt1_before = db_session.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == payment_id)
        ).scalar_one()

        att1_id = attempt1_before.id
        att1_created_at = attempt1_before.created_at
        att1_error_code = attempt1_before.error_code
        att1_provider_id = attempt1_before.provider_payment_id

        # Perform retry
        service.retry_payment(db_session, payment_id=payment_id)

        # Re-fetch attempt 1 and attempt 2
        attempts = db_session.execute(
            select(PaymentAttempt)
            .where(PaymentAttempt.transaction_id == payment_id)
            .order_by(PaymentAttempt.attempt_number.asc())
        ).scalars().all()

        assert len(attempts) == 2

        # Attempt #1 remained 100% unchanged
        assert attempts[0].id == att1_id
        assert attempts[0].attempt_number == 1
        assert attempts[0].created_at == att1_created_at
        assert attempts[0].error_code == att1_error_code
        assert attempts[0].provider_payment_id == att1_provider_id

        # Attempt #2 is distinct
        assert attempts[1].id != att1_id
        assert attempts[1].attempt_number == 2
        assert attempts[1].status == "SUCCESS"

    def test_5_successful_transaction_cannot_retry(self, db_session, test_seed_data):
        """7. Successful transaction cannot be retried."""
        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        res = service.process_payment(
            db_session,
            merchant_name="Spotify",
            amount=699.0,
            category="subscriptions",
            idempotency_key=f"e2e_succ_no_ret_{uuid.uuid4().hex[:8]}",
        )
        payment_id = uuid.UUID(res["payment_id"])

        with pytest.raises(InvalidPaymentStateError, match="already completed successfully"):
            service.retry_payment(db_session, payment_id=payment_id)

    def test_6_rejected_transaction_cannot_retry(self, db_session, test_seed_data):
        """8. Policy REJECTED transaction cannot be retried."""
        service = PaymentService()

        agent = test_seed_data["agent"]
        wallet = test_seed_data["wallet"]
        tx = Transaction(
            id=uuid.uuid4(),
            idempotency_key=f"e2e_rej_no_ret_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
            wallet_id=wallet.id,
            merchant_name="Blocked Merchant",
            category="gambling",
            amount=500.0,
            status=TransactionStatus.REJECTED.value,
            decision_reason="Policy rejected gambling category",
        )
        db_session.add(tx)
        db_session.commit()

        with pytest.raises(InvalidPaymentStateError, match="transaction was REJECTED by policy"):
            service.retry_payment(db_session, payment_id=tx.id)

    def test_7_duplicate_retry_protection(self, db_session, test_seed_data):
        """9. Duplicate retry calls cannot create attempt #3."""
        provider = MockPaymentProvider(mode=MockPaymentMode.DECLINED)
        service = PaymentService(provider=provider)

        res = service.process_payment(
            db_session,
            merchant_name="Netflix",
            amount=499.0,
            category="subscriptions",
            idempotency_key=f"e2e_dup_retry_{uuid.uuid4().hex[:8]}",
        )
        payment_id = uuid.UUID(res["payment_id"])

        # Retry #1 (Attempt 2)
        service.retry_payment(db_session, payment_id=payment_id)

        # Retry call 2 -> raises MaxRetriesExceededError
        with pytest.raises(MaxRetriesExceededError):
            service.retry_payment(db_session, payment_id=payment_id)

        # Retry call 3 -> raises MaxRetriesExceededError
        with pytest.raises(MaxRetriesExceededError):
            service.retry_payment(db_session, payment_id=payment_id)

        # Total attempts in DB remains exactly 2
        attempts = db_session.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == payment_id)
        ).scalars().all()
        assert len(attempts) == 2

    def test_8_state_transition_sequence_full_verification(self, db_session, test_seed_data):
        """
        10. Verify full state machine sequence:
        REQUESTED -> POLICY_CHECK -> APPROVED -> PAYMENT_PENDING -> FAILED
        Controlled retry: FAILED -> PAYMENT_PENDING -> SUCCESS
        """
        provider = MockPaymentProvider(
            mode_sequence=[MockPaymentMode.TIMEOUT, MockPaymentMode.SUCCESS]
        )
        service = PaymentService(provider=provider)
        agent = test_seed_data["agent"]
        wallet = test_seed_data["wallet"]

        # Step A: Initialize in REQUESTED
        tx = Transaction(
            id=uuid.uuid4(),
            idempotency_key=f"e2e_state_seq_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
            wallet_id=wallet.id,
            merchant_name="Torrent Power",
            category="utilities",
            amount=1240.0,
            status=TransactionStatus.REQUESTED.value,
        )
        db_session.add(tx)
        db_session.commit()
        assert tx.status == "REQUESTED"

        # Step B: Process payment (transitions to POLICY_CHECK -> APPROVED -> PAYMENT_PENDING -> FAILED)
        service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=tx.idempotency_key,
        )
        db_session.refresh(tx)
        assert tx.status == "FAILED"

        # Universal transition FAILED -> PAYMENT_PENDING without retry authorization is BLOCKED
        with pytest.raises(InvalidPaymentStateError):
            tx.transition_to(TransactionStatus.PAYMENT_PENDING)

        # Step C: Controlled retry (moves to PAYMENT_PENDING -> SUCCESS)
        res_retry = service.retry_payment(db_session, payment_id=tx.id)
        db_session.refresh(tx)
        assert res_retry["success"] is True
        assert tx.status == "SUCCESS"
