import hmac
import hashlib
import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import get_settings


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


def test_verify_razorpay_payment_signature(client, test_seed_data):
    # 1. First trigger an agent payment to create a transaction in db

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

    settings = get_settings()
    key_secret = getattr(settings, "razorpay_key_secret", "") or "dummy_secret_for_test"

    order_id = "order_test_checkout_123"
    payment_id = "pay_test_payment_456"
    msg = f"{order_id}|{payment_id}"
    sig = hmac.new(key_secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()

    # 2. Call verify endpoint
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
