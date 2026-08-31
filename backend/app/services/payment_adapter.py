import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, Union, List
from pydantic import BaseModel, Field


class MockPaymentMode(str, Enum):
    """
    Deterministic operational modes for MockPaymentProvider.
    Ensures zero random/flaky behavior in demos and tests.
    """
    SUCCESS = "SUCCESS"
    FAIL = "FAIL"
    TIMEOUT = "TIMEOUT"


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
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_response: Optional[Dict[str, Any]] = None


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
    Guarantees reproducible outcomes based on configured mode:
      - SUCCESS: Payment approved and settled instantly
      - FAIL: Payment rejected by gateway
      - TIMEOUT: Gateway request times out, leaving payment in TIMEOUT state
    """

    def __init__(
        self,
        mode: Union[MockPaymentMode, str] = MockPaymentMode.SUCCESS,
        default_failure: bool = False,
        failure_reason: Optional[str] = None,
    ):
        if default_failure:
            self.mode = MockPaymentMode.FAIL
        elif isinstance(mode, str):
            self.mode = MockPaymentMode(mode.upper())
        else:
            self.mode = mode

        self.failure_reason = failure_reason or "Simulated payment gateway timeout"
        self._provider_records: Dict[str, PaymentExecutionResult] = {}
        self.call_history: List[PaymentExecutionRequest] = []

    @property
    def call_count(self) -> int:
        return len(self.call_history)

    def create_payment(self, request: PaymentExecutionRequest) -> PaymentExecutionResult:
        self.call_history.append(request)

        # Resolve mode: check request metadata override or default instance mode
        effective_mode = self.mode
        if request.metadata:
            meta_mode = request.metadata.get("payment_mode") or request.metadata.get("mode")
            if meta_mode:
                effective_mode = MockPaymentMode(str(meta_mode).upper())
            elif request.metadata.get("force_failure") is True:
                effective_mode = MockPaymentMode.FAIL
            elif request.metadata.get("force_timeout") is True:
                effective_mode = MockPaymentMode.TIMEOUT
            elif request.metadata.get("force_failure") is False and "payment_mode" not in request.metadata:
                # If explicitly set force_failure=False and no mode override, default to SUCCESS
                effective_mode = MockPaymentMode.SUCCESS

        provider_id = f"pay_mock_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        if effective_mode == MockPaymentMode.FAIL:
            result = PaymentExecutionResult(
                success=False,
                status="FAILED",
                payment_id=request.transaction_id,
                provider_payment_id=provider_id,
                amount=request.amount,
                currency=request.currency,
                attempt_number=request.attempt_number,
                error_code="GATEWAY_REJECTED",
                error_message=self.failure_reason if self.failure_reason != "Simulated payment gateway timeout" else "Payment gateway rejected transaction",
                timestamp=now,
                raw_response={
                    "provider": "MockPaymentProvider",
                    "mode": "FAIL",
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
                error_code="GATEWAY_TIMEOUT",
                error_message="Payment gateway request timed out",
                timestamp=now,
                raw_response={
                    "provider": "MockPaymentProvider",
                    "mode": "TIMEOUT",
                    "simulated_timeout": True,
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
        )

    def retry(self, request: PaymentExecutionRequest) -> PaymentExecutionResult:
        return self.create_payment(request)


# Backward-compatible alias
MockPaymentAdapter = MockPaymentProvider
