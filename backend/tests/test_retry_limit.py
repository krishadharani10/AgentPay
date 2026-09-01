"""
Day 3 Phase 1 Step 5: Explicit Retry Limit (MAX_RETRIES = 1) Tests
Verifies that:
1. MAX_RETRIES = 1 is strictly enforced.
2. Source of truth is persisted PaymentAttempt records in the database.
3. Maximum total provider attempts per transaction is 2 (attempt 1 + attempt 2).
4. Any 3rd attempt is rejected with MaxRetriesExceededError.
5. Successful and Policy-Rejected transactions cannot be retried.
6. Attempt numbers are strictly 1 and 2, never 3.
7. Retries work across different failure reasons (NETWORK_ERROR, TIMEOUT, DECLINED).
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


class TestRetryLimitAndAttemptGuards:
    """Test suite for MAX_RETRIES = 1 enforcement and PaymentAttempt lifecycle."""

    def test_authoritative_constant_value(self):
        """Verify MAX_RETRIES constant is authoritative and set to 1."""
        assert MAX_RETRIES == 1

    def test_1_successful_first_attempt_no_retry_created(self, db_session, test_seed_data):
        """Test 1: Attempt #1 -> SUCCESS. Transaction is complete, no retry is created."""
        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        result = service.process_payment(
            db_session,
            merchant_name="Netflix",
            amount=499.0,
            category="subscriptions",
            idempotency_key=f"tx_succ_init_{uuid.uuid4().hex[:8]}",
        )

        assert result["success"] is True
        assert result["status"] == "SUCCESS"
        payment_id = uuid.UUID(result["payment_id"])

        # Check DB PaymentAttempt records
        attempts = db_session.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == payment_id)
        ).scalars().all()

        assert len(attempts) == 1
        assert attempts[0].attempt_number == 1
        assert attempts[0].status == "SUCCESS"

    def test_2_first_failure_then_successful_retry(self, db_session, test_seed_data):
        """Test 2: Attempt #1 -> FAILED, Retry Attempt #2 -> SUCCESS. Transaction ends in SUCCESS."""
        # 1. Initial attempt fails with NETWORK_ERROR
        failing_provider = MockPaymentProvider(mode=MockPaymentMode.NETWORK_ERROR)
        service1 = PaymentService(provider=failing_provider)
        res1 = service1.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=f"tx_fail_retry_succ_{uuid.uuid4().hex[:8]}",
        )

        assert res1["success"] is False
        assert res1["status"] == "FAILED"
        payment_id = uuid.UUID(res1["payment_id"])

        # 2. Retry with SUCCESS provider
        working_provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service2 = PaymentService(provider=working_provider)
        res2 = service2.retry_payment(db_session, payment_id=payment_id)

        assert res2["success"] is True
        assert res2["status"] == "SUCCESS"
        assert res2["attempt_number"] == 2

        # 3. Verify DB state: Transaction is SUCCESS, exactly 2 attempts persisted
        tx = db_session.get(Transaction, payment_id)
        assert tx.status == "SUCCESS"

        attempts = db_session.execute(
            select(PaymentAttempt)
            .where(PaymentAttempt.transaction_id == payment_id)
            .order_by(PaymentAttempt.attempt_number.asc())
        ).scalars().all()

        assert len(attempts) == 2
        assert attempts[0].attempt_number == 1
        assert attempts[0].status == "FAILED"
        assert attempts[0].error_code == "NETWORK_ERROR"

        assert attempts[1].attempt_number == 2
        assert attempts[1].status == "SUCCESS"
        assert attempts[1].error_code is None

    def test_3_first_failure_then_failed_retry_terminal(self, db_session, test_seed_data):
        """Test 3: Attempt #1 -> FAILED, Retry Attempt #2 -> FAILED. Transaction ends FAILED. 3rd attempt rejected."""
        # 1. Initial attempt fails
        provider = MockPaymentProvider(mode=MockPaymentMode.DECLINED)
        service = PaymentService(provider=provider)
        res1 = service.process_payment(
            db_session,
            merchant_name="Amazon",
            amount=899.0,
            category="shopping",
            idempotency_key=f"tx_fail_fail_{uuid.uuid4().hex[:8]}",
        )
        payment_id = uuid.UUID(res1["payment_id"])

        # 2. Retry #1 (Attempt #2) also fails
        res2 = service.retry_payment(db_session, payment_id=payment_id)
        assert res2["success"] is False
        assert res2["status"] == "FAILED"
        assert res2["attempt_number"] == 2

        # 3. Third attempt MUST be rejected with MaxRetriesExceededError
        with pytest.raises(MaxRetriesExceededError) as exc_info:
            service.retry_payment(db_session, payment_id=payment_id)

        assert "retry limit reached" in str(exc_info.value).lower()

        # Verify DB: exactly 2 attempts exist, NEVER 3
        attempts = db_session.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == payment_id)
        ).scalars().all()
        assert len(attempts) == 2

    def test_4_retry_limit_max_retries_exceeded_error(self, db_session, test_seed_data):
        """Test 4: After two total attempts, retry raises MaxRetriesExceededError and creates no PaymentAttempt #3."""
        provider = MockPaymentProvider(mode=MockPaymentMode.PROVIDER_ERROR)
        service = PaymentService(provider=provider)

        res = service.process_payment(
            db_session,
            merchant_name="MakeMyTrip",
            amount=4500.0,
            category="travel",
            idempotency_key=f"tx_limit_test_{uuid.uuid4().hex[:8]}",
        )
        payment_id = uuid.UUID(res["payment_id"])

        # First retry (Attempt 2)
        service.retry_payment(db_session, payment_id=payment_id)

        # Second retry (Attempt 3) -> rejected
        with pytest.raises(MaxRetriesExceededError):
            service.retry_payment(db_session, payment_id=payment_id)

        # Subsequent retry call -> still rejected
        with pytest.raises(MaxRetriesExceededError):
            service.retry_payment(db_session, payment_id=payment_id)

        # Assert no attempt 3 in DB
        attempts = db_session.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == payment_id)
        ).scalars().all()
        assert len(attempts) == 2
        assert [a.attempt_number for a in attempts] == [1, 2]

    def test_5_successful_transaction_cannot_retry(self, db_session, test_seed_data):
        """Test 5: SUCCESS transaction cannot be retried."""
        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        res = service.process_payment(
            db_session,
            merchant_name="Spotify",
            amount=699.0,
            category="subscriptions",
            idempotency_key=f"tx_succ_no_retry_{uuid.uuid4().hex[:8]}",
        )
        payment_id = uuid.UUID(res["payment_id"])

        with pytest.raises(InvalidPaymentStateError, match="already completed successfully"):
            service.retry_payment(db_session, payment_id=payment_id)

    def test_6_rejected_transaction_cannot_retry(self, db_session, test_seed_data):
        """Test 6: REJECTED policy transaction cannot be retried."""
        service = PaymentService()

        agent = test_seed_data["agent"]
        wallet = test_seed_data["wallet"]
        rejected_tx = Transaction(
            id=uuid.uuid4(),
            idempotency_key=f"tx_pol_rej_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
            wallet_id=wallet.id,
            merchant_name="Casino",
            category="gambling",
            amount=10000.0,
            status=TransactionStatus.REJECTED.value,
            decision_reason="Policy rejected gambling category",
        )
        db_session.add(rejected_tx)
        db_session.commit()

        with pytest.raises(InvalidPaymentStateError, match="transaction was REJECTED by policy"):
            service.retry_payment(db_session, payment_id=rejected_tx.id)

    def test_7_retry_uses_persisted_attempt_count_from_db(self, db_session, test_seed_data):
        """Test 7: Retry eligibility is computed directly from persisted PaymentAttempt records in DB."""
        agent = test_seed_data["agent"]
        wallet = test_seed_data["wallet"]
        tx = Transaction(
            id=uuid.uuid4(),
            idempotency_key=f"tx_manual_attempts_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
            wallet_id=wallet.id,
            merchant_name="Netflix",
            category="subscriptions",
            amount=499.0,
            status=TransactionStatus.FAILED.value,
        )
        db_session.add(tx)
        db_session.commit()

        # Manually insert 2 existing attempts in DB
        attempt1 = PaymentAttempt(
            id=uuid.uuid4(),
            transaction_id=tx.id,
            attempt_number=1,
            status="FAILED",
            error_code="TIMEOUT",
        )
        attempt2 = PaymentAttempt(
            id=uuid.uuid4(),
            transaction_id=tx.id,
            attempt_number=2,
            status="FAILED",
            error_code="DECLINED",
        )
        db_session.add_all([attempt1, attempt2])
        db_session.commit()

        service = PaymentService()

        # Service MUST detect 2 attempts in DB and raise MaxRetriesExceededError
        with pytest.raises(MaxRetriesExceededError):
            service.check_retry_eligibility(db_session, tx.id)

    def test_8_attempt_numbering_strictly_1_and_2(self, db_session, test_seed_data):
        """Test 8: Verify attempt numbers are strictly 1 and 2, never #3."""
        provider = MockPaymentProvider(mode=MockPaymentMode.TIMEOUT)
        service = PaymentService(provider=provider)

        res = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=f"tx_numbering_{uuid.uuid4().hex[:8]}",
        )
        payment_id = uuid.UUID(res["payment_id"])

        # Retry once
        service.retry_payment(db_session, payment_id=payment_id)

        # Check attempts
        attempts = db_session.execute(
            select(PaymentAttempt)
            .where(PaymentAttempt.transaction_id == payment_id)
            .order_by(PaymentAttempt.attempt_number.asc())
        ).scalars().all()

        assert len(attempts) == 2
        assert attempts[0].attempt_number == 1
        assert attempts[1].attempt_number == 2

    @pytest.mark.parametrize("failure_mode", [
        MockPaymentMode.NETWORK_ERROR,
        MockPaymentMode.TIMEOUT,
        MockPaymentMode.DECLINED,
    ])
    def test_9_different_failure_reasons_retry_behavior(self, db_session, test_seed_data, failure_mode):
        """Test 9: Verify retry behavior with NETWORK_ERROR, TIMEOUT, and DECLINED."""
        # 1. Initial attempt with specific failure mode
        failing_provider = MockPaymentProvider(mode=failure_mode)
        service1 = PaymentService(provider=failing_provider)

        res1 = service1.process_payment(
            db_session,
            merchant_name="Spotify",
            amount=699.0,
            category="subscriptions",
            idempotency_key=f"tx_reason_{failure_mode.value.lower()}_{uuid.uuid4().hex[:8]}",
        )
        assert res1["status"] == "FAILED"
        payment_id = uuid.UUID(res1["payment_id"])

        # 2. Retry succeeds
        working_provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service2 = PaymentService(provider=working_provider)
        res2 = service2.retry_payment(db_session, payment_id=payment_id)

        assert res2["success"] is True
        assert res2["status"] == "SUCCESS"
        assert res2["attempt_number"] == 2

        # 3. Check DB
        attempts = db_session.execute(
            select(PaymentAttempt)
            .where(PaymentAttempt.transaction_id == payment_id)
            .order_by(PaymentAttempt.attempt_number.asc())
        ).scalars().all()

        assert len(attempts) == 2
        assert attempts[0].error_code == failure_mode.value
        assert attempts[1].status == "SUCCESS"
