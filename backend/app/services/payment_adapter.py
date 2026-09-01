import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, Union, List
from pydantic import BaseModel, Field


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
