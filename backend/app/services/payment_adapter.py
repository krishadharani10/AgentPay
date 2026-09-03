import uuid
import httpx
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, Union, List, Tuple
from pydantic import BaseModel, Field
from app.config import get_settings, Settings


class PaymentFailureReason(str, Enum):
    """
    Authoritative payment failure reasons.
    """
    DECLINED = "DECLINED"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"


class MockPaymentMode(str, Enum):
    """
    Deterministic operational modes for MockPaymentProvider.
    Ensures zero random/flaky behavior in demos and tests.
    """
    SUCCESS = "SUCCESS"
    DECLINED = "DECLINED"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    FAIL = "FAIL"  # Backward-compatible alias for DECLINED


class PaymentExecutionRequest(BaseModel):
    transaction_id: str
    idempotency_key: str
    amount: float = Field(..., gt=0)
    currency: str = "INR"
    merchant_name: str
    category: str
    attempt_number: int = 1
    payment_method_alias: Optional[str] = "mock_primary_vpa"
    metadata: Optional[Dict[str, Any]] = None


class PaymentExecutionResult(BaseModel):
    success: bool
    status: str  # "SUCCESS", "FAILED", "TIMEOUT", "PENDING"
    payment_id: str
    provider_payment_id: str
    amount: float
    currency: str
    attempt_number: int
    error_code: Optional[str] = None  # DECLINED, TIMEOUT, NETWORK_ERROR, PROVIDER_ERROR, INSUFFICIENT_FUNDS
    error_message: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_response: Optional[Dict[str, Any]] = None
    response_payload: Optional[Dict[str, Any]] = None


class PaymentProvider(ABC):
    """
    Abstract interface for payment providers (Mock, Razorpay, etc.).
    Defines the contract for payment execution, status lookup, and retries.
    """

    @abstractmethod
    def create_payment(self, request: PaymentExecutionRequest) -> PaymentExecutionResult:
        """Create and execute a payment request."""
        pass

    @abstractmethod
    def get_status(self, provider_payment_id: str) -> PaymentExecutionResult:
        """Retrieve latest payment status from the provider."""
        pass

    @abstractmethod
    def retry(self, request: PaymentExecutionRequest) -> PaymentExecutionResult:
        """Retry a failed or timed out payment."""
        pass

    # Aliases for backward compatibility
    def execute_payment(self, request: PaymentExecutionRequest) -> PaymentExecutionResult:
        return self.create_payment(request)

    def get_payment_status(self, provider_payment_id: str) -> PaymentExecutionResult:
        return self.get_status(provider_payment_id)

    def retry_payment(self, request: PaymentExecutionRequest) -> PaymentExecutionResult:
        return self.retry(request)


# Backward-compatible alias
PaymentAdapter = PaymentProvider


class MockPaymentProvider(PaymentProvider):
    """
    Deterministic Mock Payment Provider for testing and demonstrations.
    Guarantees reproducible outcomes based on configured mode or sequence:
      - SUCCESS: Payment approved and settled instantly
      - DECLINED / FAIL: Card or payment method declined
      - TIMEOUT: Gateway request times out
      - NETWORK_ERROR: Network connection / transport error
      - PROVIDER_ERROR: Internal processor error
      - INSUFFICIENT_FUNDS: Insufficient account balance
    """

    def __init__(
        self,
        mode: Union[MockPaymentMode, PaymentFailureReason, str] = MockPaymentMode.SUCCESS,
        mode_sequence: Optional[List[Union[MockPaymentMode, PaymentFailureReason, str]]] = None,
        default_failure: bool = False,
        failure_reason: Optional[str] = None,
    ):
        if default_failure:
            self.mode = MockPaymentMode.DECLINED
        elif isinstance(mode, str):
            self.mode = MockPaymentMode(mode.upper())
        elif isinstance(mode, PaymentFailureReason):
            self.mode = MockPaymentMode(mode.value)
        else:
            self.mode = mode

        self.mode_sequence: Optional[List[MockPaymentMode]] = None
        if mode_sequence is not None:
            self.mode_sequence = [
                MockPaymentMode(m.value if hasattr(m, "value") else str(m).upper())
                for m in mode_sequence
            ]

        self.failure_reason = failure_reason
        self._provider_records: Dict[str, PaymentExecutionResult] = {}
        self.call_history: List[PaymentExecutionRequest] = []

    @property
    def call_count(self) -> int:
        return len(self.call_history)

    def create_payment(self, request: PaymentExecutionRequest) -> PaymentExecutionResult:
        call_index = len(self.call_history)
        self.call_history.append(request)

        # Resolve mode:
        # 1. Check if request metadata has explicit override
        # 2. Check if a deterministic mode_sequence is configured
        # 3. Default to instance self.mode
        effective_mode = self.mode
        if self.mode_sequence and len(self.mode_sequence) > 0:
            seq_idx = min(call_index, len(self.mode_sequence) - 1)
            effective_mode = self.mode_sequence[seq_idx]

        if request.metadata:
            meta_mode = (
                request.metadata.get("payment_mode")
                or request.metadata.get("mode")
                or request.metadata.get("failure_mode")
            )
            if meta_mode:
                mode_str = meta_mode.value if hasattr(meta_mode, "value") else str(meta_mode)
                effective_mode = MockPaymentMode(mode_str.upper())
            elif request.metadata.get("force_failure") is True:
                effective_mode = MockPaymentMode.DECLINED
            elif request.metadata.get("force_timeout") is True:
                effective_mode = MockPaymentMode.TIMEOUT
            elif request.metadata.get("force_failure") is False and "payment_mode" not in request.metadata:
                effective_mode = MockPaymentMode.SUCCESS

        provider_id = f"pay_mock_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        if effective_mode in (MockPaymentMode.DECLINED, MockPaymentMode.FAIL):
            result = PaymentExecutionResult(
                success=False,
                status="FAILED",
                payment_id=request.transaction_id,
                provider_payment_id=provider_id,
                amount=request.amount,
                currency=request.currency,
                attempt_number=request.attempt_number,
                error_code=PaymentFailureReason.DECLINED.value,
                error_message=self.failure_reason or "Payment method was declined by the bank or network.",
                timestamp=now,
                raw_response={
                    "provider": "MockPaymentProvider",
                    "mode": "DECLINED",
                    "failure_reason": "DECLINED",
                    "simulated_error": True,
                },
            )
        elif effective_mode == MockPaymentMode.TIMEOUT:
            result = PaymentExecutionResult(
                success=False,
                status="TIMEOUT",
                payment_id=request.transaction_id,
                provider_payment_id=provider_id,
                amount=request.amount,
                currency=request.currency,
                attempt_number=request.attempt_number,
                error_code=PaymentFailureReason.TIMEOUT.value,
                error_message=self.failure_reason or "Payment gateway request timed out.",
                timestamp=now,
                raw_response={
                    "provider": "MockPaymentProvider",
                    "mode": "TIMEOUT",
                    "failure_reason": "TIMEOUT",
                    "simulated_timeout": True,
                },
            )
        elif effective_mode == MockPaymentMode.NETWORK_ERROR:
            result = PaymentExecutionResult(
                success=False,
                status="FAILED",
                payment_id=request.transaction_id,
                provider_payment_id=provider_id,
                amount=request.amount,
                currency=request.currency,
                attempt_number=request.attempt_number,
                error_code=PaymentFailureReason.NETWORK_ERROR.value,
                error_message=self.failure_reason or "Network communication failure connecting to payment processor.",
                timestamp=now,
                raw_response={
                    "provider": "MockPaymentProvider",
                    "mode": "NETWORK_ERROR",
                    "failure_reason": "NETWORK_ERROR",
                    "simulated_network_error": True,
                },
            )
        elif effective_mode == MockPaymentMode.PROVIDER_ERROR:
            result = PaymentExecutionResult(
                success=False,
                status="FAILED",
                payment_id=request.transaction_id,
                provider_payment_id=provider_id,
                amount=request.amount,
                currency=request.currency,
                attempt_number=request.attempt_number,
                error_code=PaymentFailureReason.PROVIDER_ERROR.value,
                error_message=self.failure_reason or "Internal gateway/provider error occurred while processing.",
                timestamp=now,
                raw_response={
                    "provider": "MockPaymentProvider",
                    "mode": "PROVIDER_ERROR",
                    "failure_reason": "PROVIDER_ERROR",
                    "simulated_provider_error": True,
                },
            )
        elif effective_mode == MockPaymentMode.INSUFFICIENT_FUNDS:
            result = PaymentExecutionResult(
                success=False,
                status="FAILED",
                payment_id=request.transaction_id,
                provider_payment_id=provider_id,
                amount=request.amount,
                currency=request.currency,
                attempt_number=request.attempt_number,
                error_code=PaymentFailureReason.INSUFFICIENT_FUNDS.value,
                error_message=self.failure_reason or "Insufficient funds or credit limit available in account.",
                timestamp=now,
                raw_response={
                    "provider": "MockPaymentProvider",
                    "mode": "INSUFFICIENT_FUNDS",
                    "failure_reason": "INSUFFICIENT_FUNDS",
                    "simulated_funds_error": True,
                },
            )
        else:  # SUCCESS
            result = PaymentExecutionResult(
                success=True,
                status="SUCCESS",
                payment_id=request.transaction_id,
                provider_payment_id=provider_id,
                amount=request.amount,
                currency=request.currency,
                attempt_number=request.attempt_number,
                timestamp=now,
                raw_response={
                    "provider": "MockPaymentProvider",
                    "mode": "SUCCESS",
                    "settlement": "instant",
                    "method": request.payment_method_alias or "UPI",
                },
            )

        result.response_payload = result.raw_response
        self._provider_records[provider_id] = result
        return result

    def get_status(self, provider_payment_id: str) -> PaymentExecutionResult:
        if provider_payment_id in self._provider_records:
            return self._provider_records[provider_payment_id]

        return PaymentExecutionResult(
            success=True,
            status="SUCCESS",
            payment_id="unknown",
            provider_payment_id=provider_payment_id,
            amount=0.0,
            currency="INR",
            attempt_number=1,
            timestamp=datetime.now(timezone.utc),
            raw_response={"provider": "MockPaymentProvider", "lookup": "fallback"},
            response_payload={"provider": "MockPaymentProvider", "lookup": "fallback"},
        )

    def retry(self, request: PaymentExecutionRequest) -> PaymentExecutionResult:
        return self.create_payment(request)


# Backward-compatible alias
MockPaymentAdapter = MockPaymentProvider


_SENTINEL = object()


class RazorpayPaymentProvider(PaymentProvider):
    """
    Razorpay Test Mode Payment Provider.
    Implements the authoritative PaymentProvider abstraction for Razorpay Test Mode.
    Communicates securely with Razorpay API using environment-backed credentials.
    Zero leakage: RAZORPAY_KEY_SECRET is strictly guarded and never exposed in responses or logs.
    """

    def __init__(
        self,
        key_id: Any = _SENTINEL,
        key_secret: Any = _SENTINEL,
        base_url: str = "https://api.razorpay.com/v1",
        timeout: float = 10.0,
        http_client: Optional[httpx.Client] = None,
    ):
        settings = get_settings()
        raw_key_id = getattr(settings, "razorpay_key_id", "") if key_id is _SENTINEL else key_id
        raw_key_secret = getattr(settings, "razorpay_key_secret", "") if key_secret is _SENTINEL else key_secret
        self.key_id = str(raw_key_id or "").strip()
        self.key_secret = str(raw_key_secret or "").strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._external_client = http_client

    def _get_client(self) -> httpx.Client:
        if self._external_client is not None:
            return self._external_client
        return httpx.Client(timeout=self.timeout)

    def _map_razorpay_error(self, status_code: int, error_data: Dict[str, Any]) -> Tuple[str, str]:
        """
        Maps Razorpay API error structures into authoritative PaymentFailureReason and human description.
        """
        error_obj = error_data.get("error", {}) if isinstance(error_data, dict) else {}
        # Guard: error_obj might be a non-dict (e.g. a plain string like "bad gateway")
        if not isinstance(error_obj, dict):
            error_obj = {}
        code = str(error_obj.get("code") or "").upper()
        description = str(error_obj.get("description") or error_obj.get("message") or "")
        reason = str(error_obj.get("reason") or "").lower()
        desc_lower = description.lower()

        if "insufficient" in desc_lower or "limit" in desc_lower or "balance" in desc_lower or "funds" in desc_lower:
            return PaymentFailureReason.INSUFFICIENT_FUNDS.value, description or "Insufficient balance or card limit exceeded."
        elif "declined" in desc_lower or reason == "payment_declined" or "rejected" in desc_lower or code in ("BAD_REQUEST_ERROR", "PAYMENT_DECLINED"):
            return PaymentFailureReason.DECLINED.value, description or "Payment was declined by issuing bank or network."
        elif "timeout" in desc_lower or "timed out" in desc_lower or code in ("GATEWAY_TIMEOUT", "TIMEOUT"):
            return PaymentFailureReason.TIMEOUT.value, description or "Payment gateway request timed out."
        elif "network" in desc_lower or code == "NETWORK_ERROR" or status_code in (502, 503, 504):
            return PaymentFailureReason.NETWORK_ERROR.value, description or "Network communication failure connecting to Razorpay."
        else:
            return PaymentFailureReason.PROVIDER_ERROR.value, description or f"Razorpay processing error (HTTP {status_code})."

    def create_payment(self, request: PaymentExecutionRequest) -> PaymentExecutionResult:
        now = datetime.now(timezone.utc)

        # 1. Credentials Check
        if not self.key_id or not self.key_secret:
            return PaymentExecutionResult(
                success=False,
                status="FAILED",
                payment_id=request.transaction_id,
                provider_payment_id="uninitialized_credentials",
                amount=request.amount,
                currency=request.currency,
                attempt_number=request.attempt_number,
                error_code=PaymentFailureReason.PROVIDER_ERROR.value,
                error_message="Razorpay credentials (RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET) not configured.",
                timestamp=now,
                raw_response={"error": "MISSING_CREDENTIALS", "provider": "RazorpayPaymentProvider"},
                response_payload={"error": "MISSING_CREDENTIALS", "provider": "RazorpayPaymentProvider"},
            )

        # 2. Prepare payload (Amount in paise for INR)
        amount_paise = int(round(request.amount * 100))
        payload = {
            "amount": amount_paise,
            "currency": request.currency.upper(),
            "receipt": request.idempotency_key or f"rcpt_{request.transaction_id[:16]}",
            "notes": {
                "transaction_id": request.transaction_id,
                "merchant_name": request.merchant_name,
                "category": request.category,
                "attempt_number": str(request.attempt_number),
                "payment_method": request.payment_method_alias or "UPI",
            },
        }

        # 3. Dispatch to Razorpay Orders API
        endpoint = f"{self.base_url}/orders"
        try:
            client = self._get_client()
            should_close = self._external_client is None
            try:
                response = client.post(
                    endpoint,
                    json=payload,
                    auth=(self.key_id, self.key_secret),
                )
            finally:
                if should_close:
                    client.close()

            status_code = response.status_code
            try:
                data = response.json()
            except Exception:
                data = {"raw_text": response.text}

            # 4. Handle Success (200 / 201)
            if status_code in (200, 201):
                order_id = data.get("id") or f"order_{uuid.uuid4().hex[:14]}"
                sanitized_response = {
                    "provider": "RazorpayPaymentProvider",
                    "mode": "TEST",
                    "order_id": order_id,
                    "entity": data.get("entity", "order"),
                    "amount": data.get("amount", amount_paise),
                    "currency": data.get("currency", request.currency),
                    "status": data.get("status", "created"),
                    "receipt": data.get("receipt"),
                    "method": request.payment_method_alias or "UPI",
                }
                return PaymentExecutionResult(
                    success=True,
                    status="SUCCESS",
                    payment_id=request.transaction_id,
                    provider_payment_id=order_id,
                    amount=request.amount,
                    currency=request.currency,
                    attempt_number=request.attempt_number,
                    timestamp=now,
                    raw_response=sanitized_response,
                    response_payload=sanitized_response,
                )

            # 5. Handle HTTP API Errors
            mapped_code, error_msg = self._map_razorpay_error(status_code, data)
            raw_err_obj = data.get("error", {}) if isinstance(data, dict) else {}
            raw_err_code = raw_err_obj.get("code") if isinstance(raw_err_obj, dict) else None
            sanitized_err_response = {
                "provider": "RazorpayPaymentProvider",
                "mode": "TEST",
                "http_status": status_code,
                "error_code": raw_err_code,
                "description": error_msg,
            }
            return PaymentExecutionResult(
                success=False,
                status="TIMEOUT" if mapped_code == PaymentFailureReason.TIMEOUT.value else "FAILED",
                payment_id=request.transaction_id,
                provider_payment_id=data.get("id") or f"rzp_err_{uuid.uuid4().hex[:8]}",
                amount=request.amount,
                currency=request.currency,
                attempt_number=request.attempt_number,
                error_code=mapped_code,
                error_message=error_msg,
                timestamp=now,
                raw_response=sanitized_err_response,
                response_payload=sanitized_err_response,
            )

        except (httpx.TimeoutException, httpx.ReadTimeout, httpx.ConnectTimeout):
            return PaymentExecutionResult(
                success=False,
                status="TIMEOUT",
                payment_id=request.transaction_id,
                provider_payment_id=f"rzp_timeout_{uuid.uuid4().hex[:8]}",
                amount=request.amount,
                currency=request.currency,
                attempt_number=request.attempt_number,
                error_code=PaymentFailureReason.TIMEOUT.value,
                error_message="Razorpay gateway request timed out.",
                timestamp=now,
                raw_response={"error": "TIMEOUT", "provider": "RazorpayPaymentProvider"},
                response_payload={"error": "TIMEOUT", "provider": "RazorpayPaymentProvider"},
            )
        except (httpx.NetworkError, httpx.ConnectError):
            return PaymentExecutionResult(
                success=False,
                status="FAILED",
                payment_id=request.transaction_id,
                provider_payment_id=f"rzp_neterr_{uuid.uuid4().hex[:8]}",
                amount=request.amount,
                currency=request.currency,
                attempt_number=request.attempt_number,
                error_code=PaymentFailureReason.NETWORK_ERROR.value,
                error_message="Network communication error connecting to Razorpay.",
                timestamp=now,
                raw_response={"error": "NETWORK_ERROR", "provider": "RazorpayPaymentProvider"},
                response_payload={"error": "NETWORK_ERROR", "provider": "RazorpayPaymentProvider"},
            )
        except Exception as exc:
            return PaymentExecutionResult(
                success=False,
                status="FAILED",
                payment_id=request.transaction_id,
                provider_payment_id=f"rzp_err_{uuid.uuid4().hex[:8]}",
                amount=request.amount,
                currency=request.currency,
                attempt_number=request.attempt_number,
                error_code=PaymentFailureReason.PROVIDER_ERROR.value,
                error_message=f"Razorpay provider exception: {str(exc)}",
                timestamp=now,
                raw_response={"error": "PROVIDER_EXCEPTION", "details": str(exc), "provider": "RazorpayPaymentProvider"},
                response_payload={"error": "PROVIDER_EXCEPTION", "details": str(exc), "provider": "RazorpayPaymentProvider"},
            )

    def get_status(self, provider_payment_id: str) -> PaymentExecutionResult:
        now = datetime.now(timezone.utc)
        if not self.key_id or not self.key_secret:
            return PaymentExecutionResult(
                success=False,
                status="FAILED",
                payment_id="unknown",
                provider_payment_id=provider_payment_id,
                amount=0.0,
                currency="INR",
                attempt_number=1,
                error_code=PaymentFailureReason.PROVIDER_ERROR.value,
                error_message="Razorpay credentials not configured.",
                timestamp=now,
                raw_response={"error": "MISSING_CREDENTIALS", "provider": "RazorpayPaymentProvider"},
                response_payload={"error": "MISSING_CREDENTIALS", "provider": "RazorpayPaymentProvider"},
            )

        is_order = str(provider_payment_id).startswith("order_")
        endpoint = f"{self.base_url}/orders/{provider_payment_id}" if is_order else f"{self.base_url}/payments/{provider_payment_id}"

        try:
            client = self._get_client()
            should_close = self._external_client is None
            try:
                response = client.get(
                    endpoint,
                    auth=(self.key_id, self.key_secret),
                )
            finally:
                if should_close:
                    client.close()

            if response.status_code == 200:
                data = response.json()
                status_raw = str(data.get("status") or "").lower()
                is_success = status_raw in ("created", "authorized", "captured", "paid")
                amount_inr = float(data.get("amount", 0)) / 100.0

                return PaymentExecutionResult(
                    success=is_success,
                    status="SUCCESS" if is_success else "FAILED",
                    payment_id=data.get("notes", {}).get("transaction_id", "unknown"),
                    provider_payment_id=provider_payment_id,
                    amount=amount_inr,
                    currency=data.get("currency", "INR"),
                    attempt_number=int(data.get("notes", {}).get("attempt_number", 1)),
                    error_code=None if is_success else PaymentFailureReason.DECLINED.value,
                    error_message=None if is_success else f"Payment in status '{status_raw}'",
                    timestamp=now,
                    raw_response={"provider": "RazorpayPaymentProvider", "status": status_raw, "order_id": provider_payment_id},
                    response_payload={"provider": "RazorpayPaymentProvider", "status": status_raw, "order_id": provider_payment_id},
                )
            else:
                return PaymentExecutionResult(
                    success=False,
                    status="FAILED",
                    payment_id="unknown",
                    provider_payment_id=provider_payment_id,
                    amount=0.0,
                    currency="INR",
                    attempt_number=1,
                    error_code=PaymentFailureReason.PROVIDER_ERROR.value,
                    error_message=f"Failed to retrieve Razorpay payment status (HTTP {response.status_code})",
                    timestamp=now,
                    raw_response={"error": "LOOKUP_FAILED", "http_status": response.status_code},
                    response_payload={"error": "LOOKUP_FAILED", "http_status": response.status_code},
                )
        except Exception as exc:
            return PaymentExecutionResult(
                success=False,
                status="FAILED",
                payment_id="unknown",
                provider_payment_id=provider_payment_id,
                amount=0.0,
                currency="INR",
                attempt_number=1,
                error_code=PaymentFailureReason.PROVIDER_ERROR.value,
                error_message=f"Exception checking Razorpay status: {str(exc)}",
                timestamp=now,
                raw_response={"error": "LOOKUP_EXCEPTION", "details": str(exc)},
                response_payload={"error": "LOOKUP_EXCEPTION", "details": str(exc)},
            )

    def retry(self, request: PaymentExecutionRequest) -> PaymentExecutionResult:
        return self.create_payment(request)


def get_payment_provider(
    settings: Optional[Settings] = None,
    mode: Union[MockPaymentMode, str] = MockPaymentMode.SUCCESS,
) -> PaymentProvider:
    """
    Authoritative provider factory.
    Selects provider based on settings or environment:
    - If PAYMENT_PROVIDER == "RAZORPAY": returns RazorpayPaymentProvider (requires credentials)
    - If PAYMENT_PROVIDER == "MOCK" (default): returns MockPaymentProvider
    - Any other value: raises ValueError
    """
    SUPPORTED_PROVIDERS = {"MOCK", "RAZORPAY"}

    s = settings or get_settings()
    provider_type = (getattr(s, "payment_provider", None) or "MOCK").upper().strip()

    if provider_type not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Invalid PAYMENT_PROVIDER='{provider_type}'. "
            f"Supported values: {', '.join(sorted(SUPPORTED_PROVIDERS))}."
        )

    if provider_type == "RAZORPAY":
        key_id = str(getattr(s, "razorpay_key_id", "") or "").strip()
        key_secret = str(getattr(s, "razorpay_key_secret", "") or "").strip()
        if not key_id or not key_secret:
            raise ValueError(
                "PAYMENT_PROVIDER=RAZORPAY requires both RAZORPAY_KEY_ID and "
                "RAZORPAY_KEY_SECRET environment variables to be set."
            )
        return RazorpayPaymentProvider(key_id=key_id, key_secret=key_secret)

    return MockPaymentProvider(mode=mode)

