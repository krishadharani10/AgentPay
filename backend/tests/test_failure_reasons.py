"""
Day 3 Phase 1 Step 4: Payment Failure Reasons & Attempt Persistence Tests
Verifies the complete failure-reason infrastructure across all 5 modes:
DECLINED, TIMEOUT, NETWORK_ERROR, PROVIDER_ERROR, INSUFFICIENT_FUNDS,
and verifies PaymentAttempt persistence and state machine transitions.
"""
import uuid
import pytest
from sqlalchemy import select

from app.models.transaction import Transaction, TransactionStatus
from app.models.payment_attempt import PaymentAttempt
from app.services.payment_adapter import (
    MockPaymentProvider,
    MockPaymentMode,
    PaymentFailureReason,
    PaymentExecutionRequest,
    PaymentExecutionResult,
)
from app.services.payment_service import PaymentService


class TestPaymentFailureReasonsAndPersistence:
    """Test suite covering all 5 failure modes and PaymentAttempt persistence."""

    FAILURE_MODES = [
        (MockPaymentMode.DECLINED, "DECLINED"),
        (MockPaymentMode.TIMEOUT, "TIMEOUT"),
        (MockPaymentMode.NETWORK_ERROR, "NETWORK_ERROR"),
        (MockPaymentMode.PROVIDER_ERROR, "PROVIDER_ERROR"),
        (MockPaymentMode.INSUFFICIENT_FUNDS, "INSUFFICIENT_FUNDS"),
    ]

    @pytest.mark.parametrize("mode,expected_reason", FAILURE_MODES)
    def test_mock_provider_deterministic_failure_modes(self, mode, expected_reason):
        """1. Mock Provider produces the requested deterministic result for all 5 failure reasons."""
        provider = MockPaymentProvider(mode=mode)
        req = PaymentExecutionRequest(
            transaction_id="tx_test_001",
            idempotency_key=f"idemp_{expected_reason.lower()}",
            amount=1240.0,
            currency="INR",
            merchant_name="Torrent Power",
            category="utilities",
        )
        result: PaymentExecutionResult = provider.create_payment(req)

        assert result.success is False
        assert result.error_code == expected_reason
        assert result.provider_payment_id.startswith("pay_mock_")
        assert result.error_message is not None
        assert result.raw_response is not None
        assert result.raw_response.get("failure_reason") == expected_reason

    @pytest.mark.parametrize("mode,expected_reason", FAILURE_MODES)
    def test_payment_service_recognizes_and_persists_failure_reasons(
        self, db_session, test_seed_data, mode, expected_reason
    ):
        """
        2. PaymentService recognizes the correct failure reason.
        3. PaymentAttempt persists the correct failure reason.
        4. Transaction transitions from PAYMENT_PENDING -> FAILED.
        5. No successful payment is recorded.
        """
        provider = MockPaymentProvider(mode=mode)
        service = PaymentService(provider=provider)
        idemp_key = f"test_fail_{expected_reason.lower()}_{uuid.uuid4().hex[:8]}"

        result = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=idemp_key,
        )

        # 1. PaymentService result check
        assert result["success"] is False
        assert result["status"] == TransactionStatus.FAILED.value
        assert result["failure_reason"] == expected_reason
        assert result["error_code"] == expected_reason
        payment_id = uuid.UUID(result["payment_id"])

        # 2. Transaction status check: must be FAILED, not SUCCESS
        tx = db_session.get(Transaction, payment_id)
        assert tx is not None
        assert tx.status == TransactionStatus.FAILED.value
        assert tx.provider_payment_id is not None
        assert expected_reason in tx.decision_reason

        # 3. PaymentAttempt persistence check: exactly 1 attempt persisted with failure details
        attempts = db_session.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == payment_id)
        ).scalars().all()

        assert len(attempts) == 1
        attempt = attempts[0]
        assert attempt.attempt_number == 1
        assert attempt.status == "FAILED"
        assert attempt.error_code == expected_reason
        assert attempt.error_message is not None
        assert attempt.response_payload is not None
        assert attempt.provider_payment_id == result["provider_payment_id"]

        # 4. Relationship access from Transaction
        assert len(tx.payment_attempts) == 1
        assert tx.payment_attempts[0].error_code == expected_reason

    def test_network_error_specifically(self, db_session, test_seed_data):
        """Specifically verify NETWORK_ERROR as mandated by requirements."""
        provider = MockPaymentProvider(mode=MockPaymentMode.NETWORK_ERROR)
        service = PaymentService(provider=provider)

        result = service.process_payment(
            db_session,
            merchant_name="Netflix",
            amount=499.0,
            category="subscriptions",
            idempotency_key=f"net_err_{uuid.uuid4().hex[:8]}",
        )

        assert result["success"] is False
        assert result["status"] == "FAILED"
        assert result["failure_reason"] == "NETWORK_ERROR"

        payment_id = uuid.UUID(result["payment_id"])
        attempt = db_session.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == payment_id)
        ).scalar_one()

        assert attempt.error_code == "NETWORK_ERROR"
        assert "network" in attempt.error_message.lower()

    def test_success_mode_persists_successful_payment_attempt(self, db_session, test_seed_data):
        """Verify SUCCESS mode still works and creates a successful PaymentAttempt."""
        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        result = service.process_payment(
            db_session,
            merchant_name="Spotify",
            amount=699.0,
            category="subscriptions",
            idempotency_key=f"succ_test_{uuid.uuid4().hex[:8]}",
        )

        assert result["success"] is True
        assert result["status"] == TransactionStatus.SUCCESS.value
        assert result["failure_reason"] is None

        payment_id = uuid.UUID(result["payment_id"])
        tx = db_session.get(Transaction, payment_id)
        assert tx.status == TransactionStatus.SUCCESS.value

        attempts = db_session.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == payment_id)
        ).scalars().all()

        assert len(attempts) == 1
        attempt = attempts[0]
        assert attempt.attempt_number == 1
        assert attempt.status == "SUCCESS"
        assert attempt.error_code is None
        assert attempt.provider_payment_id == result["provider_payment_id"]

    def test_payment_failure_reason_enum_values(self):
        """Verify PaymentFailureReason enum contains all required failure types."""
        expected_values = {
            "DECLINED",
            "TIMEOUT",
            "NETWORK_ERROR",
            "PROVIDER_ERROR",
            "INSUFFICIENT_FUNDS",
        }
        actual_values = {r.value for r in PaymentFailureReason}
        assert actual_values == expected_values
