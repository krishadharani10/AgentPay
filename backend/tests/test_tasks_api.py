"""
API Tests for AgentPay Autonomous Tasks (POST /api/tasks).

Verifies the critical distinction between:
- USER TASK CONSTRAINTS (evaluated by domain commerce tools)
- DETERMINISTIC FINANCIAL AUTHORIZATION (evaluated by AgentPay Policy Engine)

Test Coverage:
1. Flight success: Tool constraint PASS + Policy APPROVED -> payment SUCCESS -> task COMPLETED
2. Flight policy rejection: Tool constraint PASS + Policy REJECTED -> payment NOT_ATTEMPTED -> task REJECTED
3. Restaurant reservation success: Tool constraint PASS + Policy APPROVED -> payment SUCCESS -> task COMPLETED
4. Restaurant reservation policy rejection: Tool constraint PASS + Policy REJECTED -> payment NOT_ATTEMPTED -> task REJECTED
5. Malformed task: empty message or missing fields
6. Unsupported task: route not served or impossible budget -> Tool constraint FAIL -> Policy NOT_EVALUATED
7. Direct payment backward compatibility via POST /api/tasks
"""
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models.agent import Agent
from app.models.policy import Policy
from app.models.wallet import Wallet
from app.models.transaction import Transaction


class TestTasksApi:

    def test_1_flight_success_endpoint(self, client: TestClient, db_session: Session, test_seed_data):
        """
        Flight booking request within user constraint and within policy limits.
        Expected:
          task_constraint_result: "PASS"
          policy_result: "APPROVED"
          payment_status: "SUCCESS"
          task_status: "COMPLETED"
          transaction_id: valid UUID string
        """
        payload = {
            "message": "Book a flight from Mumbai to Delhi under ₹5,000 on September 11"
        }

        response = client.post("/api/tasks", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert data["task_type"] == "BOOK_FLIGHT"
        assert data["task_constraint_result"] == "PASS"
        assert data["policy_result"] == "APPROVED"
        assert data["payment_status"] == "SUCCESS"
        assert data["task_status"] == "COMPLETED"
        assert data["transaction_id"] is not None
        assert data["amount"] == 3800.0
        assert data["merchant_name"] == "AirDemo"
        assert data["selected_option"] is not None
        assert data["selected_option"]["flight_number"] == "AP701"
        assert "Flight successfully booked" in data["final_message"]

        # Verify transaction in database
        tx = db_session.get(Transaction, uuid.UUID(data["transaction_id"]))
        assert tx is not None
        assert tx.status == "SUCCESS"
        assert tx.amount == 3800.0

    def test_2_flight_policy_rejection_endpoint(self, client: TestClient, db_session: Session, test_seed_data):
        """
        Flight booking request satisfies user's ₹10,000 budget (AP101 @ ₹7,450),
        but violates AgentPay Policy Engine per-transaction limit of ₹5,000.
        Expected:
          task_constraint_result: "PASS"
          policy_result: "REJECTED"
          payment_status: "NOT_ATTEMPTED"
          task_status: "REJECTED"
          transaction_id: None
        """
        # Ensure policy has per_transaction_limit = 5000
        policy = db_session.execute(select(Policy).limit(1)).scalar_one()
        policy.max_transaction_amount = 5000.0
        wallet = db_session.execute(select(Wallet).limit(1)).scalar_one()
        wallet.per_transaction_limit = 5000.0
        db_session.flush()

        payload = {
            "message": "Book a flight from Ahmedabad to Mumbai under ₹10,000 on September 5"
        }

        response = client.post("/api/tasks", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert data["task_type"] == "BOOK_FLIGHT"
        assert data["task_constraint_result"] == "PASS"     # User constraint PASS
        assert data["policy_result"] == "REJECTED"           # Policy REJECTED
        assert data["payment_status"] == "NOT_ATTEMPTED"     # No payment executed
        assert data["task_status"] == "REJECTED"             # Task denied
        assert data["transaction_id"] is None
        assert data["amount"] == 7450.0
        assert data["selected_option"] is not None
        assert data["selected_option"]["flight_number"] == "AP101"
        assert "REJECTED by Policy Engine" in data["final_message"]

    def test_3_restaurant_reservation_success_endpoint(self, client: TestClient, db_session: Session, test_seed_data):
        """
        Restaurant reservation deposit within user budget and policy limits.
        Expected:
          task_constraint_result: "PASS"
          policy_result: "APPROVED"
          payment_status: "SUCCESS"
          task_status: "COMPLETED"
          transaction_id: valid UUID string
        """
        payload = {
            "message": "Reserve a table in ITC Narmada, Ahmedabad for 2 people at 8 PM on September 22 under ₹3,000"
        }

        response = client.post("/api/tasks", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert data["task_type"] == "RESERVE_RESTAURANT"
        assert data["task_constraint_result"] == "PASS"
        assert data["policy_result"] == "APPROVED"
        assert data["payment_status"] == "SUCCESS"
        assert data["task_status"] == "COMPLETED"
        assert data["transaction_id"] is not None
        assert data["amount"] == 1000.0
        assert data["merchant_name"] == "ITC Narmada"
        assert data["selected_option"]["restaurant_name"] == "ITC Narmada"
        assert "Reservation confirmed" in data["final_message"]

        # Verify transaction in database
        tx = db_session.get(Transaction, uuid.UUID(data["transaction_id"]))
        assert tx is not None
        assert tx.status == "SUCCESS"
        assert tx.amount == 1000.0

    def test_4_restaurant_policy_rejection_endpoint(self, client: TestClient, db_session: Session, test_seed_data):
        """
        Restaurant reservation satisfies user constraint (ITC Narmada deposit ₹1,000 <= ₹3,000),
        but Policy Engine blocks dining category.
        Expected:
          task_constraint_result: "PASS"
          policy_result: "REJECTED"
          payment_status: "NOT_ATTEMPTED"
          task_status: "REJECTED"
          transaction_id: None
        """
        policy = db_session.execute(select(Policy).limit(1)).scalar_one()
        policy.blocked_categories = ["dining"]
        if "dining" in policy.allowed_categories:
            policy.allowed_categories.remove("dining")
        db_session.flush()

        payload = {
            "message": "Reserve a table in ITC Narmada, Ahmedabad for 2 people at 8 PM on September 22 under ₹3,000"
        }

        response = client.post("/api/tasks", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert data["task_type"] == "RESERVE_RESTAURANT"
        assert data["task_constraint_result"] == "PASS"
        assert data["policy_result"] == "REJECTED"
        assert data["payment_status"] == "NOT_ATTEMPTED"
        assert data["task_status"] == "REJECTED"
        assert data["transaction_id"] is None
        assert "REJECTED by Policy Engine" in data["final_message"]

    def test_5_malformed_task_empty_message(self, client: TestClient):
        """
        Empty or whitespace message should return 400 Bad Request.
        """
        response = client.post("/api/tasks", json={"message": "   "})
        assert response.status_code == 400
        assert "cannot be empty" in response.json()["detail"].lower()

    def test_6_unsupported_task_no_options_found(self, client: TestClient, db_session: Session, test_seed_data):
        """
        When user specifies an impossible budget or unserved route:
        Expected:
          task_constraint_result: "FAIL"
          policy_result: "NOT_EVALUATED"
          payment_status: "NOT_ATTEMPTED"
          task_status: "TOOL_FAILED"
        """
        payload = {
            "message": "Book a flight from Ahmedabad to Mumbai under ₹500 on September 5"
        }

        response = client.post("/api/tasks", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert data["task_type"] == "BOOK_FLIGHT"
        assert data["task_constraint_result"] == "FAIL"
        assert data["policy_result"] == "NOT_EVALUATED"
        assert data["payment_status"] == "NOT_ATTEMPTED"
        assert data["task_status"] == "TOOL_FAILED"
        assert data["transaction_id"] is None

    def test_7_direct_payment_backward_compatibility(self, client: TestClient, db_session: Session, test_seed_data):
        """
        Direct payment via POST /api/tasks:
        "Pay Netflix ₹2,000"
        Expected:
          task_type: "DIRECT_PAYMENT"
          task_constraint_result: "NOT_APPLICABLE"
          policy_result: "APPROVED"
          payment_status: "SUCCESS"
          task_status: "COMPLETED"
        """
        payload = {
            "message": "Pay Netflix ₹2,000"
        }

        response = client.post("/api/tasks", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert data["task_type"] == "DIRECT_PAYMENT"
        assert data["task_constraint_result"] == "NOT_APPLICABLE"
        assert data["policy_result"] == "APPROVED"
        assert data["payment_status"] == "SUCCESS"
        assert data["task_status"] == "COMPLETED"
        assert data["amount"] == 2000.0
        assert data["merchant_name"] == "Netflix"
        assert data["transaction_id"] is not None
