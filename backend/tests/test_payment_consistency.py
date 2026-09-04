"""
Comprehensive Payment Consistency Test Suite for AgentPay.

Verifies:
1. Two execution paths (Autonomous Agent and Razorpay flow) operate on the same prepared task
   and the same underlying transaction identity.
2. If Autonomous Agent execution succeeds:
   - Transaction is recorded with status SUCCESS
   - Subsequent task execution or preparation returns already_completed=True
   - Exactly ONE transaction is created (no second charge / transaction)
3. If Razorpay verification succeeds:
   - Transaction is transitioned to SUCCESS
   - Subsequent task preparation/execution returns already_completed=True with the verified transaction ID
4. Rejected tasks (e.g. policy block) do NOT mark the task as already_completed.
5. Failed payments do NOT mark the task as already_completed.
6. Deterministic idempotency key computation guarantees single source of truth across prepare and execute.
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
from app.models.audit_log import AuditLog
from app.models.wallet import Wallet
from app.services.wallet_service import WalletService
from app.agents.task_orchestrator import TaskOrchestrator
from app.schemas.task_types import TaskType, TaskIntent
from app.services.payment_adapter import MockPaymentProvider, MockPaymentMode
from app.config import get_settings


class TestPaymentConsistency:

    def test_flight_task_single_transaction_consistency(
        self, client: TestClient, db_session: Session, test_seed_data
    ):
        """
        Scenario:
        1. Task is prepared (flight Ahmedabad -> Mumbai).
        2. Path A executes (Autonomous Agent) -> SUCCESS.
        3. Task is prepared again -> returns already_completed=True and existing_transaction_id.
        4. Re-running task -> returns already_completed=True, reuses exact transaction ID, no second charge.
        """
        # Ensure policy and wallet allow the flight amount
        policy = test_seed_data["policy"]
        policy.max_transaction_amount = 25000.0
        policy.daily_spending_limit = 50000.0

        wallet = test_seed_data["wallet"]
        wallet.per_transaction_limit = 25000.0
        wallet.daily_spending_limit = 50000.0
        db_session.commit()

        task_msg = "Book a flight from Ahmedabad to Mumbai under ₹10,000 on September 22"

        # Step 1: Prepare task
        prep_res1 = client.post("/api/tasks/prepare", json={"message": task_msg})
        assert prep_res1.status_code == 200
        prep1 = prep_res1.json()
        assert prep1["already_completed"] is False
        assert prep1["existing_transaction_id"] is None
        idem_key = prep1["idempotency_key"]
        assert "task_fl_" in idem_key

        # Step 2: Path A executes
        exec_res1 = client.post("/api/tasks", json={"message": task_msg})
        assert exec_res1.status_code == 200
        exec1 = exec_res1.json()
        assert exec1["task_status"] == "COMPLETED"
        assert exec1["payment_status"] == "SUCCESS"
        assert exec1["already_completed"] is False
        tx_id = exec1["transaction_id"]
        assert tx_id is not None

        # Step 3: Prepare task after Path A success
        prep_res2 = client.post("/api/tasks/prepare", json={"message": task_msg})
        assert prep_res2.status_code == 200
        prep2 = prep_res2.json()
        assert prep2["already_completed"] is True
        assert prep2["existing_transaction_id"] == tx_id
        assert prep2["existing_payment_status"] == "SUCCESS"
        assert prep2["idempotency_key"] == idem_key

        # Step 4: Subsequent execution attempt (Path A or Path B fallback)
        exec_res2 = client.post("/api/tasks", json={"message": task_msg})
        assert exec_res2.status_code == 200
        exec2 = exec_res2.json()
        assert exec2["task_status"] == "COMPLETED"
        assert exec2["payment_status"] == "SUCCESS"
        assert exec2["already_completed"] is True
        assert exec2["transaction_id"] == tx_id

        # Verify only 1 transaction exists in database
        tx_records = db_session.execute(
            select(Transaction).where(Transaction.idempotency_key == idem_key)
        ).scalars().all()
        assert len(tx_records) == 1
        assert tx_records[0].status == "SUCCESS"

    def test_razorpay_verification_marks_task_already_completed(
        self, client: TestClient, db_session: Session, test_seed_data
    ):
        """
        Scenario:
        1. Task is prepared.
        2. Transaction is initiated for the task.
        3. Razorpay payment verification succeeds.
        4. Querying prepare_task reflects already_completed=True with the verified transaction.
        5. Attempting execution returns already_completed=True.
        """
        from app.models.payment_method import PaymentMethod
        from app.config import Settings

        key_secret = "test_secret_for_signing_12345"

        def override_settings_for_razorpay():
            return Settings(
                APP_NAME="AgentPay",
                APP_ENV="test",
                DEBUG=True,
                DATABASE_URL="sqlite:///:memory:",
                payment_provider="MOCK",
                razorpay_key_secret=key_secret,
            )

        from app.config import get_settings
        from app.main import app

        app.dependency_overrides[get_settings] = override_settings_for_razorpay

        try:
            task_msg = "Book a flight from Ahmedabad to Mumbai under ₹10,000 on September 22"
            prep = client.post("/api/tasks/prepare", json={"message": task_msg}).json()
            idem_key = prep["idempotency_key"]

            pm = db_session.execute(select(PaymentMethod)).scalars().first()

            # Simulate creation of the transaction in DB for Razorpay checkout
            tx = Transaction(
                wallet_id=test_seed_data["wallet"].id,
                agent_id=test_seed_data["agent"].id,
                payment_method_id=pm.id if pm else None,
                amount=7450.0,
                currency="INR",
                merchant_name="AirDemo",
                category="travel",
                status="PROCESSING",
                idempotency_key=idem_key,
            )
            db_session.add(tx)
            db_session.commit()
            db_session.refresh(tx)

            # Generate valid signature
            order_id = "order_test_cons_123"
            payment_id = "pay_test_cons_456"
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
            vdata = verify_res.json()
            assert vdata["success"] is True
            assert vdata["status"] == "SUCCESS"

            # Now prepare_task MUST reflect already_completed=True
            prep_after = client.post("/api/tasks/prepare", json={"message": task_msg}).json()
            assert prep_after["already_completed"] is True
            assert prep_after["existing_transaction_id"] == str(tx.id)
            assert prep_after["existing_payment_status"] == "SUCCESS"

            # Executing the task MUST NOT charge again and return already_completed
            exec_after = client.post("/api/tasks", json={"message": task_msg}).json()
            assert exec_after["already_completed"] is True
            assert exec_after["transaction_id"] == str(tx.id)
            assert exec_after["task_status"] == "COMPLETED"
        finally:
            from tests.conftest import override_get_settings
            app.dependency_overrides[get_settings] = override_get_settings

    def test_policy_rejection_is_not_already_paid(
        self, client: TestClient, db_session: Session, test_seed_data
    ):
        """
        Scenario:
        1. User attempts a flight that exceeds limits (Policy Block).
        2. Execution returns policy_result='REJECTED', task_status='REJECTED'.
        3. prepare_task does NOT mark this task as already_completed.
        """
        blocked_msg = "Book a flight from Ahmedabad to Mumbai under ₹15,000 on September 8"

        # Execute rejected task
        exec_res = client.post("/api/tasks", json={"message": blocked_msg})
        assert exec_res.status_code == 200
        edata = exec_res.json()
        assert edata["policy_result"] == "REJECTED"
        assert edata["task_status"] == "REJECTED"
        assert edata["already_completed"] is False

        # Prepare check MUST NOT be marked already_completed
        prep_res = client.post("/api/tasks/prepare", json={"message": blocked_msg})
        assert prep_res.status_code == 200
        pdata = prep_res.json()
        assert pdata["already_completed"] is False
        assert pdata["existing_transaction_id"] is None

    def test_payment_failure_is_not_already_paid(
        self, client: TestClient, db_session: Session, test_seed_data
    ):
        """
        Scenario:
        1. Task is executed with forced failure (and no retries).
        2. prepare_task does NOT mark this task as already_completed.
        """
        msg = "Pay ₹500 to Torrent Power"
        # Force failure
        exec_res = client.post("/api/tasks", json={"message": msg, "force_failure": True, "retry_if_failed": False})
        assert exec_res.status_code == 200
        edata = exec_res.json()
        # Even if transaction failed, it is not SUCCESS
        assert edata["payment_status"] == "FAILED" or edata["task_status"] == "PAYMENT_FAILED"
        assert edata["already_completed"] is False

        # Prepare check MUST NOT be marked already_completed
        prep_res = client.post("/api/tasks/prepare", json={"message": msg})
        assert prep_res.status_code == 200
        pdata = prep_res.json()
        assert pdata["already_completed"] is False
