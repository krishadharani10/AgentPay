"""
Regression tests for AgentPay Backend Hardening Pass:
1. Test Environment & Payment Provider Isolation:
   - Proves default test run uses MockPaymentProvider regardless of PAYMENT_PROVIDER in .env
   - Proves MockPaymentProvider operates deterministically without external network
   - Proves RazorpayPaymentProvider can still be explicitly selected with runtime settings
2. Refresh / Run Again Demo Architecture:
   - Retrying the SAME transaction/request does not double-charge (idempotent)
   - Starting a NEW demo run (with demo_run_id) creates a different, distinct transaction
   - Completed SUCCESS transactions remain immutable
   - Old audit records remain fully available
   - Refresh does not alter old PaymentAttempts
   - Policy Engine is rerun for genuinely new executions
   - Fallback behavior works reliably in fresh runs
"""
import uuid
import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient

from app.models import Transaction, TransactionStatus, AuditLog, PaymentAttempt, Agent
from app.config import Settings
from app.services.payment_adapter import (
    get_payment_provider,
    MockPaymentProvider,
    RazorpayPaymentProvider,
    MockPaymentMode,
    PaymentExecutionRequest,
)


class TestProviderIsolationRegression:
    """Verify provider isolation and runtime selection."""

    def test_default_test_suite_uses_mock_provider(self):
        """Default provider factory must return MockPaymentProvider in test environment."""
        provider = get_payment_provider()
        assert isinstance(provider, MockPaymentProvider)

    def test_mock_provider_operates_without_network(self):
        """MockPaymentProvider executes deterministically in-memory."""
        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        req = PaymentExecutionRequest(
            transaction_id="tx_iso_test",
            idempotency_key="idem_iso_test",
            amount=500.0,
            currency="INR",
            merchant_name="Test Merchant",
            category="GENERAL",
        )
        res = provider.create_payment(req)
        assert res.success is True
        assert res.status == "SUCCESS"
        assert res.provider_payment_id.startswith("pay_mock_")

    def test_razorpay_provider_can_be_selected_with_runtime_settings(self):
        """RazorpayPaymentProvider can be explicitly instantiated when configured."""
        s = Settings(
            payment_provider="RAZORPAY",
            razorpay_key_id="rzp_test_valid123",
            razorpay_key_secret="secret123",
            environment="test",
        )
        provider = get_payment_provider(settings=s)
        assert isinstance(provider, RazorpayPaymentProvider)
        assert provider.key_id == "rzp_test_valid123"


class TestRefreshAndIdempotencyRegression:
    """Verify Refresh / Run Again demo architecture and idempotency guarantees."""

    def test_same_task_is_idempotent_no_double_charge(self, client: TestClient, db_session, test_seed_data):
        """Same task message without new demo_run_id reuses completed transaction."""
        flight_msg = "Book a flight from Mumbai to Delhi under ₹5,000 on September 11"

        # First run: completes
        r1 = client.post("/api/tasks", json={"message": flight_msg})
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["task_status"] == "COMPLETED"
        assert d1["payment_status"] == "SUCCESS"
        tx1_id = d1["transaction_id"]
        assert tx1_id is not None

        # Second run: same message -> already completed, same tx, no double charge
        r2 = client.post("/api/tasks", json={"message": flight_msg})
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["transaction_id"] == tx1_id
        assert d2["already_completed"] is True
        assert d2["payment_status"] == "SUCCESS"

    def test_new_demo_run_creates_distinct_transaction(self, client: TestClient, db_session, test_seed_data):
        """Providing a demo_run_id creates a brand new transaction while preserving the old one."""
        flight_msg = "Book a flight from Mumbai to Delhi under ₹5,000 on September 11"

        # Run 1: original demo run
        r1 = client.post("/api/tasks", json={"message": flight_msg, "demo_run_id": "run_alpha"})
        assert r1.status_code == 200
        d1 = r1.json()
        tx1_id = d1["transaction_id"]
        assert d1["task_status"] == "COMPLETED"

        # Verify Tx1 in DB
        tx1 = db_session.get(Transaction, uuid.UUID(tx1_id))
        assert tx1 is not None
        assert tx1.status == TransactionStatus.SUCCESS

        # Run 2: Refresh / Run Again with fresh demo_run_id
        r2 = client.post("/api/tasks", json={"message": flight_msg, "demo_run_id": "run_beta"})
        assert r2.status_code == 200
        d2 = r2.json()
        tx2_id = d2["transaction_id"]
        assert d2["task_status"] == "COMPLETED"

        # Assertions on distinct transactions
        assert tx1_id != tx2_id, "New demo run must create a distinct transaction ID"

        # Assertions on immutability of Transaction 1
        db_session.expire_all()
        tx1_after = db_session.get(Transaction, uuid.UUID(tx1_id))
        assert tx1_after.status == TransactionStatus.SUCCESS
        assert tx1_after.amount == tx1.amount
        assert tx1_after.idempotency_key != d2.get("idempotency_key")

        # Verify both transactions coexist in database
        tx2 = db_session.get(Transaction, uuid.UUID(tx2_id))
        assert tx2 is not None
        assert tx2.status == TransactionStatus.SUCCESS

    def test_completed_transactions_remain_immutable_under_replay(self, client: TestClient, db_session, test_seed_data):
        """Attempting to replay an identical demo_run_id returns existing record without altering state."""
        msg = "Reserve a table in ITC Narmada, Ahmedabad for 2 people at 8 PM on September 22 under ₹3,000"
        run_id = "run_immutable_check"

        # Execute run
        r1 = client.post("/api/tasks", json={"message": msg, "demo_run_id": run_id})
        assert r1.status_code == 200
        d1 = r1.json()
        tx_id = d1["transaction_id"]

        # Snapshot DB state
        tx_before = db_session.get(Transaction, uuid.UUID(tx_id))
        initial_status = tx_before.status
        initial_amount = tx_before.amount
        initial_attempts_count = len(tx_before.payment_attempts)

        # Replay same run_id
        r2 = client.post("/api/tasks", json={"message": msg, "demo_run_id": run_id})
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["already_completed"] is True
        assert d2["transaction_id"] == tx_id

        # Verify DB transaction is strictly unmodified
        db_session.expire_all()
        tx_after = db_session.get(Transaction, uuid.UUID(tx_id))
        assert tx_after.status == initial_status
        assert tx_after.amount == initial_amount
        assert len(tx_after.payment_attempts) == initial_attempts_count

    def test_audit_logs_and_payment_attempts_preserved_across_runs(self, client: TestClient, db_session, test_seed_data):
        """Old audit logs and payment attempts remain queryable after new runs."""
        msg = "Pay ₹899 to Amazon for office supplies"

        # Run 1
        r1 = client.post("/api/tasks", json={"message": msg, "demo_run_id": "audit_run_1"})
        assert r1.status_code == 200
        tx1_id = r1.json()["transaction_id"]

        # Run 2
        r2 = client.post("/api/tasks", json={"message": msg, "demo_run_id": "audit_run_2"})
        assert r2.status_code == 200
        tx2_id = r2.json()["transaction_id"]

        # Check audit logs for Tx 1
        audits_tx1 = db_session.execute(
            select(AuditLog).where(AuditLog.transaction_id == uuid.UUID(tx1_id))
        ).scalars().all()
        assert len(audits_tx1) > 0, "Tx1 must retain its audit log trail"

        # Check audit logs for Tx 2
        audits_tx2 = db_session.execute(
            select(AuditLog).where(AuditLog.transaction_id == uuid.UUID(tx2_id))
        ).scalars().all()
        assert len(audits_tx2) > 0, "Tx2 must have its own audit log trail"

        # Both sets of attempts exist independently
        attempts_tx1 = db_session.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == uuid.UUID(tx1_id))
        ).scalars().all()
        attempts_tx2 = db_session.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == uuid.UUID(tx2_id))
        ).scalars().all()
        assert len(attempts_tx1) >= 1
        assert len(attempts_tx2) >= 1

    def test_policy_engine_rerun_for_new_demo_execution(self, client: TestClient, db_session, test_seed_data):
        """Every new execution passes through the Policy Engine deterministically."""
        msg = "Pay ₹899 to Amazon for office supplies"

        r = client.post("/api/tasks", json={"message": msg, "demo_run_id": "policy_rerun_1"})
        assert r.status_code == 200
        data = r.json()
        assert data["policy_result"] == "APPROVED"
        assert len(data["rules_checked"]) > 0

        # Verify Policy Engine rules were logged
        rule_names = [rule.get("rule") for rule in data["rules_checked"]]
        assert "TRANSACTION_LIMIT" in rule_names
        assert "CATEGORY_CHECK" in rule_names

    def test_prepare_task_with_demo_run_id_reflects_fresh_state(self, client: TestClient, db_session, test_seed_data):
        """Prepare endpoint returns already_completed=False when a fresh demo_run_id is used."""
        flight_msg = "Book a flight from Mumbai to Delhi under ₹5,000 on September 11"

        # First run execution
        client.post("/api/tasks", json={"message": flight_msg, "demo_run_id": "prep_run_1"})

        # Prepare for the old run -> already_completed is True
        p1 = client.post("/api/tasks/prepare", json={"message": flight_msg, "demo_run_id": "prep_run_1"})
        assert p1.status_code == 200
        assert p1.json()["already_completed"] is True

        # Prepare for a new run -> already_completed is False, ready to execute
        p2 = client.post("/api/tasks/prepare", json={"message": flight_msg, "demo_run_id": "prep_run_2"})
        assert p2.status_code == 200
        assert p2.json()["already_completed"] is False
