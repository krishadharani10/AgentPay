import uuid
import pytest
from app.models.transaction import Transaction, TransactionStatus
from app.models.payment_attempt import PaymentAttempt
from app.models.audit_log import AuditLog
from app.models.payment_method import PaymentMethod


def test_health_extended_safe_fields(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ok", "degraded")
    assert data["database"] == "connected"
    assert "provider" in data
    assert data["provider"] in ("MOCK", "RAZORPAY")
    assert data["policy_engine"] == "active"
    # Ensure no secret credentials leaked
    raw_text = response.text
    assert "secret" not in raw_text.lower()
    assert "rzp_test_key_secret" not in raw_text


def test_get_transaction_by_id_success(client, db_session, test_seed_data):
    wallet = test_seed_data["wallet"]
    agent = test_seed_data["agent"]

    # Create test transaction
    tx_id = uuid.uuid4()
    tx = Transaction(
        id=tx_id,
        idempotency_key=f"tx_test_{tx_id.hex[:8]}",
        agent_id=agent.id,
        wallet_id=wallet.id,
        merchant_name="Amazon",
        category="shopping",
        amount=899.0,
        currency="INR",
        status=TransactionStatus.SUCCESS.value,
        decision_reason="Payment authorized by policy.",
    )
    db_session.add(tx)
    db_session.flush()

    # Create associated PaymentAttempt
    attempt = PaymentAttempt(
        id=uuid.uuid4(),
        transaction_id=tx.id,
        attempt_number=1,
        status="SUCCESS",
        provider_payment_id="pay_test_amazon_001",
    )
    db_session.add(attempt)

    # Create associated AuditLog
    audit = AuditLog(
        id=uuid.uuid4(),
        agent_id=agent.id,
        transaction_id=tx.id,
        event_type="POLICY_EVALUATION",
        action="EVALUATE_POLICY",
        decision="APPROVED",
        reason="Amazon ₹899 passed policy rules",
    )
    db_session.add(audit)
    db_session.commit()

    response = client.get(f"/api/transactions/{tx_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(tx_id)
    assert data["merchant_name"] == "Amazon"
    assert data["amount"] == 899.0
    assert data["status"] == "SUCCESS"
    assert len(data["payment_attempts"]) == 1
    assert data["payment_attempts"][0]["provider_payment_id"] == "pay_test_amazon_001"
    assert len(data["audit_logs"]) == 1
    assert data["audit_logs"][0]["decision"] == "APPROVED"


def test_get_transaction_by_id_404(client):
    random_id = uuid.uuid4()
    response = client.get(f"/api/transactions/{random_id}")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_transaction_data_isolation(client, db_session, test_seed_data):
    wallet = test_seed_data["wallet"]
    agent = test_seed_data["agent"]

    tx1 = Transaction(
        id=uuid.uuid4(),
        idempotency_key="tx_iso_1",
        agent_id=agent.id,
        wallet_id=wallet.id,
        merchant_name="Netflix",
        category="subscriptions",
        amount=3000.0,
        currency="INR",
        status=TransactionStatus.REJECTED.value,
    )
    tx2 = Transaction(
        id=uuid.uuid4(),
        idempotency_key="tx_iso_2",
        agent_id=agent.id,
        wallet_id=wallet.id,
        merchant_name="Torrent Power",
        category="utilities",
        amount=1240.0,
        currency="INR",
        status=TransactionStatus.SUCCESS.value,
    )
    db_session.add_all([tx1, tx2])
    db_session.flush()

    att2 = PaymentAttempt(
        id=uuid.uuid4(),
        transaction_id=tx2.id,
        attempt_number=1,
        status="SUCCESS",
        provider_payment_id="pay_torrent_only",
    )
    db_session.add(att2)
    db_session.commit()

    # Query tx1 -> should have 0 attempts
    res1 = client.get(f"/api/transactions/{tx1.id}")
    assert res1.status_code == 200
    assert len(res1.json()["payment_attempts"]) == 0

    # Query tx2 -> should have 1 attempt
    res2 = client.get(f"/api/transactions/{tx2.id}")
    assert res2.status_code == 200
    assert len(res2.json()["payment_attempts"]) == 1
    assert res2.json()["payment_attempts"][0]["provider_payment_id"] == "pay_torrent_only"


def test_audit_logs_transaction_id_filter(client, db_session, test_seed_data):
    agent = test_seed_data["agent"]
    tx_target = uuid.uuid4()
    tx_other = uuid.uuid4()

    log1 = AuditLog(
        id=uuid.uuid4(),
        agent_id=agent.id,
        transaction_id=tx_target,
        event_type="TEST_EVENT_TARGET",
        action="TEST",
        decision="APPROVED",
        reason="Target tx log",
    )
    log2 = AuditLog(
        id=uuid.uuid4(),
        agent_id=agent.id,
        transaction_id=tx_other,
        event_type="TEST_EVENT_OTHER",
        action="TEST",
        decision="APPROVED",
        reason="Other tx log",
    )
    db_session.add_all([log1, log2])
    db_session.commit()

    # Filter by transaction_id
    response = client.get(f"/api/audit-logs?transaction_id={tx_target}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["event_type"] == "TEST_EVENT_TARGET"
    assert data[0]["transaction_id"] == str(tx_target)
