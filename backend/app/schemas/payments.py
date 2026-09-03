from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class PaymentProviderConfigResponse(BaseModel):
    provider: str = Field(..., description="Active payment provider: MOCK or RAZORPAY")
    key_id: Optional[str] = Field(default=None, description="Public Razorpay Key ID (never includes secret)")
    currency: str = Field(default="INR", description="Default transaction currency")
    is_test_mode: bool = Field(default=True, description="True if running in Test Mode")
    features: Dict[str, bool] = Field(
        default_factory=lambda: {
            "checkout_js": True,
            "direct_upi": True,
            "card_tokenization": True,
            "policy_guard": True,
        }
    )


class RazorpayVerifyRequest(BaseModel):
    transaction_id: str = Field(..., description="AgentPay Transaction UUID")
    razorpay_order_id: str = Field(..., description="Razorpay Order ID (e.g. order_XXXXX)")
    razorpay_payment_id: str = Field(..., description="Razorpay Payment ID (e.g. pay_XXXXX)")
    razorpay_signature: str = Field(..., description="HMAC-SHA256 signature from Razorpay Checkout")


class RazorpayVerifyResponse(BaseModel):
    success: bool
    verified: bool
    transaction_id: str
    status: str
    provider_payment_id: str
    message: str
    details: Optional[Dict[str, Any]] = None
