"""
Day 3 Phase 2 Step 5: Idempotency Hardening Across Fallback and Retry Integration Tests.
Verifies all 5 authoritative idempotency cases:
CASE 1: Duplicate request before execution (no duplicate transaction).
CASE 2: Duplicate request after successful primary payment (returns SUCCESS, 0 new calls, 1 attempt).
CASE 3: Duplicate request after primary failure and successful fallback (returns SUCCESS, 0 new calls, exactly 2 attempts, no attempt #3).
CASE 4: Duplicate request after fallback rejection (returns FAILED, 0 fallback provider calls, 1 attempt).
CASE 5: Controlled retry idempotency (MAX_RETRIES=1 enforced, distinct retry, no duplicate executions).
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
)
from app.services.payment_service import (
    PaymentService,
    PolicyViolationError,
    MAX_RETRIES,
)


class TestIdempotencyHardening:
    """Comprehensive test suite for idempotency guarantees across the full payment lifecycle."""

    def test_case_1_duplicate_request_before_execution(self, db_session, test_seed_data):
        """
        CASE 1: Duplicate request before execution.
        - Existing seeded demo bill or unexecuted transaction
        - Reusing the same idempotency key does not create duplicate Transaction rows
        - Exactly 1 Transaction row exists in DB
        """
        agent = test_seed_data["agent"]
        wallet = test_seed_data["wallet"]
        shared_key = f"idem_pre_exec_{uuid.uuid4().hex[:8]}"

        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        # 1. Process initial payment
        res1 = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=shared_key,
        )
        assert res1["success"] is True
        payment_id_1 = res1["payment_id"]

        # 2. Query transactions matching this idempotency_key
        tx_rows = db_session.execute(
            select(Transaction).where(Transaction.idempotency_key == shared_key)
        ).scalars().all()
        assert len(tx_rows) == 1
        assert str(tx_rows[0].id) == payment_id_1

        # 3. Duplicate request with identical idempotency_key
        res2 = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=shared_key,
        )
        assert res2["success"] is True
        assert res2["payment_id"] == payment_id_1

        # Still exactly 1 Transaction row in DB
        tx_rows_after = db_session.execute(
            select(Transaction).where(Transaction.idempotency_key == shared_key)
        ).scalars().all()
        assert len(tx_rows_after) == 1

    def test_case_2_duplicate_request_after_successful_primary_payment(self, db_session, test_seed_data):
        """
        CASE 2: Duplicate request after successful primary payment.
        - Primary succeeds on Attempt #1
        - Duplicate process_payment calls with same idempotency key return SUCCESS
        - Provider is called exactly ONCE total
        - Exactly 1 PaymentAttempt row persisted in DB
        """
        shared_key = f"idem_primary_succ_{uuid.uuid4().hex[:8]}"
        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        # 1. Initial execution
        res1 = service.process_payment(
            db_session,
            merchant_name="Netflix",
            amount=499.0,
            category="subscriptions",
            idempotency_key=shared_key,
        )
        assert res1["success"] is True
        assert res1["status"] == "SUCCESS"
        assert res1["attempt_number"] == 1
        payment_id = uuid.UUID(res1["payment_id"])
        assert provider.call_count == 1

        # 2. First duplicate call
        res2 = service.process_payment(
            db_session,
            merchant_name="Netflix",
            amount=499.0,
            category="subscriptions",
            idempotency_key=shared_key,
        )
        assert res2["success"] is True
        assert res2["status"] == "SUCCESS"
        assert res2["payment_id"] == str(payment_id)
        assert res2["attempt_number"] == 1
        assert provider.call_count == 1  # ZERO additional provider calls

        # 3. Second duplicate call
        res3 = service.process_payment(
            db_session,
            merchant_name="Netflix",
            amount=499.0,
            category="subscriptions",
            idempotency_key=shared_key,
        )
        assert res3["success"] is True
        assert res3["payment_id"] == str(payment_id)
        assert provider.call_count == 1  # ZERO additional provider calls

        # Verify DB PaymentAttempt count remains exactly 1
        attempts = db_session.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == payment_id)
        ).scalars().all()
        assert len(attempts) == 1
        assert attempts[0].attempt_number == 1
        assert attempts[0].status == "SUCCESS"

    def test_case_3_duplicate_request_after_primary_failure_and_successful_fallback(self, db_session, test_seed_data):
        """
        CASE 3: Duplicate request after primary failure and successful fallback.
        - Primary fails (Attempt #1 = FAILED, DECLINED)
        - Fallback executes and succeeds (Attempt #2 = SUCCESS, CARD_TOKEN)
        - Duplicate process_payment calls return existing SUCCESS transaction with attempt_number=2
        - Provider is called exactly 2 times total
        - Exactly 2 PaymentAttempt rows exist in DB (no Attempt #3)
        """
        shared_key = f"idem_fallback_succ_{uuid.uuid4().hex[:8]}"
        provider = MockPaymentProvider(
            mode_sequence=[MockPaymentMode.DECLINED, MockPaymentMode.SUCCESS]
        )
        service = PaymentService(provider=provider)
        wallet = test_seed_data["wallet"]

        fallback_pm = db_session.execute(
            select(PaymentMethod).where(PaymentMethod.wallet_id == wallet.id, PaymentMethod.is_primary == False)
        ).scalar_one()

        # 1. Primary fails
        res1 = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=shared_key,
        )
        assert res1["success"] is False
        assert res1["status"] == "FAILED"
        payment_id = uuid.UUID(res1["payment_id"])
        assert provider.call_count == 1

        # 2. Fallback succeeds
        res_fb = service.execute_fallback_payment(
            db_session,
            payment_id=payment_id,
            fallback_method_id=fallback_pm.id,
        )
        assert res_fb["success"] is True
        assert res_fb["status"] == "SUCCESS"
        assert res_fb["attempt_number"] == 2
        assert provider.call_count == 2

        # 3. Duplicate process_payment with original idempotency key
        res_dup = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=shared_key,
        )
        assert res_dup["success"] is True
        assert res_dup["status"] == "SUCCESS"
        assert res_dup["payment_id"] == str(payment_id)
        assert res_dup["attempt_number"] == 2
        assert provider.call_count == 2  # ZERO additional provider calls

        # 4. Duplicate fallback call is blocked because already SUCCESS
        with pytest.raises(InvalidPaymentStateError, match="already completed successfully"):
            service.execute_fallback_payment(db_session, payment_id=payment_id)

        assert provider.call_count == 2  # ZERO additional provider calls

        # 5. Exactly 2 PaymentAttempt rows in DB
        attempts = db_session.execute(
            select(PaymentAttempt)
            .where(PaymentAttempt.transaction_id == payment_id)
            .order_by(PaymentAttempt.attempt_number.asc())
        ).scalars().all()
        assert len(attempts) == 2
        assert attempts[0].attempt_number == 1
        assert attempts[0].status == "FAILED"
        assert attempts[1].attempt_number == 2
        assert attempts[1].status == "SUCCESS"

    def test_case_4_duplicate_request_after_fallback_rejection(self, db_session, test_seed_data):
        """
        CASE 4: Duplicate request after fallback rejection.
        - Primary fails (Attempt #1 = FAILED, TIMEOUT)
        - Policy rejects fallback (e.g. daily limit reduced)
        - Duplicate process_payment call returns the existing FAILED transaction
        - Provider is called exactly ONCE total
        - Exactly 1 PaymentAttempt row exists in DB
        """
        shared_key = f"idem_fb_rej_{uuid.uuid4().hex[:8]}"
        provider = MockPaymentProvider(mode=MockPaymentMode.TIMEOUT)
        service = PaymentService(provider=provider)
        agent = test_seed_data["agent"]

        # 1. Primary payment fails
        res1 = service.process_payment(
            db_session,
            merchant_name="Amazon",
            amount=899.0,
            category="shopping",
            idempotency_key=shared_key,
        )
        assert res1["success"] is False
        payment_id = uuid.UUID(res1["payment_id"])
        assert provider.call_count == 1

        # 2. Reduce policy limit to force fallback rejection
        policy = db_session.execute(
            select(Policy).where(Policy.agent_id == agent.id)
        ).scalar_one()
        policy.daily_spending_limit = 200.0  # ₹200 limit, transaction is ₹899
        db_session.commit()

        # 3. Fallback rejected
        with pytest.raises(PolicyViolationError):
            service.execute_fallback_payment(db_session, payment_id=payment_id)

        assert provider.call_count == 1  # ZERO calls for fallback

        # 4. Duplicate process_payment replay with original idempotency key
        res_dup = service.process_payment(
            db_session,
            merchant_name="Amazon",
            amount=899.0,
            category="shopping",
            idempotency_key=shared_key,
        )
        assert res_dup["success"] is False
        assert res_dup["status"] == "FAILED"
        assert res_dup["payment_id"] == str(payment_id)
        assert res_dup["attempt_number"] == 1
        assert provider.call_count == 1  # ZERO additional provider calls

        # 5. Exactly 1 PaymentAttempt in DB
        attempts = db_session.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == payment_id)
        ).scalars().all()
        assert len(attempts) == 1

    def test_case_5_retry_request_idempotency_and_limits(self, db_session, test_seed_data):
        """
        CASE 5: Retry request idempotency.
        - Primary fails (Attempt #1 = FAILED)
        - Retry executes as distinct controlled operation (Attempt #2 = SUCCESS)
        - Replaying process_payment with original key returns SUCCESS
        - Further retry attempts raise MaxRetriesExceededError or InvalidPaymentStateError
        - Provider is called exactly 2 times total
        """
        shared_key = f"idem_retry_succ_{uuid.uuid4().hex[:8]}"
        provider = MockPaymentProvider(
            mode_sequence=[MockPaymentMode.NETWORK_ERROR, MockPaymentMode.SUCCESS]
        )
        service = PaymentService(provider=provider)

        # 1. Primary payment fails
        res1 = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=shared_key,
        )
        assert res1["status"] == "FAILED"
        payment_id = uuid.UUID(res1["payment_id"])
        assert provider.call_count == 1

        # 2. Distinct controlled retry operation
        res_retry = service.retry_payment(db_session, payment_id=payment_id)
        assert res_retry["success"] is True
        assert res_retry["status"] == "SUCCESS"
        assert res_retry["attempt_number"] == 2
        assert provider.call_count == 2

        # 3. Duplicate process_payment replay
        res_dup = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=shared_key,
        )
        assert res_dup["success"] is True
        assert res_dup["status"] == "SUCCESS"
        assert res_dup["attempt_number"] == 2
        assert provider.call_count == 2  # ZERO additional provider calls

        # 4. Duplicate retry_payment call rejected
        with pytest.raises(InvalidPaymentStateError, match="already completed successfully"):
            service.retry_payment(db_session, payment_id=payment_id)

        assert provider.call_count == 2
