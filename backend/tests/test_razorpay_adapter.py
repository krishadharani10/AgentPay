"""
Day 3 Phase 3 Step 2: RazorpayPaymentProvider Unit Tests.
Tests Razorpay integration using mocked HTTP responses.
Does NOT require real Razorpay credentials.
Verifies:
  - Successful order creation response mapping
  - Declined / error response mapping
  - Provider exception handling (timeout, network error)
  - Missing credentials behavior
  - Provider reference (order_id) extraction
  - Secret is never included in response/logging structures
  - get_payment_provider factory
  - PaymentProvider ABC compliance
"""
import uuid
import json
import pytest
import httpx

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


def _make_request(**overrides) -> PaymentExecutionRequest:
    """Helper to build a standard PaymentExecutionRequest."""
    defaults = dict(
        transaction_id=str(uuid.uuid4()),
        idempotency_key=f"idem_{uuid.uuid4().hex[:8]}",
        amount=1240.0,
        currency="INR",
        merchant_name="Torrent Power",
        category="utilities",
        attempt_number=1,
        payment_method_alias="krisha.agent@icici",
    )
    defaults.update(overrides)
    return PaymentExecutionRequest(**defaults)


def _mock_transport(status_code: int, json_body: dict) -> httpx.MockTransport:
    """Create a deterministic httpx.MockTransport returning a fixed response."""
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=status_code,
            json=json_body,
            request=request,
        )
    return _mock_transport_from_handler(_handler)


def _mock_transport_from_handler(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


class TestRazorpayProviderSuccessMapping:
    """Test successful Razorpay API responses map correctly to PaymentExecutionResult."""

    def test_1_successful_order_creation(self):
        """Razorpay 200 order creation maps to success=True, status=SUCCESS."""
        order_id = "order_TestABC12345"
        transport = _mock_transport(200, {
            "id": order_id,
            "entity": "order",
            "amount": 124000,
            "currency": "INR",
            "receipt": "test_receipt",
            "status": "created",
        })
        client = httpx.Client(transport=transport)
        provider = RazorpayPaymentProvider(
            key_id="rzp_test_key123",
            key_secret="rzp_test_secret456",
            http_client=client,
        )

        req = _make_request()
        result = provider.create_payment(req)

        assert isinstance(result, PaymentExecutionResult)
        assert result.success is True
        assert result.status == "SUCCESS"
        assert result.provider_payment_id == order_id
        assert result.amount == 1240.0
        assert result.currency == "INR"
        assert result.attempt_number == 1
        assert result.error_code is None
        assert result.error_message is None

    def test_2_provider_payment_id_stored_as_razorpay_order_id(self):
        """provider_payment_id must contain the Razorpay order_id for audit/lookup."""
        order_id = "order_XYZ789"
        transport = _mock_transport(200, {
            "id": order_id,
            "entity": "order",
            "amount": 49900,
            "currency": "INR",
            "status": "created",
        })
        client = httpx.Client(transport=transport)
        provider = RazorpayPaymentProvider(
            key_id="rzp_test_key",
            key_secret="rzp_test_secret",
            http_client=client,
        )

        result = provider.create_payment(_make_request(amount=499.0))
        assert result.provider_payment_id == order_id

    def test_3_sanitized_response_excludes_secret(self):
        """raw_response and response_payload must never contain the API secret."""
        secret = "rzp_test_secret_SUPER_SECRET"
        transport = _mock_transport(200, {
            "id": "order_Safe1",
            "entity": "order",
            "amount": 100000,
            "currency": "INR",
            "status": "created",
        })
        client = httpx.Client(transport=transport)
        provider = RazorpayPaymentProvider(
            key_id="rzp_test_key",
            key_secret=secret,
            http_client=client,
        )

        result = provider.create_payment(_make_request(amount=1000.0))
        assert result.success is True

        # Verify secret is not anywhere in serialized response
        raw_str = json.dumps(result.raw_response)
        payload_str = json.dumps(result.response_payload)
        result_str = result.model_dump_json()

        assert secret not in raw_str
        assert secret not in payload_str
        assert secret not in result_str

    def test_4_amount_converted_to_paise_in_request(self):
        """Verify the provider sends amount in paise (x100) to Razorpay."""
        captured_bodies = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_bodies.append(json.loads(request.content))
            return httpx.Response(200, json={
                "id": "order_PaiseTest",
                "entity": "order",
                "amount": 124000,
                "currency": "INR",
                "status": "created",
            }, request=request)

        transport = httpx.MockTransport(handler)
        client = httpx.Client(transport=transport)
        provider = RazorpayPaymentProvider(
            key_id="rzp_test_key",
            key_secret="rzp_test_secret",
            http_client=client,
        )
        provider.create_payment(_make_request(amount=1240.0))
        assert captured_bodies[0]["amount"] == 124000

    def test_5_201_also_treated_as_success(self):
        """Razorpay 201 is also a success response."""
        transport = _mock_transport(201, {
            "id": "order_201Test",
            "entity": "order",
            "amount": 69900,
            "currency": "INR",
            "status": "created",
        })
        client = httpx.Client(transport=transport)
        provider = RazorpayPaymentProvider(
            key_id="rzp_test_key",
            key_secret="rzp_test_secret",
            http_client=client,
        )
        result = provider.create_payment(_make_request(amount=699.0))
        assert result.success is True
        assert result.status == "SUCCESS"


class TestRazorpayProviderErrorMapping:
    """Test Razorpay error responses map correctly to failure reasons."""

    def test_1_declined_error_maps_to_declined(self):
        """BAD_REQUEST_ERROR with declined description maps to DECLINED."""
        transport = _mock_transport(400, {
            "error": {
                "code": "BAD_REQUEST_ERROR",
                "description": "Payment was declined by the issuing bank.",
                "reason": "payment_declined",
            }
        })
        client = httpx.Client(transport=transport)
        provider = RazorpayPaymentProvider(
            key_id="rzp_test_key",
            key_secret="rzp_test_secret",
            http_client=client,
        )

        result = provider.create_payment(_make_request())
        assert result.success is False
        assert result.status == "FAILED"
        assert result.error_code == PaymentFailureReason.DECLINED.value
        assert "declined" in result.error_message.lower()

    def test_2_insufficient_funds_maps_correctly(self):
        """Description containing 'insufficient' maps to INSUFFICIENT_FUNDS."""
        transport = _mock_transport(400, {
            "error": {
                "code": "BAD_REQUEST_ERROR",
                "description": "Insufficient funds in the account.",
            }
        })
        client = httpx.Client(transport=transport)
        provider = RazorpayPaymentProvider(
            key_id="rzp_test_key",
            key_secret="rzp_test_secret",
            http_client=client,
        )

        result = provider.create_payment(_make_request())
        assert result.success is False
        assert result.error_code == PaymentFailureReason.INSUFFICIENT_FUNDS.value

    def test_3_gateway_timeout_maps_to_timeout(self):
        """GATEWAY_TIMEOUT code maps to TIMEOUT failure reason."""
        transport = _mock_transport(504, {
            "error": {
                "code": "GATEWAY_TIMEOUT",
                "description": "The payment request timed out at the gateway.",
            }
        })
        client = httpx.Client(transport=transport)
        provider = RazorpayPaymentProvider(
            key_id="rzp_test_key",
            key_secret="rzp_test_secret",
            http_client=client,
        )

        result = provider.create_payment(_make_request())
        assert result.success is False
        assert result.status == "TIMEOUT"
        assert result.error_code == PaymentFailureReason.TIMEOUT.value

    def test_4_502_maps_to_network_error(self):
        """HTTP 502 maps to NETWORK_ERROR."""
        transport = _mock_transport(502, {
            "error": {
                "code": "SERVER_ERROR",
                "description": "Bad gateway error connecting to upstream.",
            }
        })
        client = httpx.Client(transport=transport)
        provider = RazorpayPaymentProvider(
            key_id="rzp_test_key",
            key_secret="rzp_test_secret",
            http_client=client,
        )

        result = provider.create_payment(_make_request())
        assert result.success is False
        assert result.error_code == PaymentFailureReason.NETWORK_ERROR.value

    def test_5_unknown_error_maps_to_provider_error(self):
        """Unknown Razorpay error codes map to PROVIDER_ERROR as a safe fallback."""
        transport = _mock_transport(422, {
            "error": {
                "code": "UNKNOWN_WEIRD_CODE",
                "description": "Something unexpected happened.",
            }
        })
        client = httpx.Client(transport=transport)
        provider = RazorpayPaymentProvider(
            key_id="rzp_test_key",
            key_secret="rzp_test_secret",
            http_client=client,
        )

        result = provider.create_payment(_make_request())
        assert result.success is False
        assert result.error_code == PaymentFailureReason.PROVIDER_ERROR.value


class TestRazorpayProviderExceptionHandling:
    """Test httpx exception types are correctly caught and mapped."""

    def test_1_httpx_timeout_exception(self):
        """httpx.TimeoutException maps to TIMEOUT result."""
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("Connection timed out")

        transport = httpx.MockTransport(handler)
        client = httpx.Client(transport=transport)
        provider = RazorpayPaymentProvider(
            key_id="rzp_test_key",
            key_secret="rzp_test_secret",
            http_client=client,
        )

        result = provider.create_payment(_make_request())
        assert result.success is False
        assert result.status == "TIMEOUT"
        assert result.error_code == PaymentFailureReason.TIMEOUT.value

    def test_2_httpx_network_error(self):
        """httpx.ConnectError maps to NETWORK_ERROR result."""
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Failed to connect")

        transport = httpx.MockTransport(handler)
        client = httpx.Client(transport=transport)
        provider = RazorpayPaymentProvider(
            key_id="rzp_test_key",
            key_secret="rzp_test_secret",
            http_client=client,
        )

        result = provider.create_payment(_make_request())
        assert result.success is False
        assert result.error_code == PaymentFailureReason.NETWORK_ERROR.value

    def test_3_generic_exception_maps_to_provider_error(self):
        """Unexpected exceptions are caught and mapped to PROVIDER_ERROR."""
        def handler(request: httpx.Request) -> httpx.Response:
            raise RuntimeError("Something unexpected")

        transport = httpx.MockTransport(handler)
        client = httpx.Client(transport=transport)
        provider = RazorpayPaymentProvider(
            key_id="rzp_test_key",
            key_secret="rzp_test_secret",
            http_client=client,
        )

        result = provider.create_payment(_make_request())
        assert result.success is False
        assert result.error_code == PaymentFailureReason.PROVIDER_ERROR.value
        assert "unexpected" in result.error_message.lower()


class TestRazorpayProviderCredentials:
    """Test missing or empty credentials behavior."""

    def test_1_missing_credentials_returns_failed(self):
        """Empty key_id / key_secret returns a safe FAILED result without calling Razorpay."""
        provider = RazorpayPaymentProvider(key_id="", key_secret="")
        result = provider.create_payment(_make_request())

        assert result.success is False
        assert result.status == "FAILED"
        assert result.error_code == PaymentFailureReason.PROVIDER_ERROR.value
        assert "credentials" in result.error_message.lower()
        assert result.provider_payment_id == "uninitialized_credentials"

    def test_2_none_credentials_returns_failed(self):
        """None credentials are handled gracefully."""
        provider = RazorpayPaymentProvider(key_id=None, key_secret=None)
        result = provider.create_payment(_make_request())

        assert result.success is False
        assert result.error_code == PaymentFailureReason.PROVIDER_ERROR.value

    def test_3_get_status_with_missing_credentials(self):
        """get_status also fails gracefully with missing credentials."""
        provider = RazorpayPaymentProvider(key_id="", key_secret="")
        result = provider.get_status("order_ABC")
        assert result.success is False
        assert result.error_code == PaymentFailureReason.PROVIDER_ERROR.value

    def test_4_secret_never_in_result_model(self):
        """The key_secret must never appear in any PaymentExecutionResult field."""
        secret = "rzp_test_TOP_SECRET_KEY_999"
        transport = _mock_transport(200, {
            "id": "order_SecretCheck",
            "entity": "order",
            "amount": 124000,
            "currency": "INR",
            "status": "created",
        })
        client = httpx.Client(transport=transport)
        provider = RazorpayPaymentProvider(
            key_id="rzp_test_key",
            key_secret=secret,
            http_client=client,
        )

        result = provider.create_payment(_make_request())
        full_json = result.model_dump_json()
        assert secret not in full_json

        # Also check error path
        err_transport = _mock_transport(400, {
            "error": {"code": "BAD_REQUEST_ERROR", "description": "Test error"}
        })
        err_client = httpx.Client(transport=err_transport)
        err_provider = RazorpayPaymentProvider(
            key_id="rzp_test_key",
            key_secret=secret,
            http_client=err_client,
        )
        err_result = err_provider.create_payment(_make_request())
        err_json = err_result.model_dump_json()
        assert secret not in err_json


class TestRazorpayProviderGetStatus:
    """Test get_status with mocked Razorpay lookup responses."""

    def test_1_successful_order_lookup(self):
        """Order lookup returning 'created' status maps to SUCCESS."""
        transport = _mock_transport(200, {
            "id": "order_Lookup1",
            "entity": "order",
            "amount": 124000,
            "currency": "INR",
            "status": "created",
            "notes": {
                "transaction_id": "tx_123",
                "attempt_number": "1",
            },
        })
        client = httpx.Client(transport=transport)
        provider = RazorpayPaymentProvider(
            key_id="rzp_test_key",
            key_secret="rzp_test_secret",
            http_client=client,
        )

        result = provider.get_status("order_Lookup1")
        assert result.success is True
        assert result.status == "SUCCESS"
        assert result.amount == 1240.0

    def test_2_failed_order_status(self):
        """Order in 'failed' status maps to FAILED."""
        transport = _mock_transport(200, {
            "id": "order_Failed1",
            "entity": "order",
            "amount": 124000,
            "currency": "INR",
            "status": "failed",
            "notes": {"transaction_id": "tx_456"},
        })
        client = httpx.Client(transport=transport)
        provider = RazorpayPaymentProvider(
            key_id="rzp_test_key",
            key_secret="rzp_test_secret",
            http_client=client,
        )

        result = provider.get_status("order_Failed1")
        assert result.success is False
        assert result.status == "FAILED"


class TestProviderRetry:
    """Test that retry delegates to create_payment as expected."""

    def test_1_retry_delegates_to_create_payment(self):
        transport = _mock_transport(200, {
            "id": "order_Retry1",
            "entity": "order",
            "amount": 124000,
            "currency": "INR",
            "status": "created",
        })
        client = httpx.Client(transport=transport)
        provider = RazorpayPaymentProvider(
            key_id="rzp_test_key",
            key_secret="rzp_test_secret",
            http_client=client,
        )

        req = _make_request(attempt_number=2)
        result = provider.retry(req)
        assert result.success is True
        assert result.attempt_number == 2


class TestProviderFactory:
    """Test get_payment_provider factory function and runtime switching."""

    def test_1_default_returns_mock_provider(self):
        """Mock settings returns MockPaymentProvider."""
        from app.config import Settings
        settings = Settings(PAYMENT_PROVIDER="MOCK")
        provider = get_payment_provider(settings=settings)
        assert isinstance(provider, MockPaymentProvider)

    def test_2_razorpay_config_returns_razorpay_provider(self):
        """Settings with PAYMENT_PROVIDER=RAZORPAY returns RazorpayPaymentProvider."""
        from app.config import Settings
        settings = Settings(
            PAYMENT_PROVIDER="RAZORPAY",
            RAZORPAY_KEY_ID="rzp_test_factory_key",
            RAZORPAY_KEY_SECRET="rzp_test_factory_secret",
        )
        provider = get_payment_provider(settings=settings)
        assert isinstance(provider, RazorpayPaymentProvider)
        assert provider.key_id == "rzp_test_factory_key"

    def test_3_mock_config_returns_mock_provider(self):
        """Settings with PAYMENT_PROVIDER=MOCK returns MockPaymentProvider."""
        from app.config import Settings
        settings = Settings(PAYMENT_PROVIDER="MOCK")
        provider = get_payment_provider(settings=settings)
        assert isinstance(provider, MockPaymentProvider)

    def test_4_invalid_provider_raises_value_error(self):
        """Unsupported PAYMENT_PROVIDER value raises ValueError with supported list."""
        from app.config import Settings
        settings = Settings(PAYMENT_PROVIDER="STRIPE")
        with pytest.raises(ValueError, match="Invalid PAYMENT_PROVIDER='STRIPE'"):
            get_payment_provider(settings=settings)

    def test_5_razorpay_without_credentials_raises_value_error(self):
        """PAYMENT_PROVIDER=RAZORPAY without credentials raises ValueError."""
        from app.config import Settings
        settings = Settings(
            PAYMENT_PROVIDER="RAZORPAY",
            RAZORPAY_KEY_ID="",
            RAZORPAY_KEY_SECRET="",
        )
        with pytest.raises(ValueError, match="requires both RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET"):
            get_payment_provider(settings=settings)

    def test_6_mock_mode_works_without_razorpay_credentials(self):
        """Mock mode works cleanly with zero Razorpay credentials."""
        from app.config import Settings
        settings = Settings(
            PAYMENT_PROVIDER="MOCK",
            RAZORPAY_KEY_ID="",
            RAZORPAY_KEY_SECRET="",
        )
        provider = get_payment_provider(settings=settings)
        assert isinstance(provider, MockPaymentProvider)

    def test_7_payment_service_uses_factory_default(self):
        """PaymentService defaults to the configured provider or custom provider."""
        from app.services.payment_service import PaymentService
        service = PaymentService(provider=MockPaymentProvider())
        assert isinstance(service.provider, MockPaymentProvider)




class TestPaymentProviderABCCompliance:
    """Verify RazorpayPaymentProvider implements the full PaymentProvider interface."""

    def test_1_is_instance_of_payment_provider(self):
        provider = RazorpayPaymentProvider(key_id="k", key_secret="s")
        assert isinstance(provider, PaymentProvider)

    def test_2_has_all_required_methods(self):
        provider = RazorpayPaymentProvider(key_id="k", key_secret="s")
        assert hasattr(provider, "create_payment")
        assert hasattr(provider, "get_status")
        assert hasattr(provider, "retry")
        assert callable(provider.create_payment)
        assert callable(provider.get_status)
        assert callable(provider.retry)

    def test_3_backward_compatible_aliases_work(self):
        """execute_payment, get_payment_status, retry_payment aliases exist."""
        provider = RazorpayPaymentProvider(key_id="", key_secret="")
        assert hasattr(provider, "execute_payment")
        assert hasattr(provider, "get_payment_status")
        assert hasattr(provider, "retry_payment")
