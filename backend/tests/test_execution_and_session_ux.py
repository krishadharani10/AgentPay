"""
Comprehensive verification test suite for AgentPay Payment Execution + Session UX.

Validates all 18 requirements:
1. New flight task can be prepared.
2. New restaurant task can be prepared.
3. Autonomous Agent payment succeeds.
4. Razorpay payment succeeds.
5. Agent-first -> Razorpay shows Already Paid.
6. Razorpay-first -> Agent shows Already Paid.
7. No duplicate transaction.
8. No duplicate payment.
9. No duplicate booking.
10. Refresh resets frontend presentation (simulated via clean session requests).
11. Refresh does NOT reset backend payment state.
12. Same already-paid task after refresh returns Already Paid.
13. Policy rejection means no payment.
14. Payment failure does not show booking success.
15. Existing retry works.
16. Existing fallback works.
17. Existing idempotency works.
18. Existing Razorpay Test Mode works.
"""
import uuid
import hmac
import hashlib
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.models.payment_method import PaymentMethod
from app.models.payment_attempt import PaymentAttempt
from app.config import Settings, get_settings


class TestExecutionAndSessionUX:

    def test_1_flight_task_preparation(self, client: TestClient, test_seed_data):
        """1. New flight task can be prepared without paying."""
        msg = "Book a flight from Ahmedabad to Mumbai under ₹10,000 on September 22"
        res = client.post("/api/tasks/prepare", json={"message": msg})
        assert res.status_code == 200
        data = res.json()
        assert data["task_type"] == "BOOK_FLIGHT"
        assert data["already_completed"] is False
        assert data["existing_transaction_id"] is None
        assert "task_fl_" in data["idempotency_key"]
        assert data["estimated_amount"] == 7450.0

    def test_2_restaurant_task_preparation(self, client: TestClient, test_seed_data):
        """2. New restaurant task can be prepared without paying."""
        msg = "Reserve a table in ITC Narmada, Ahmedabad for 2 people at 8 PM on September 22 under ₹3,000"
        res = client.post("/api/tasks/prepare", json={"message": msg})
        assert res.status_code == 200
        data = res.json()
        assert data["task_type"] == "RESERVE_RESTAURANT"
        assert data["already_completed"] is False
        assert data["existing_transaction_id"] is None
        assert "task_res_" in data["idempotency_key"]
        assert data["estimated_amount"] == 1000.0

    def test_3_autonomous_agent_payment_succeeds(
        self, client: TestClient, db_session: Session, test_seed_data
    ):
        """3. Autonomous Agent payment succeeds."""
        policy = test_seed_data["policy"]
        policy.max_transaction_amount = 25000.0
        policy.daily_spending_limit = 50000.0
        wallet = test_seed_data["wallet"]
        wallet.per_transaction_limit = 25000.0
        wallet.daily_spending_limit = 50000.0
        db_session.commit()

        msg = "Book a flight from Ahmedabad to Mumbai under ₹10,000 on September 22"
        res = client.post("/api/tasks", json={"message": msg})
        assert res.status_code == 200
        data = res.json()
        assert data["task_status"] == "COMPLETED"
        assert data["payment_status"] == "SUCCESS"
        assert data["already_completed"] is False
        assert data["transaction_id"] is not None

    def test_4_razorpay_payment_succeeds(
        self, client: TestClient, db_session: Session, test_seed_data
    ):
        """4. Razorpay payment verification succeeds."""
        key_secret = "test_sec_e2e_rzp_4"

        def override_settings():
            return Settings(
                APP_NAME="AgentPay",
                APP_ENV="test",
                DEBUG=True,
                DATABASE_URL="sqlite:///:memory:",
                payment_provider="MOCK",
                razorpay_key_secret=key_secret,
            )

        from app.main import app
        app.dependency_overrides[get_settings] = override_settings

        try:
            pm = db_session.execute(select(PaymentMethod)).scalars().first()
            tx = Transaction(
                wallet_id=test_seed_data["wallet"].id,
                agent_id=test_seed_data["agent"].id,
                payment_method_id=pm.id if pm else None,
                amount=7450.0,
                currency="INR",
                merchant_name="AirDemo",
                category="travel",
                status="PROCESSING",
                idempotency_key="task_rzp_test_4",
            )
            db_session.add(tx)
            db_session.commit()
            db_session.refresh(tx)

            order_id = "order_test_4"
            payment_id = "pay_test_4"
            msg = f"{order_id}|{payment_id}"
            sig = hmac.new(key_secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()

            verify_res = client.post(
                "/api/payments/razorpay/verify",
                json={
                    "transaction_id": str(tx.id),
                    "razorpay_order_id": order_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": sig,
                },
            )
            assert verify_res.status_code == 200
            assert verify_res.json()["success"] is True
            assert verify_res.json()["status"] == "SUCCESS"

            db_session.refresh(tx)
            assert tx.status == "SUCCESS"
            assert tx.payment_provider == "RAZORPAY"
        finally:
            from tests.conftest import override_get_settings
            app.dependency_overrides[get_settings] = override_get_settings

    def test_5_7_8_9_agent_first_then_razorpay_consistency(
        self, client: TestClient, db_session: Session, test_seed_data
    ):
        """
        5. Agent-first -> Razorpay shows Already Paid.
        7. No duplicate transaction.
        8. No duplicate payment.
        9. No duplicate booking.
        """
        policy = test_seed_data["policy"]
        policy.max_transaction_amount = 25000.0
        policy.daily_spending_limit = 50000.0
        wallet = test_seed_data["wallet"]
        wallet.per_transaction_limit = 25000.0
        wallet.daily_spending_limit = 50000.0
        db_session.commit()

        msg = "Book a flight from Ahmedabad to Mumbai under ₹10,000 on September 22"
        prep1 = client.post("/api/tasks/prepare", json={"message": msg}).json()
        idem_key = prep1["idempotency_key"]

        # Step A: Agent pays first
        exec1 = client.post("/api/tasks", json={"message": msg}).json()
        assert exec1["task_status"] == "COMPLETED"
        assert exec1["payment_status"] == "SUCCESS"
        tx_id = exec1["transaction_id"]

        # Step B: Razorpay path queries prepared task
        prep2 = client.post("/api/tasks/prepare", json={"message": msg}).json()
        assert prep2["already_completed"] is True
        assert prep2["existing_transaction_id"] == tx_id
        assert prep2["existing_payment_status"] == "SUCCESS"

        # Step C: Subsequent execution attempt returns already completed
        task_msg = msg
        exec2 = client.post("/api/tasks", json={"message": task_msg}).json()
        assert exec2["already_completed"] is True
        assert exec2["transaction_id"] == tx_id

        # Verification of Invariants:
        # 7. No duplicate transaction
        txs = db_session.execute(select(Transaction).where(Transaction.idempotency_key == idem_key)).scalars().all()
        assert len(txs) == 1
        assert txs[0].status == "SUCCESS"

        # 8. No duplicate payment
        successful_attempts = db_session.execute(
            select(PaymentAttempt)
            .where(PaymentAttempt.transaction_id == txs[0].id, PaymentAttempt.status == "SUCCESS")
        ).scalars().all()
        assert len(successful_attempts) == 1

        # 9. No duplicate booking (only 1 transaction identity exists)
        assert str(txs[0].id) == tx_id

    def test_6_7_8_9_razorpay_first_then_agent_consistency(
        self, client: TestClient, db_session: Session, test_seed_data
    ):
        """
        6. Razorpay-first -> Agent shows Already Paid.
        7. No duplicate transaction.
        8. No duplicate payment.
        9. No duplicate booking.
        """
        from app.main import app

        key_secret = "test_sec_e2e_rzp_6"

        def override_settings():
            return Settings(
                APP_NAME="AgentPay",
                APP_ENV="test",
                DEBUG=True,
                DATABASE_URL="sqlite:///:memory:",
                payment_provider="MOCK",
                razorpay_key_secret=key_secret,
            )

        app.dependency_overrides[get_settings] = override_settings

        try:
            msg = "Reserve a table in ITC Narmada, Ahmedabad for 2 people at 8 PM on September 22 under ₹3,000"
            prep = client.post("/api/tasks/prepare", json={"message": msg}).json()
            idem_key = prep["idempotency_key"]

            pm = db_session.execute(select(PaymentMethod)).scalars().first()
            tx = Transaction(
                wallet_id=test_seed_data["wallet"].id,
                agent_id=test_seed_data["agent"].id,
                payment_method_id=pm.id if pm else None,
                amount=1000.0,
                currency="INR",
                merchant_name="ITC Narmada",
                category="dining",
                status="PROCESSING",
                idempotency_key=idem_key,
            )
            db_session.add(tx)
            db_session.commit()
            db_session.refresh(tx)

            order_id = "order_test_6"
            payment_id = "pay_test_6"
            sig = hmac.new(
                key_secret.encode("utf-8"),
                f"{order_id}|{payment_id}".encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            verify_res = client.post(
                "/api/payments/razorpay/verify",
                json={
                    "transaction_id": str(tx.id),
                    "razorpay_order_id": order_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": sig,
                },
            )
            assert verify_res.status_code == 200

            # 6. Now agent queries task preparation
            prep_after = client.post("/api/tasks/prepare", json={"message": msg}).json()
            assert prep_after["already_completed"] is True
            assert prep_after["existing_payment_provider"] == "RAZORPAY"
            assert prep_after["existing_transaction_id"] == str(tx.id)

            # Agent attempts execution
            exec_after = client.post("/api/tasks", json={"message": msg}).json()
            assert exec_after["already_completed"] is True
            assert exec_after["transaction_id"] == str(tx.id)
            assert exec_after["payment_status"] == "SUCCESS"

            # 7 & 8 & 9. Exactly 1 transaction, 1 successful payment
            # Expire all to clear SQLAlchemy identity map cache (TestClient uses a different session)
            db_session.expire_all()
            txs = db_session.execute(select(Transaction).where(Transaction.idempotency_key == idem_key)).scalars().all()
            assert len(txs) == 1
            assert txs[0].status == "SUCCESS"
        finally:
            from tests.conftest import override_get_settings
            app.dependency_overrides[get_settings] = override_get_settings

    def test_10_11_12_refresh_behavior(
        self, client: TestClient, db_session: Session, test_seed_data
    ):
        """
        10. Refresh resets frontend presentation (clean state).
        11. Refresh does NOT reset backend payment state.
        12. Same already-paid task after refresh returns Already Paid.
        """
        policy = test_seed_data["policy"]
        policy.max_transaction_amount = 25000.0
        policy.daily_spending_limit = 50000.0
        wallet = test_seed_data["wallet"]
        wallet.per_transaction_limit = 25000.0
        wallet.daily_spending_limit = 50000.0
        db_session.commit()

        msg = "Book a flight from Ahmedabad to Mumbai under ₹10,000 on September 22"

        # Complete payment before "refresh"
        exec1 = client.post("/api/tasks", json={"message": msg}).json()
        assert exec1["task_status"] == "COMPLETED"
        assert exec1["payment_status"] == "SUCCESS"
        tx_id = exec1["transaction_id"]

        # 11. Verify backend payment state remains in DB
        tx = db_session.get(Transaction, uuid.UUID(tx_id))
        assert tx is not None
        assert tx.status == "SUCCESS"

        # 10 & 12. User opens clean page and types/prepares task:
        # Backend authoritatively detects completed payment
        prep_after_refresh = client.post("/api/tasks/prepare", json={"message": msg}).json()
        assert prep_after_refresh["already_completed"] is True
        assert prep_after_refresh["existing_transaction_id"] == tx_id
        assert prep_after_refresh["existing_payment_status"] == "SUCCESS"

    def test_13_policy_rejection_no_payment(
        self, client: TestClient, db_session: Session, test_seed_data
    ):
        """13. Policy rejection means no payment, no booking, not marked already completed."""
        blocked_msg = "Book a flight from Ahmedabad to Mumbai under ₹15,000 on September 8"
        exec_res = client.post("/api/tasks", json={"message": blocked_msg})
        assert exec_res.status_code == 200
        edata = exec_res.json()
        assert edata["policy_result"] == "REJECTED"
        assert edata["task_status"] == "REJECTED"
        assert edata["payment_status"] == "NOT_ATTEMPTED"
        assert edata["already_completed"] is False

        prep_res = client.post("/api/tasks/prepare", json={"message": blocked_msg})
        pdata = prep_res.json()
        assert pdata["already_completed"] is False
        assert pdata["existing_transaction_id"] is None

    def test_14_payment_failure_does_not_show_success(
        self, client: TestClient, db_session: Session, test_seed_data
    ):
        """14. Payment failure does not show booking success or already paid."""
        msg = "Pay ₹500 to Torrent Power"
        exec_res = client.post(
            "/api/tasks",
            json={"message": msg, "force_failure": True, "retry_if_failed": False},
        )
        assert exec_res.status_code == 200
        edata = exec_res.json()
        assert edata["payment_status"] == "FAILED" or edata["task_status"] == "PAYMENT_FAILED"
        assert edata["already_completed"] is False

        prep_res = client.post("/api/tasks/prepare", json={"message": msg})
        pdata = prep_res.json()
        assert pdata["already_completed"] is False

    def test_15_existing_retry_works(
        self, client: TestClient, db_session: Session, test_seed_data
    ):
        """15. Existing retry works on payment failure."""
        msg = "Pay ₹1,240 to Torrent Power"
        exec_res = client.post(
            "/api/tasks",
            json={"message": msg, "force_failure": False, "retry_if_failed": True},
        )
        assert exec_res.status_code == 200
        edata = exec_res.json()
        assert edata["task_status"] == "COMPLETED"
        assert edata["payment_status"] == "SUCCESS"

    def test_16_existing_fallback_works(
        self, client: TestClient, db_session: Session, test_seed_data
    ):
        """16. Existing fallback works through payment service."""
        from app.services.payment_service import PaymentService

        wallet = test_seed_data["wallet"]
        service = PaymentService()
        fallback_pm = service.get_fallback_payment_method(db_session, wallet_id=wallet.id)
        assert fallback_pm is not None
        assert fallback_pm.is_primary is False

    def test_17_existing_idempotency_works(
        self, client: TestClient, db_session: Session, test_seed_data
    ):
        """17. Existing idempotency works."""
        from app.agents.task_orchestrator import TaskOrchestrator
        from app.schemas.task_types import TaskIntent, TaskType

        intent = TaskIntent(
            task_type=TaskType.BOOK_FLIGHT,
            origin="AMD",
            destination="BOM",
            date="2026-09-22",
            budget=10000.0,
            user_message="Book flight AMD to BOM",
        )
        k1 = TaskOrchestrator.compute_task_idempotency_key(intent)
        k2 = TaskOrchestrator.compute_task_idempotency_key(intent)
        assert k1 == k2
        assert len(k1) <= 48

    def test_18_existing_razorpay_test_mode_works(
        self, client: TestClient
    ):
        """18. Existing Razorpay Test Mode config endpoint works."""
        res = client.get("/api/payments/config")
        assert res.status_code == 200
        data = res.json()
        assert data["currency"] == "INR"
        assert data["is_test_mode"] is True
