import hmac
import hashlib
import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import get_settings, Settings
from app.database import get_db
from tests.conftest import override_get_db, SQLALCHEMY_TEST_DATABASE_URL


def test_get_payment_provider_config(client):
    response = client.get("/api/payments/config")
    assert response.status_code == 200
    data = response.json()
    assert "provider" in data
    assert data["provider"] in ("MOCK", "RAZORPAY")
    assert "is_test_mode" in data
    assert data["currency"] == "INR"
    # Security Rule #2: Secret key must never be exposed
    assert "key_secret" not in data
    assert "secret" not in data


def test_verify_razorpay_payment_signature(test_seed_data, db_session):
    """
    Verifies Razorpay signature validation end-to-end.
    Uses a self-contained test HMAC secret — no real credentials required.
    """
    TEST_KEY_SECRET = "test_razorpay_secret_payments_api"

    def override_settings_with_razorpay():
        return Settings(
            APP_NAME="AgentPay",
            APP_ENV="test",
            DEBUG=True,
            DATABASE_URL=SQLALCHEMY_TEST_DATABASE_URL,
            PAYMENT_PROVIDER="MOCK",
            RAZORPAY_KEY_ID="rzp_test_payments_api",
            RAZORPAY_KEY_SECRET=TEST_KEY_SECRET,
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = override_settings_with_razorpay

    with TestClient(app) as client:
        # 1. Create a transaction via agent run (MOCK provider)
        run_res = client.post(
            "/api/agent/run",
            json={
                "message": "Pay ₹500 to Amazon for stationary",
                "merchant_name": "Amazon",
                "amount": 500.0,
                "category": "shopping",
            },
        )
        assert run_res.status_code == 200
        run_data = run_res.json()
        tx_id = run_data.get("payment_id")
        assert tx_id is not None

        # 2. Generate a valid HMAC-SHA256 signature using the test secret
        order_id = "order_test_checkout_123"
        payment_id = "pay_test_payment_456"
        msg = f"{order_id}|{payment_id}"
        sig = hmac.new(
            TEST_KEY_SECRET.encode("utf-8"),
            msg.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # 3. Verify the signature via the endpoint
        verify_res = client.post(
            "/api/payments/razorpay/verify",
            json={
                "transaction_id": tx_id,
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": sig,
            },
        )
        assert verify_res.status_code == 200
        v_data = verify_res.json()
        assert v_data["success"] is True
        assert v_data["verified"] is True
        assert v_data["status"] == "SUCCESS"
        assert v_data["provider_payment_id"] == payment_id

    app.dependency_overrides.clear()
