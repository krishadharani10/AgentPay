import uuid
import pytest
from app.models.audit_log import AuditLog
from app.models.transaction import Transaction
from sqlalchemy import select


class TestAPIEndpoints:
    def test_get_merchants(self, client, test_seed_data):
        """Test GET /api/merchants endpoint."""
        response = client.get("/api/merchants")
        assert response.status_code == 200
        merchants = response.json()
        assert len(merchants) >= 5
        names = [m["name"] for m in merchants]
        assert "Torrent Power" in names
        assert "Netflix" in names
        assert "Spotify" in names
        assert "MakeMyTrip" in names
        assert "Amazon" in names

    def test_get_policies(self, client, test_seed_data):
        """Test GET /api/policies endpoint."""
        response = client.get("/api/policies")
        assert response.status_code == 200
        policies = response.json()
        assert len(policies) >= 1
        assert policies[0]["max_transaction_amount"] == 5000.0
        assert policies[0]["daily_spending_limit"] == 10000.0

    def test_get_wallet(self, client, test_seed_data):
        """Test GET /api/wallet endpoint."""
        response = client.get("/api/wallet")
        assert response.status_code == 200
        wallet_data = response.json()
        assert wallet_data["status"] == "ACTIVE"
        assert wallet_data["daily_spending_limit"] == 10000.0
        assert wallet_data["per_transaction_limit"] == 5000.0
        assert "current_daily_spent" in wallet_data
        assert "remaining_daily_budget" in wallet_data
        assert len(wallet_data["payment_methods"]) >= 1

    def test_policy_evaluate_approved_creates_audit_log(self, client, test_seed_data, db_session):
        """Test POST /api/policy/evaluate with valid ₹1,240 utility payment."""
        payload = {
            "merchant_name": "Torrent Power",
            "amount": 1240.0,
            "category": "utilities",
            "currency": "INR",
            "idempotency_key": "test_torrent_power_001",
        }
        response = client.post("/api/policy/evaluate", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["approved"] is True
        assert data["decision_code"] == "APPROVED"
        assert data["remaining_daily_budget"] == 8760.0
        assert data["audit_log_id"] is not None

        # Verify AuditLog created in DB
        audit = db_session.get(AuditLog, uuid.UUID(data["audit_log_id"]))
        assert audit is not None
        assert audit.event_type == "POLICY_EVALUATION"
        assert audit.decision == "APPROVED"
        assert audit.metadata_payload["merchant_name"] == "Torrent Power"
        assert audit.metadata_payload["amount"] == 1240.0

    def test_policy_evaluate_netflix_approved(self, client, test_seed_data):
        """Test POST /api/policy/evaluate with ₹3,000 Netflix subscription."""
        payload = {
            "merchant_name": "Netflix",
            "amount": 3000.0,
            "category": "subscriptions",
        }
        response = client.post("/api/policy/evaluate", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["approved"] is True
        assert data["decision_code"] == "APPROVED"
        assert data["remaining_daily_budget"] == 7000.0

    def test_policy_evaluate_above_limit_rejected(self, client, test_seed_data, db_session):
        """Test POST /api/policy/evaluate with ₹6,000 amount exceeding limit."""
        payload = {
            "merchant_name": "MakeMyTrip",
            "amount": 6000.0,
            "category": "travel",
            "idempotency_key": "test_mmt_over_limit",
        }
        response = client.post("/api/policy/evaluate", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["approved"] is False
        assert data["decision_code"] == "TX_LIMIT_EXCEEDED"
        assert data["audit_log_id"] is not None

        # Verify AuditLog entry for rejection
        audit = db_session.get(AuditLog, uuid.UUID(data["audit_log_id"]))
        assert audit is not None
        assert audit.decision == "REJECTED"
        assert "TX_LIMIT_EXCEEDED" in audit.reason or "exceeds" in audit.reason

    def test_policy_evaluate_blocked_category_rejected(self, client, test_seed_data):
        """Test POST /api/policy/evaluate with blocked category."""
        payload = {
            "merchant_name": "Crypto Exchange",
            "amount": 1000.0,
            "category": "crypto",
        }
        response = client.post("/api/policy/evaluate", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["approved"] is False
        assert data["decision_code"] == "CATEGORY_BLOCKED"

    def test_get_transactions_and_audit_logs(self, client, test_seed_data):
        """Test GET /api/transactions and GET /api/audit-logs endpoints."""
        tx_resp = client.get("/api/transactions")
        assert tx_resp.status_code == 200

        audit_resp = client.get("/api/audit-logs")
        assert audit_resp.status_code == 200
        logs = audit_resp.json()
        assert isinstance(logs, list)
