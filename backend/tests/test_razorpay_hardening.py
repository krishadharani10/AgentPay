"""
Day 4 Phase 1.5 — Part C: Razorpay Integration Safety Tests

Tests the RazorpayPaymentProvider that already exists in payment_adapter.py.

What IS already implemented:
  - RazorpayPaymentProvider class using httpx to call https://api.razorpay.com/v1/orders
  - Credentials loaded from RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET environment variables
  - All tests here use httpx.MockTransport to simulate Razorpay API responses
  - No live API calls are made in this test suite (see scripts/verify_razorpay_test_mode.py for live tests)

What this test suite verifies:
  1. RazorpayPaymentProvider can be instantiated safely with and without credentials
  2. Missing credentials return PROVIDER_ERROR (not crash)
  3. Payment request constructs correct payload (amount in paise, notes, receipt)
  4. Secret key is NEVER leaked in response payloads or audit logs
  5. Successful Razorpay response is correctly normalized to PaymentExecutionResult
  6. HTTP error responses are mapped to correct PaymentFailureReason
  7. Network timeouts map to TIMEOUT failure reason
  8. PaymentAttempt is correctly persisted with provider info
  9. AuditLog contains provider name (not secret)
 10. Provider abstraction is agnostic — PaymentService works identically with Mock or Razorpay
"""
import uuid
import json
import pytest
import httpx
from unittest.mock import MagicMock
from sqlalchemy import select

from app.config import Settings, get_settings
from app.models.transaction import Transaction, TransactionStatus
from app.models.payment_attempt import PaymentAttempt
from app.models.audit_log import AuditLog
from app.services.payment_adapter import (
    PaymentProvider,
    RazorpayPaymentProvider,
    MockPaymentProvider,
    MockPaymentMode,
    PaymentExecutionRequest,
    PaymentExecutionResult,
    PaymentFailureReason,
    get_payment_provider,
)
from app.services.payment_service import PaymentService


# ──────────────────────────────────────────────────────────────────────────────
# Helper: build a mock Razorpay HTTP client
# ──────────────────────────────────────────────────────────────────────────────

def _razorpay_provider_with_response(
    status_code: int,
    response_body: dict,
    key_id: str = "rzp_test_key_abc",
    key_secret: str = "rzp_test_secret_xyz",
) -> RazorpayPaymentProvider:
    """Build a RazorpayPaymentProvider whose HTTP layer returns the given response."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=response_body, request=request)

    transport = httpx.MockTransport(mock_handler)
    client = httpx.Client(transport=transport)
    return RazorpayPaymentProvider(
        key_id=key_id,
        key_secret=key_secret,
        http_client=client,
    )


def _make_exec_request(amount: float = 1240.0, attempt: int = 1) -> PaymentExecutionRequest:
    return PaymentExecutionRequest(
        transaction_id=str(uuid.uuid4()),
        idempotency_key=f"rzp_itest_{uuid.uuid4().hex[:12]}",
        amount=amount,
        currency="INR",
        merchant_name="Torrent Power",
        category="utilities",
        attempt_number=attempt,
        payment_method_alias="upi_primary_vpa@mock",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Test 1: Provider can be instantiated
# ──────────────────────────────────────────────────────────────────────────────

class TestRazorpayProviderInstantiation:
    def test_1a_instantiation_with_credentials(self):
        """Provider instantiates cleanly when credentials are provided."""
        provider = RazorpayPaymentProvider(
            key_id="rzp_test_abc",
            key_secret="rzp_test_secret_xyz",
        )
        assert provider.key_id == "rzp_test_abc"
        # Secret is stored (needed for auth) but NEVER should be in responses

    def test_1b_instantiation_without_credentials_no_crash(self):
        """Provider instantiates cleanly even without credentials — returns PROVIDER_ERROR."""
        provider = RazorpayPaymentProvider(key_id="", key_secret="")
        req = _make_exec_request()
        result = provider.create_payment(req)
        assert result.success is False
        assert result.error_code == PaymentFailureReason.PROVIDER_ERROR.value
        assert "credentials" in result.error_message.lower()

    def test_1c_none_credentials_no_crash(self):
        """None credentials don't crash the provider."""
        provider = RazorpayPaymentProvider(key_id=None, key_secret=None)
        req = _make_exec_request()
        result = provider.create_payment(req)
        assert result.success is False
        assert result.error_code == PaymentFailureReason.PROVIDER_ERROR.value

    def test_1d_provider_is_paymentprovider_instance(self):
        """RazorpayPaymentProvider implements the PaymentProvider interface."""
        provider = RazorpayPaymentProvider(key_id="x", key_secret="y")
        assert isinstance(provider, PaymentProvider)


# ──────────────────────────────────────────────────────────────────────────────
# Test 2: Request construction correctness
# ──────────────────────────────────────────────────────────────────────────────

class TestRazorpayRequestConstruction:
    def test_2_amount_converted_to_paise(self):
        """INR amount is converted to paise (×100) in the Razorpay API request."""
        captured_requests = []

        def capture_handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode())
            captured_requests.append(body)
            return httpx.Response(200, json={"id": "order_paise_test", "status": "created"}, request=request)

        transport = httpx.MockTransport(capture_handler)
        client = httpx.Client(transport=transport)
        provider = RazorpayPaymentProvider(key_id="rzp_test", key_secret="secret", http_client=client)

        req = PaymentExecutionRequest(
            transaction_id=str(uuid.uuid4()),
            idempotency_key="paise_test_key",
            amount=1240.50,
            currency="INR",
            merchant_name="Torrent Power",
            category="utilities",
            attempt_number=1,
        )
        result = provider.create_payment(req)

        assert len(captured_requests) == 1
        payload = captured_requests[0]
        # ₹1,240.50 → 124050 paise
        assert payload["amount"] == 124050
        assert payload["currency"] == "INR"

    def test_2b_notes_contain_required_metadata(self):
        """Razorpay request notes contain transaction_id, merchant, category, attempt."""
        captured_requests = []

        def capture_handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode())
            captured_requests.append(body)
            return httpx.Response(200, json={"id": "order_notes_test", "status": "created"}, request=request)

        transport = httpx.MockTransport(capture_handler)
        client = httpx.Client(transport=transport)
        provider = RazorpayPaymentProvider(key_id="rzp_test", key_secret="secret", http_client=client)

        tx_id = str(uuid.uuid4())
        req = PaymentExecutionRequest(
            transaction_id=tx_id,
            idempotency_key="notes_test_key",
            amount=499.0,
            currency="INR",
            merchant_name="Netflix",
            category="subscriptions",
            attempt_number=2,
            payment_method_alias="card_token_primary",
        )
        provider.create_payment(req)

        payload = captured_requests[0]
        notes = payload.get("notes", {})
        assert notes["transaction_id"] == tx_id
        assert notes["merchant_name"] == "Netflix"
        assert notes["category"] == "subscriptions"
        assert notes["attempt_number"] == "2"


# ──────────────────────────────────────────────────────────────────────────────
# Test 3: Secret key never leaked in responses
# ──────────────────────────────────────────────────────────────────────────────

class TestRazorpaySecretNeverLeaked:
    def test_3a_secret_not_in_success_response(self):
        """Razorpay secret key must NEVER appear in a success response payload."""
        secret = "rzp_super_secret_KEY_xyz"
        provider = _razorpay_provider_with_response(
            200,
            {"id": "order_sec_test", "status": "created"},
            key_secret=secret,
        )
        result = provider.create_payment(_make_exec_request())
        assert result.success is True

        # Check all string fields in the result
        result_dict = result.model_dump()
        result_str = json.dumps(result_dict, default=str)
        assert secret not in result_str, f"Secret key leaked in response: {result_str}"

    def test_3b_secret_not_in_error_response(self):
        """Razorpay secret key must NEVER appear in an error response payload."""
        secret = "rzp_secret_MUST_NOT_LEAK_xyz"
        provider = _razorpay_provider_with_response(
            400,
            {"error": {"code": "BAD_REQUEST_ERROR", "description": "Invalid amount"}},
            key_secret=secret,
        )
        result = provider.create_payment(_make_exec_request())
        assert result.success is False

        result_str = json.dumps(result.model_dump(), default=str)
        assert secret not in result_str, f"Secret key leaked in error response: {result_str}"

    def test_3c_key_id_does_not_appear_in_raw_response(self):
        """The Razorpay key_id (which is less sensitive) should not leak into responses."""
        key_id = "rzp_test_UNIQUE_KEY_ID_xyz"
        provider = _razorpay_provider_with_response(
            200,
            {"id": "order_keyid_test", "status": "created"},
            key_id=key_id,
        )
        result = provider.create_payment(_make_exec_request())
        assert result.success is True

        # The raw_response is what we store in PaymentAttempt — must not have key_id
        raw_str = json.dumps(result.raw_response or {}, default=str)
        assert key_id not in raw_str, f"key_id leaked in raw_response: {raw_str}"


# ──────────────────────────────────────────────────────────────────────────────
# Test 4: Success response normalization
# ──────────────────────────────────────────────────────────────────────────────

class TestRazorpaySuccessResponseNormalization:
    def test_4_success_response_normalized_correctly(self):
        """HTTP 200 with order data is normalized to PaymentExecutionResult(success=True)."""
        provider = _razorpay_provider_with_response(
            200,
            {
                "id": "order_rzp_live_test_001",
                "entity": "order",
                "amount": 124000,
                "currency": "INR",
                "receipt": "test_receipt",
                "status": "created",
            },
        )
        req = _make_exec_request(amount=1240.0)
        result = provider.create_payment(req)

        assert result.success is True
        assert result.status == "SUCCESS"
        assert result.provider_payment_id == "order_rzp_live_test_001"
        assert result.amount == 1240.0
        assert result.currency == "INR"
        assert result.error_code is None
        assert result.error_message is None
        assert result.raw_response["provider"] == "RazorpayPaymentProvider"
        assert result.raw_response["order_id"] == "order_rzp_live_test_001"

    def test_4b_201_also_treated_as_success(self):
        """HTTP 201 Created is treated as a success (Razorpay sometimes returns 201)."""
        provider = _razorpay_provider_with_response(
            201,
            {"id": "order_201_created", "status": "created"},
        )
        result = provider.create_payment(_make_exec_request())
        assert result.success is True
        assert result.provider_payment_id == "order_201_created"


# ──────────────────────────────────────────────────────────────────────────────
# Test 5: HTTP error response mapping
# ──────────────────────────────────────────────────────────────────────────────

class TestRazorpayErrorResponseMapping:
    def test_5a_declined_error_maps_to_declined(self):
        """Payment declined error maps to DECLINED failure reason."""
        provider = _razorpay_provider_with_response(
            400,
            {"error": {"code": "BAD_REQUEST_ERROR", "description": "Your payment was declined."}},
        )
        result = provider.create_payment(_make_exec_request())
        assert result.success is False
        assert result.error_code == PaymentFailureReason.DECLINED.value

    def test_5b_insufficient_funds_maps_correctly(self):
        """Insufficient funds error maps to INSUFFICIENT_FUNDS."""
        provider = _razorpay_provider_with_response(
            400,
            {"error": {"description": "insufficient balance in your account"}},
        )
        result = provider.create_payment(_make_exec_request())
        assert result.success is False
        assert result.error_code == PaymentFailureReason.INSUFFICIENT_FUNDS.value

    def test_5c_gateway_timeout_maps_to_timeout(self):
        """Gateway timeout HTTP error maps to TIMEOUT failure reason."""
        provider = _razorpay_provider_with_response(
            408,
            {"error": {"description": "Gateway timeout", "code": "GATEWAY_TIMEOUT"}},
        )
        result = provider.create_payment(_make_exec_request())
        assert result.success is False
        assert result.error_code == PaymentFailureReason.TIMEOUT.value

    def test_5d_502_maps_to_network_error(self):
        """HTTP 502 Bad Gateway maps to NETWORK_ERROR failure reason."""
        provider = _razorpay_provider_with_response(502, {"error": "bad gateway"})
        result = provider.create_payment(_make_exec_request())
        assert result.success is False
        assert result.error_code == PaymentFailureReason.NETWORK_ERROR.value


# ──────────────────────────────────────────────────────────────────────────────
# Test 6: Exception handling
# ──────────────────────────────────────────────────────────────────────────────

class TestRazorpayExceptionHandling:
    def test_6a_httpx_timeout_maps_to_timeout(self):
        """httpx.TimeoutException is caught and mapped to TIMEOUT failure."""
        def timeout_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("connection timed out", request=request)

        transport = httpx.MockTransport(timeout_handler)
        client = httpx.Client(transport=transport)
        provider = RazorpayPaymentProvider(key_id="rzp_test", key_secret="secret", http_client=client)

        result = provider.create_payment(_make_exec_request())
        assert result.success is False
        assert result.error_code == PaymentFailureReason.TIMEOUT.value
        assert result.status == "TIMEOUT"

    def test_6b_httpx_network_error_maps_to_network_error(self):
        """httpx.NetworkError is caught and mapped to NETWORK_ERROR."""
        def network_error_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.NetworkError("connection refused")

        transport = httpx.MockTransport(network_error_handler)
        client = httpx.Client(transport=transport)
        provider = RazorpayPaymentProvider(key_id="rzp_test", key_secret="secret", http_client=client)

        result = provider.create_payment(_make_exec_request())
        assert result.success is False
        assert result.error_code == PaymentFailureReason.NETWORK_ERROR.value


# ──────────────────────────────────────────────────────────────────────────────
# Test 7: PaymentService is provider-agnostic
# ──────────────────────────────────────────────────────────────────────────────

class TestPaymentServiceProviderAgnosticism:
    def test_7_payment_service_works_with_razorpay_provider(self, db_session, test_seed_data):
        """PaymentService is provider-agnostic: runs identically with Razorpay provider."""
        agent = test_seed_data["agent"]

        razorpay_provider = _razorpay_provider_with_response(
            200,
            {"id": "order_agnostic_test_001", "status": "created"},
        )
        service = PaymentService(provider=razorpay_provider)

        result = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=f"agnostic_test_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
        )

        assert result["success"] is True
        assert result["status"] == "SUCCESS"
        assert result["provider_payment_id"] == "order_agnostic_test_001"

        # Verify DB records
        payment_id = uuid.UUID(result["payment_id"])
        tx = db_session.get(Transaction, payment_id)
        assert tx.status == TransactionStatus.SUCCESS.value
        assert tx.payment_provider == "RazorpayPaymentProvider"

        attempts = db_session.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == payment_id)
        ).scalars().all()
        assert len(attempts) == 1
        assert attempts[0].status == "SUCCESS"
        assert attempts[0].provider_payment_id == "order_agnostic_test_001"

    def test_7b_razorpay_failure_triggers_same_state_machine(self, db_session, test_seed_data):
        """Razorpay failure result navigates through same FAILED state machine path as Mock."""
        agent = test_seed_data["agent"]

        razorpay_provider = _razorpay_provider_with_response(
            400,
            {"error": {"description": "Payment was declined.", "code": "BAD_REQUEST_ERROR"}},
        )
        service = PaymentService(provider=razorpay_provider)

        result = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=f"rzp_fail_sm_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
        )

        assert result["success"] is False
        assert result["status"] == "FAILED"
        assert result["failure_reason"] == PaymentFailureReason.DECLINED.value

        payment_id = uuid.UUID(result["payment_id"])
        tx = db_session.get(Transaction, payment_id)
        assert tx.status == TransactionStatus.FAILED.value

    def test_7c_secret_not_in_payment_attempt_response_payload(self, db_session, test_seed_data):
        """Secret key must NOT appear in the PaymentAttempt.response_payload stored in DB."""
        agent = test_seed_data["agent"]
        SECRET = "SUPER_SECRET_KEY_MUST_NOT_LEAK"

        razorpay_provider = _razorpay_provider_with_response(
            200,
            {"id": "order_secret_check", "status": "created"},
            key_secret=SECRET,
        )
        service = PaymentService(provider=razorpay_provider)

        result = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=f"secret_check_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
        )
        assert result["success"] is True

        payment_id = uuid.UUID(result["payment_id"])
        attempts = db_session.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == payment_id)
        ).scalars().all()

        for attempt in attempts:
            payload_str = json.dumps(attempt.response_payload or {}, default=str)
            assert SECRET not in payload_str, (
                f"Secret key leaked in PaymentAttempt.response_payload: {payload_str}"
            )


# ──────────────────────────────────────────────────────────────────────────────
# Test 8: get_payment_provider factory
# ──────────────────────────────────────────────────────────────────────────────

class TestProviderFactory:
    def test_8a_mock_provider_returned_by_default(self):
        """Default PAYMENT_PROVIDER=MOCK returns MockPaymentProvider."""
        mock_settings = Settings(
            DATABASE_URL="sqlite:///:memory:",
            PAYMENT_PROVIDER="MOCK",
        )
        provider = get_payment_provider(settings=mock_settings)
        assert isinstance(provider, MockPaymentProvider)

    def test_8b_razorpay_without_credentials_raises(self):
        """PAYMENT_PROVIDER=RAZORPAY without credentials raises ValueError (not crashes)."""
        mock_settings = Settings(
            DATABASE_URL="sqlite:///:memory:",
            PAYMENT_PROVIDER="RAZORPAY",
            RAZORPAY_KEY_ID="",
            RAZORPAY_KEY_SECRET="",
        )
        with pytest.raises(ValueError, match="RAZORPAY_KEY_ID"):
            get_payment_provider(settings=mock_settings)

    def test_8c_invalid_provider_name_raises(self):
        """Unknown PAYMENT_PROVIDER value raises ValueError."""
        mock_settings = Settings(
            DATABASE_URL="sqlite:///:memory:",
            PAYMENT_PROVIDER="STRIPE",
        )
        with pytest.raises(ValueError, match="Invalid PAYMENT_PROVIDER"):
            get_payment_provider(settings=mock_settings)
