"""
Test Suite for Task Idempotency and Duplicate Execution Prevention.

Verifies:
1. Executing an autonomous task once succeeds and creates a transaction.
2. Re-executing the identical task returns 'already_completed', reuses the existing transaction ID,
   does NOT create another transaction, and does NOT charge the wallet again.
3. POST /api/tasks/prepare correctly identifies whether a task is already completed.
4. Custom idempotency keys are respected and prevent duplicate execution.
5. Audit logs properly record DUPLICATE_TASK_PREVENTED.
"""
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.models.audit_log import AuditLog
from app.models.wallet import Wallet
from app.services.wallet_service import WalletService
from app.agents.task_orchestrator import TaskOrchestrator
from app.schemas.task_types import TaskType, TaskIntent, TaskResponse
from app.services.payment_adapter import MockPaymentProvider, MockPaymentMode


class TestTaskIdempotencyAndDuplicates:

    def test_duplicate_flight_execution_prevents_recharge(
        self, client: TestClient, db_session: Session, test_seed_data
    ):
        """
        Executing the exact same flight booking twice:
        - 1st attempt: Creates transaction, transitions to SUCCESS, charges 3800.
        - 2nd attempt: Reuses transaction, returns SUCCESS + already_completed=True, does NOT charge again.
        """
        payload = {
            "message": "Book a flight from Mumbai to Delhi under ₹5,000 on September 11"
        }

        # ── 1st Execution ──
        res1 = client.post("/api/tasks", json=payload)
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["task_status"] == "COMPLETED"
        assert data1["payment_status"] == "SUCCESS"
        assert data1["transaction_id"] is not None
        assert data1["already_completed"] is False
        first_tx_id = data1["transaction_id"]

        # Check wallet spent after 1st execution
        wallet = db_session.execute(select(Wallet).limit(1)).scalar_one()
        spent_after_1st = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert spent_after_1st == 3800.0

        # ── 2nd Execution (Duplicate Attempt) ──
        res2 = client.post("/api/tasks", json=payload)
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["task_status"] == "COMPLETED"
        assert data2["payment_status"] == "SUCCESS"
        assert data2["transaction_id"] == first_tx_id
        assert data2["already_completed"] is True
        assert "Payment Already Completed" in data2["final_message"]

        # Verify wallet was NOT charged a second time
        spent_after_2nd = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert spent_after_2nd == 3800.0

        # Verify only 1 transaction exists in database
        tx_count = db_session.execute(
            select(Transaction).where(Transaction.id == uuid.UUID(first_tx_id))
        ).scalars().all()
        assert len(tx_count) == 1

        # Verify audit log recorded DUPLICATE_TASK_PREVENTED
        audit_events = db_session.execute(
            select(AuditLog.event_type)
            .where(AuditLog.event_type == "DUPLICATE_TASK_PREVENTED")
        ).scalars().all()
        assert len(audit_events) >= 1

    def test_prepare_task_endpoint_reflects_completion_state(
        self, client: TestClient, db_session: Session, test_seed_data
    ):
        """
        POST /api/tasks/prepare returns already_completed=False before execution,
        and already_completed=True after execution.
        """
        msg = "Book a flight from Mumbai to Delhi under ₹5,000 on September 11"

        # ── Step 1: Prepare before execution ──
        prep1 = client.post("/api/tasks/prepare", json={"message": msg})
        assert prep1.status_code == 200
        pdata1 = prep1.json()
        assert pdata1["task_type"] == "BOOK_FLIGHT"
        assert pdata1["already_completed"] is False
        assert pdata1["existing_transaction_id"] is None
        assert pdata1["estimated_amount"] == 3800.0
        assert pdata1["selected_option"]["flight_number"] == "AP701"
        assert pdata1["policy_compliant"] is True

        # ── Step 2: Execute task ──
        exec_res = client.post("/api/tasks", json={"message": msg})
        assert exec_res.status_code == 200
        edata = exec_res.json()
        assert edata["task_status"] == "COMPLETED"
        assert edata["transaction_id"] is not None
        tx_id = edata["transaction_id"]

        # ── Step 3: Prepare after execution ──
        prep2 = client.post("/api/tasks/prepare", json={"message": msg})
        assert prep2.status_code == 200
        pdata2 = prep2.json()
        assert pdata2["already_completed"] is True
        assert pdata2["existing_transaction_id"] == tx_id
        assert pdata2["existing_payment_status"] == "SUCCESS"

    def test_custom_idempotency_key_duplicate_prevention(
        self, client: TestClient, db_session: Session, test_seed_data
    ):
        """
        Explicit idempotency_key in TaskRunRequest is preserved and deduplicated.
        """
        custom_key = f"custom_idem_flight_{uuid.uuid4().hex[:8]}"
        payload = {
            "message": "Book a flight from Mumbai to Delhi under ₹5,000 on September 11",
            "idempotency_key": custom_key,
        }

        res1 = client.post("/api/tasks", json=payload)
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["already_completed"] is False
        tx_id = data1["transaction_id"]

        # Duplicate call with same explicit key
        res2 = client.post("/api/tasks", json=payload)
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["already_completed"] is True
        assert data2["transaction_id"] == tx_id

    def test_orchestrator_direct_duplicate_execution(
        self, db_session: Session, test_seed_data
    ):
        """
        Direct TaskOrchestrator invocation deduplicates already-completed transactions.
        """
        orchestrator = TaskOrchestrator(adapter=MockPaymentProvider(mode=MockPaymentMode.SUCCESS))
        intent = TaskIntent(
            task_type=TaskType.BOOK_FLIGHT,
            user_message="Book a flight from Mumbai to Delhi under ₹5,000 on September 11",
            origin="Mumbai",
            destination="Delhi",
            date="2026-09-11",
            max_budget=5000.0,
        )

        res1 = orchestrator.execute_task(db_session, task_intent=intent)
        assert res1.success is True
        assert res1.task_status == "COMPLETED"
        assert res1.already_completed is False
        tx_id = res1.payment_id

        # 2nd run
        res2 = orchestrator.execute_task(db_session, task_intent=intent)
        assert res2.success is True
        assert res2.task_status == "COMPLETED"
        assert res2.already_completed is True
        assert res2.payment_id == tx_id
        assert "Payment Already Completed" in res2.message
