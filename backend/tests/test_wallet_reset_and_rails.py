import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.wallet import Wallet
from app.models.transaction import Transaction
from app.models.audit_log import AuditLog
from app.models.payment_method import PaymentMethod


class TestWalletResetAndPaymentRails:
    def test_authoritative_spending_and_per_tx_limits(self, client: TestClient, test_seed_data):
        """Verify that wallet endpoint returns authoritative ₹15,000 daily limit and ₹8,000 per-tx limit."""
        response = client.get("/api/wallet")
        assert response.status_code == 200
        data = response.json()

        assert data["daily_spending_limit"] == 15000.0
        assert data["per_transaction_limit"] == 8000.0
        assert data["status"] == "ACTIVE"

        # Check configured payment rails
        methods = data["payment_methods"]
        assert len(methods) >= 2

        primary = next((m for m in methods if m["priority"] == 1), None)
        assert primary is not None
        assert primary["type"] == "UPI_VPA"
        assert primary["is_active"] is True
        assert primary["id"] is not None

        fallback = next((m for m in methods if m["priority"] == 2), None)
        assert fallback is not None
        assert fallback["type"] == "CARD_TOKEN"
        assert fallback["is_active"] is True
        assert fallback["id"] is not None

    def test_reset_daily_spending_endpoint(
        self, client: TestClient, db_session: Session, test_seed_data
    ):
        """
        Test resetting daily spending limit:
        1. Execute a successful transaction of ₹7,450.
        2. Verify current_daily_spent is ₹7,450 and remaining is ₹7,550.
        3. Call POST /api/wallet/reset-daily-spend.
        4. Verify current_daily_spent resets to ₹0 and remaining restores to ₹15,000.
        5. Verify immutable DAILY_SPEND_RESET audit log was created.
        """
        # 1. Execute a transaction
        tx_res = client.post(
            "/api/tasks",
            json={"message": "Book a flight from Ahmedabad to Mumbai under ₹10,000 on September 22"}
        )
        assert tx_res.status_code == 200
        tx_data = tx_res.json()
        assert tx_data["payment_status"] == "SUCCESS"
        assert tx_data["amount"] == 7450.0

        # 2. Check wallet before reset
        w_before = client.get("/api/wallet").json()
        assert w_before["current_daily_spent"] == 7450.0
        assert w_before["remaining_daily_budget"] == 7550.0

        # 3. Call reset endpoint
        reset_res = client.post("/api/wallet/reset-daily-spend")
        assert reset_res.status_code == 200
        reset_data = reset_res.json()
        assert reset_data["current_daily_spent"] == 0.0
        assert reset_data["remaining_daily_budget"] == 15000.0
        assert reset_data["daily_spending_limit"] == 15000.0

        # 4. Check wallet summary after reset
        w_after = client.get("/api/wallet").json()
        assert w_after["current_daily_spent"] == 0.0
        assert w_after["remaining_daily_budget"] == 15000.0

        # 5. Verify immutable audit log
        audit_records = db_session.execute(
            select(AuditLog).where(AuditLog.event_type == "DAILY_SPEND_RESET")
        ).scalars().all()
        assert len(audit_records) >= 1
        reset_log = audit_records[-1]
        assert reset_log.decision == "RESET"
        assert reset_log.metadata_payload.get("previous_spent") == 7450.0
        assert reset_log.metadata_payload.get("new_spent") == 0.0
