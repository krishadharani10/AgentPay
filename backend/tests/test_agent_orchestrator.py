import uuid
import pytest
from app.agents.orchestrator import AgentOrchestrator
from app.agents.tools import (
    get_wallet_policy,
    get_bill,
    evaluate_payment,
    create_payment,
    get_payment_status,
    retry_payment,
)
from app.services.payment_adapter import MockPaymentAdapter
from app.models.transaction import Transaction
from app.models.policy import Policy


class TestAgentOrchestration:
    def test_1_allowed_payment(self, db_session, test_seed_data):
        """Test 1: Given valid bill and policy, evaluation ALLOWED, payment created, status SUCCESS, persisted."""
        orchestrator = AgentOrchestrator(adapter=MockPaymentAdapter(default_failure=False))
        result = orchestrator.process_request(
            db_session,
            message="Pay my Torrent Power electricity bill of 1240",
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
        )
        assert result["success"] is True
        assert result["decision"] == "ALLOWED"
        assert result["payment_status"] == "SUCCESS"
        assert result["payment_id"] is not None

        # Verify persisted in database
        tx = db_session.get(Transaction, uuid.UUID(result["payment_id"]))
        assert tx is not None
        assert tx.status == "SUCCESS"
        assert tx.amount == 1240.0

    def test_2_transaction_limit_exceeded(self, db_session, test_seed_data):
        """Test 2: Given per_transaction_limit = 5000 and amount = 6000 -> DENIED, payment NOT created."""
        orchestrator = AgentOrchestrator(adapter=MockPaymentAdapter())
        result = orchestrator.process_request(
            db_session,
            message="Pay my hotel booking of 6000 at MakeMyTrip",
            merchant_name="MakeMyTrip",
            amount=6000.0,
            category="travel",
        )
        assert result["success"] is False
        assert result["decision"] == "DENIED"
        assert result["payment_id"] is None
        assert result["payment_status"] == "REJECTED"
        assert "TX_LIMIT_EXCEEDED" in result["decision_code"] or "MULTIPLE" in result["decision_code"]

    def test_3_category_not_allowed(self, db_session, test_seed_data):
        """Test 3: Given blocked category (crypto/gambling) -> DENIED, payment NOT created."""
        orchestrator = AgentOrchestrator(adapter=MockPaymentAdapter())
        result = orchestrator.process_request(
            db_session,
            message="Transfer 500 for crypto investment",
            merchant_name="Crypto Exchange",
            amount=500.0,
            category="crypto",
        )
        assert result["success"] is False
        assert result["decision"] == "DENIED"
        assert result["payment_id"] is None
        assert result["decision_code"] == "CATEGORY_BLOCKED"

    def test_4_merchant_not_allowed(self, db_session, test_seed_data):
        """Test 4: When merchant whitelist is active and merchant is omitted -> DENIED."""
        policy = test_seed_data["policy"]
        policy.allowed_merchants = ["Torrent Power", "Netflix"]
        db_session.commit()

        orchestrator = AgentOrchestrator(adapter=MockPaymentAdapter())
        result = orchestrator.process_request(
            db_session,
            message="Pay 500 to Spotify for music",
            merchant_name="Spotify",
            amount=500.0,
            category="subscriptions",
        )
        assert result["success"] is False
        assert result["decision"] == "DENIED"
        assert result["decision_code"] == "MERCHANT_NOT_ALLOWED"

    def test_5_insufficient_wallet_budget(self, db_session, test_seed_data):
        """Test 5: When requested amount exceeds remaining daily spending limit -> DENIED."""
        # Seed an existing large transaction for today to exhaust budget
        agent = test_seed_data["agent"]
        wallet = test_seed_data["wallet"]
        prior_tx = Transaction(
            id=uuid.uuid4(),
            idempotency_key=f"prior_tx_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
            wallet_id=wallet.id,
            merchant_name="MakeMyTrip",
            category="travel",
            amount=9000.0,
            status="SUCCESS",
            currency="INR",
        )
        db_session.add(prior_tx)
        db_session.commit()

        # Try to pay ₹2,000 when only ₹1,000 budget remains (limit is ₹10,000)
        orchestrator = AgentOrchestrator(adapter=MockPaymentAdapter())
        result = orchestrator.process_request(
            db_session,
            message="Pay 2000 for utilities",
            merchant_name="Torrent Power",
            amount=2000.0,
            category="utilities",
        )
        assert result["success"] is False
        assert result["decision"] == "DENIED"
        assert result["decision_code"] == "DAILY_LIMIT_EXCEEDED"

    def test_6_payment_failure(self, db_session, test_seed_data):
        """Test 6: Configure MockPaymentAdapter to fail -> payment recorded as FAILED, status retrievable."""
        failing_adapter = MockPaymentAdapter(default_failure=True, failure_reason="Bank Gateway Down")
        orchestrator = AgentOrchestrator(adapter=failing_adapter)
        result = orchestrator.process_request(
            db_session,
            message="Pay 1240 to Torrent Power",
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            force_failure=True,
        )
        assert result["success"] is False
        assert result["payment_status"] == "FAILED"
        payment_id = result["payment_id"]
        assert payment_id is not None

        # Verify status retrievable
        status_data = get_payment_status(db_session, uuid.UUID(payment_id))
        assert status_data["status"] == "FAILED"
        assert status_data["amount"] == 1240.0

    def test_7_retry_failed_payment(self, db_session, test_seed_data):
        """Test 7: Given a FAILED payment, retry is allowed, new attempt recorded, no duplicate payment, final status SUCCESS."""
        # 1. First trigger a failed payment
        failing_adapter = MockPaymentAdapter(default_failure=True)
        orchestrator = AgentOrchestrator(adapter=failing_adapter)
        res1 = orchestrator.process_request(
            db_session,
            message="Pay 699 for Spotify",
            merchant_name="Spotify",
            amount=699.0,
            category="subscriptions",
            force_failure=True,
        )
        assert res1["payment_status"] == "FAILED"
        payment_id = uuid.UUID(res1["payment_id"])

        # 2. Retry the payment using retry_payment tool
        working_adapter = MockPaymentAdapter(default_failure=False)
        retry_res = retry_payment(db_session, payment_id=payment_id, adapter=working_adapter)
        assert retry_res["success"] is True
        assert retry_res["status"] == "SUCCESS"
        assert retry_res["attempt_number"] == 2

        # 3. Verify status from DB
        status_data = get_payment_status(db_session, payment_id)
        assert status_data["status"] == "SUCCESS"
        assert status_data["attempt"] == 2

    def test_8_successful_payment_cannot_be_retried(self, db_session, test_seed_data):
        """Test 8: Given a SUCCESS payment, retry must be rejected/prevented."""
        orchestrator = AgentOrchestrator(adapter=MockPaymentAdapter(default_failure=False))
        res = orchestrator.process_request(
            db_session,
            message="Pay 699 for Spotify",
            merchant_name="Spotify",
            amount=699.0,
            category="subscriptions",
        )
        assert res["success"] is True
        payment_id = uuid.UUID(res["payment_id"])

        # Attempt to retry the successful payment
        retry_res = retry_payment(db_session, payment_id=payment_id)
        assert retry_res["success"] is False
        assert retry_res["status"] == "RETRY_REJECTED"
        assert "already completed successfully" in retry_res["error_message"]

    def test_9_agent_cannot_bypass_policy(self, db_session, test_seed_data):
        """Test 9: Critical Security Invariant - direct call to create_payment with violating payload is rejected."""
        # Direct call to create_payment trying to bypass evaluation
        violating_req = {
            "merchant_name": "Casino Royale",
            "amount": 100000.0,  # Huge amount violating both tx & daily limit
            "category": "gambling",  # Blocked category
        }
        res = create_payment(db_session, violating_req, adapter=MockPaymentAdapter())
        assert res["success"] is False
        assert res["status"] == "REJECTED"
        assert res["decision"] == "DENIED"

    def test_10_api_agent_run_endpoint(self, client, test_seed_data):
        """Test 10: Verify POST /api/agent/run endpoint for allowed and denied scenarios."""
        # 1. Test Allowed payment via API
        resp_allowed = client.post(
            "/api/agent/run",
            json={"message": "Pay my Torrent Power electricity bill of 1240", "amount": 1240.0, "category": "utilities", "merchant_name": "Torrent Power"},
        )
        assert resp_allowed.status_code == 200
        data_allowed = resp_allowed.json()
        assert data_allowed["success"] is True
        assert data_allowed["decision"] == "ALLOWED"
        assert data_allowed["payment_status"] == "SUCCESS"

        # 2. Test Denied payment via API
        resp_denied = client.post(
            "/api/agent/run",
            json={"message": "Pay 7000 for travel", "amount": 7000.0, "category": "travel", "merchant_name": "MakeMyTrip"},
        )
        assert resp_denied.status_code == 200
        data_denied = resp_denied.json()
        assert data_denied["success"] is False
        assert data_denied["decision"] == "DENIED"
