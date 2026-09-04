import uuid
import pytest
from sqlalchemy import select
from app.services.payment_adapter import (
    PaymentProvider,
    MockPaymentProvider,
    MockPaymentMode,
    PaymentExecutionRequest,
    PaymentExecutionResult,
)
from app.services.payment_service import (
    PaymentService,
    PolicyViolationError,
    InvalidPaymentStateError,
)
from app.models.transaction import Transaction
from app.models.audit_log import AuditLog


class SpyPaymentProvider(PaymentProvider):
    """Spy provider to verify that calls never reach the provider when policy denies."""
    def __init__(self):
        self.create_payment_called = False
        self.retry_called = False
        self.get_status_called = False

    def create_payment(self, request: PaymentExecutionRequest) -> PaymentExecutionResult:
        self.create_payment_called = True
        return PaymentExecutionResult(
            success=True,
            status="SUCCESS",
            payment_id=request.transaction_id,
            provider_payment_id="spy_pay_123",
            amount=request.amount,
            currency=request.currency,
            attempt_number=request.attempt_number,
        )

    def get_status(self, provider_payment_id: str) -> PaymentExecutionResult:
        self.get_status_called = True
        return PaymentExecutionResult(
            success=True,
            status="SUCCESS",
            payment_id="spy_id",
            provider_payment_id=provider_payment_id,
            amount=100.0,
            currency="INR",
            attempt_number=1,
        )

    def retry(self, request: PaymentExecutionRequest) -> PaymentExecutionResult:
        self.retry_called = True
        return self.create_payment(request)


class TestPaymentProviderAndService:
    def test_1_mock_payment_provider_success_mode(self):
        """1. Verify SUCCESS mode in MockPaymentProvider."""
        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        req = PaymentExecutionRequest(
            transaction_id="tx_101",
            idempotency_key="idemp_101",
            amount=1240.0,
            currency="INR",
            merchant_name="Torrent Power",
            category="utilities",
        )
        result = provider.create_payment(req)

        assert result.success is True
        assert result.status == "SUCCESS"
        assert result.provider_payment_id.startswith("pay_mock_")
        assert result.amount == 1240.0
        assert result.attempt_number == 1
        assert provider.call_count == 1

    def test_2_mock_payment_provider_fail_mode(self):
        """2. Verify FAIL mode in MockPaymentProvider."""
        provider = MockPaymentProvider(
            mode=MockPaymentMode.FAIL,
            failure_reason="Insufficient balance at issuing bank",
        )
        req = PaymentExecutionRequest(
            transaction_id="tx_102",
            idempotency_key="idemp_102",
            amount=3000.0,
            currency="INR",
            merchant_name="Netflix",
            category="subscriptions",
        )
        result = provider.create_payment(req)

        assert result.success is False
        assert result.status == "FAILED"
        assert result.error_code in ["DECLINED", "GATEWAY_REJECTED"]
        assert "Insufficient balance" in result.error_message
        assert provider.call_count == 1

    def test_3_mock_payment_provider_timeout_mode(self):
        """3. Verify TIMEOUT mode in MockPaymentProvider."""
        provider = MockPaymentProvider(mode=MockPaymentMode.TIMEOUT)
        req = PaymentExecutionRequest(
            transaction_id="tx_103",
            idempotency_key="idemp_103",
            amount=699.0,
            currency="INR",
            merchant_name="Spotify",
            category="subscriptions",
        )
        result = provider.create_payment(req)

        assert result.success is False
        assert result.status == "TIMEOUT"
        assert result.error_code in ["TIMEOUT", "GATEWAY_TIMEOUT"]
        assert "timed out" in result.error_message.lower()
        assert provider.call_count == 1

    def test_4_payment_service_process_allowed_payment(self, db_session, test_seed_data):
        """Verify PaymentService executes allowed payments and persists status SUCCESS."""
        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        result = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=f"test_ps_{uuid.uuid4().hex[:8]}",
        )

        assert result["success"] is True
        assert result["status"] == "SUCCESS"
        assert result["decision"] == "ALLOWED"
        assert provider.call_count == 1

        # Verify DB transaction record
        tx = db_session.get(Transaction, uuid.UUID(result["payment_id"]))
        assert tx is not None
        assert tx.status == "SUCCESS"
        assert tx.amount == 1240.0

    def test_5_payment_service_blocks_denied_policy_invariant(self, db_session, test_seed_data):
        """
        CRITICAL SECURITY INVARIANT:
        When policy engine returns DENIED, PaymentService must NEVER invoke PaymentProvider.
        """
        spy_provider = SpyPaymentProvider()
        service = PaymentService(provider=spy_provider)

        # Attempt ₹9,500 transaction (policy limit is ₹8,000)
        with pytest.raises(PolicyViolationError) as exc_info:
            service.process_payment(
                db_session,
                merchant_name="MakeMyTrip",
                amount=9500.0,
                category="travel",
                idempotency_key="test_over_limit_key",
            )

        # 1. Error raised with correct decision code
        assert "TX_LIMIT_EXCEEDED" in exc_info.value.decision_code or "MULTIPLE" in exc_info.value.decision_code

        # 2. Invariant verified: Provider was NEVER touched!
        assert spy_provider.create_payment_called is False
        assert spy_provider.retry_called is False

    def test_6_payment_service_retry_failed_and_timeout_payments(self, db_session, test_seed_data):
        """4. Verify safe retry behavior for FAILED and TIMEOUT payments."""
        # 1. First trigger a FAILED payment
        failing_provider = MockPaymentProvider(mode=MockPaymentMode.FAIL)
        service = PaymentService(provider=failing_provider)
        res_fail = service.process_payment(
            db_session,
            merchant_name="Spotify",
            amount=699.0,
            category="subscriptions",
            idempotency_key=f"test_retry_fail_{uuid.uuid4().hex[:8]}",
        )
        assert res_fail["status"] == "FAILED"
        payment_id = uuid.UUID(res_fail["payment_id"])

        # 2. Retry the failed payment with SUCCESS provider
        working_provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        retry_service = PaymentService(provider=working_provider)
        retry_result = retry_service.retry_payment(db_session, payment_id=payment_id)

        assert retry_result["success"] is True
        assert retry_result["status"] == "SUCCESS"
        assert retry_result["attempt_number"] == 2

        # 3. Verify DB record transitioned to SUCCESS
        tx = db_session.get(Transaction, payment_id)
        assert tx.status == "SUCCESS"

    def test_7_prevent_retry_and_duplicate_payment_after_success(self, db_session, test_seed_data):
        """5. Verify a SUCCESS payment cannot be retried or duplicate processed."""
        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)
        idemp_key = f"test_succ_dup_{uuid.uuid4().hex[:8]}"

        # 1. Initial successful payment
        result1 = service.process_payment(
            db_session,
            merchant_name="Netflix",
            amount=499.0,
            category="subscriptions",
            idempotency_key=idemp_key,
        )
        assert result1["success"] is True
        assert result1["status"] == "SUCCESS"
        payment_id = uuid.UUID(result1["payment_id"])

        # 2. Attempting to retry the successful payment must raise InvalidPaymentStateError
        with pytest.raises(InvalidPaymentStateError) as exc_info:
            service.retry_payment(db_session, payment_id=payment_id)
        assert "already completed successfully" in str(exc_info.value)

        # 3. Calling process_payment with same idempotency key returns idempotent response without calling provider again
        initial_calls = provider.call_count
        result_idempotent = service.process_payment(
            db_session,
            merchant_name="Netflix",
            amount=499.0,
            category="subscriptions",
            idempotency_key=idemp_key,
        )
        assert result_idempotent["status"] == "SUCCESS"
        assert result_idempotent["payment_id"] == str(payment_id)
        assert provider.call_count == initial_calls  # Provider was NOT invoked again

    def test_8_payment_status_retrieval_and_audit_logs(self, db_session, test_seed_data):
        """7 & 8. Verify payment status retrieval and comprehensive AuditLog recording."""
        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        result = service.process_payment(
            db_session,
            merchant_name="Amazon",
            amount=899.0,
            category="shopping",
            idempotency_key=f"test_audit_status_{uuid.uuid4().hex[:8]}",
        )
        payment_id = uuid.UUID(result["payment_id"])

        # Test structured status retrieval
        status_info = service.get_payment_status(db_session, payment_id)
        assert status_info["payment_id"] == str(payment_id)
        assert status_info["status"] == "SUCCESS"
        assert status_info["amount"] == 899.0
        assert status_info["attempt"] >= 1
        assert status_info["provider_payment_id"] is not None

        # Verify provider.get_status
        provider_status = provider.get_status(status_info["provider_payment_id"])
        assert provider_status.status == "SUCCESS"
        assert provider_status.provider_payment_id == status_info["provider_payment_id"]

        # Verify AuditLog entries in DB
        logs = db_session.execute(
            select(AuditLog)
            .where(AuditLog.transaction_id == payment_id)
            .order_by(AuditLog.created_at.asc())
        ).scalars().all()

        event_types = [l.event_type for l in logs]
        assert "PAYMENT_ATTEMPT" in event_types
        assert "PAYMENT_RESULT" in event_types
