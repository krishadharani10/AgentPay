"""
Complete End-to-End Test Suite for Deterministic Autonomous Flight Booking.

Covers all core scenarios required for AgentPay:
  Scenario A: Flight under budget + AgentPay policy allows it → PASS → SUCCESS → CONFIRMED
  Scenario B: Flight meets user's budget but violates AgentPay policy → POLICY REJECT → NO PAYMENT → NO BOOKING
  Scenario C: No flight satisfies user constraints → TASK REJECTED before payment
  Scenario D: Full audit trail lifecycle recorded in existing AuditLog
"""
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent import Agent
from app.models.policy import Policy
from app.models.wallet import Wallet
from app.models.transaction import Transaction
from app.models.audit_log import AuditLog
from app.schemas.task_types import TaskType, TaskIntent, TaskResponse
from app.agents.task_orchestrator import TaskOrchestrator
from app.services.payment_adapter import MockPaymentProvider, MockPaymentMode


class TestFlightBookingCompleteDemo:

    def test_scenario_a_flight_under_budget_and_policy_allows_it(
        self, db_session: Session, test_seed_data
    ):
        """
        SCENARIO A:
        - User request: Book flight BOM → DEL on 2026-09-11 under ₹5,000
        - Policy limit: per_transaction_limit = ₹5,000, daily_spending_limit = ₹10,000
        - Flight tool finds AP701 (₹3,800)
        - Policy Engine: ALLOWED / APPROVED
        - Payment rail: SUCCESS
        - Booking: CONFIRMED / COMPLETED
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

        response: TaskResponse = orchestrator.execute_task(db_session, task_intent=intent)

        # 1. Verification of flight selection
        assert response.success is True
        assert response.task_status == "COMPLETED"
        assert response.decision == "ALLOWED"
        assert response.decision_code == "APPROVED"
        assert response.payment_status == "SUCCESS"
        assert response.amount == 3800.0
        assert response.merchant_name == "AirDemo"
        assert response.selected_option is not None
        assert response.selected_option["flight_number"] == "AP701"
        assert response.selected_option["origin"] == "BOM"
        assert response.selected_option["destination"] == "DEL"
        assert "Flight successfully booked: AirDemo AP701" in response.message

        # 2. Verification of authoritative transaction record in database
        assert response.payment_id is not None
        tx = db_session.get(Transaction, uuid.UUID(response.payment_id))
        assert tx is not None
        assert tx.status == "SUCCESS"
        assert tx.amount == 3800.0
        assert tx.category == "travel"

        # 3. Verification of audit log events for full lifecycle
        agent = db_session.execute(select(Agent).limit(1)).scalar_one()
        audit_events = db_session.execute(
            select(AuditLog.event_type)
            .where(AuditLog.agent_id == agent.id)
            .order_by(AuditLog.created_at.desc())
        ).scalars().all()

        assert "TASK_RECEIVED" in audit_events
        assert "SEARCH_PERFORMED" in audit_events
        assert "OPTIONS_FOUND" in audit_events
        assert "OPTION_SELECTED" in audit_events
        assert "PAYMENT_INTENT_CREATED" in audit_events
        assert "POLICY_CHECK" in audit_events
        assert "TASK_COMPLETED" in audit_events

    def test_scenario_b_user_budget_ok_but_agentpay_policy_rejects(
        self, db_session: Session, test_seed_data
    ):
        """
        SCENARIO B:
        - User request: Book flight AMD → BOM on 2026-09-05 under ₹10,000
        - User task constraint: max_budget = ₹10,000
        - Flight tool finds AP101 at ₹7,450 (which fits user budget ₹10,000!)
        - BUT AgentPay Policy Engine limit is per_transaction_limit = ₹5,000
        - Policy Engine: STRICTLY REJECTED (TX_LIMIT_EXCEEDED)
        - NO payment is executed
        - NO booking is confirmed
        - Result: REJECTED_POLICY
        """
        orchestrator = TaskOrchestrator(adapter=MockPaymentProvider(mode=MockPaymentMode.SUCCESS))

        # Ensure policy has per_transaction_limit = 5000
        policy = db_session.execute(select(Policy).limit(1)).scalar_one()
        policy.max_transaction_amount = 5000.0
        wallet = db_session.execute(select(Wallet).limit(1)).scalar_one()
        wallet.per_transaction_limit = 5000.0
        db_session.flush()

        intent = TaskIntent(
            task_type=TaskType.BOOK_FLIGHT,
            user_message="Book a flight from Ahmedabad to Mumbai under ₹10,000 on September 5",
            origin="Ahmedabad",
            destination="Mumbai",
            date="2026-09-05",
            max_budget=10000.0,
        )

        response: TaskResponse = orchestrator.execute_task(db_session, task_intent=intent)

        # 1. Must be rejected
        assert response.success is False
        assert response.task_status == "REJECTED_POLICY"
        assert response.decision == "DENIED"
        assert response.decision_code == "TX_LIMIT_EXCEEDED"
        assert response.payment_status == "REJECTED"
        assert response.payment_id is None

        # 2. Flight tool selected the cheapest option under user budget (₹7,450)
        assert response.selected_option is not None
        assert response.selected_option["flight_number"] == "AP101"
        assert response.selected_option["price"] == 7450.0

        # 3. Policy failure explanation is clear
        assert "REJECTED by Policy Engine" in response.message
        assert any(
            rule["rule"] == "TRANSACTION_LIMIT" and not rule["passed"]
            for rule in response.rules_checked
        )

        # 4. Invariant check: NO SUCCESS transaction created in database for this amount
        txs = db_session.execute(
            select(Transaction).where(Transaction.amount == 7450.0)
        ).scalars().all()
        # Any transaction created must NOT be SUCCESS
        for tx in txs:
            assert tx.status != "SUCCESS"

    def test_scenario_c_no_flight_satisfies_user_task_constraints(
        self, db_session: Session, test_seed_data
    ):
        """
        SCENARIO C:
        - User request: Book flight AMD → BOM on 2026-09-05 under ₹5,000
        - Flights exist (₹7,450, ₹8,250, ₹11,500), but NONE under ₹5,000
        - Tool fails cleanly before payment
        - Policy Engine is NEVER invoked
        - Payment rail is NEVER invoked
        - Result: TOOL_FAILED
        """
        orchestrator = TaskOrchestrator(adapter=MockPaymentProvider(mode=MockPaymentMode.SUCCESS))

        intent = TaskIntent(
            task_type=TaskType.BOOK_FLIGHT,
            user_message="Book a flight from Ahmedabad to Mumbai under ₹5,000 on September 5",
            origin="Ahmedabad",
            destination="Mumbai",
            date="2026-09-05",
            max_budget=5000.0,
        )

        response: TaskResponse = orchestrator.execute_task(db_session, task_intent=intent)

        assert response.success is False
        assert response.task_status == "TOOL_FAILED"
        assert response.payment_id is None
        assert response.selected_option is None
        assert "none within budget ₹5,000.00" in response.message

    def test_scenario_c_unknown_flight_route(
        self, db_session: Session, test_seed_data
    ):
        """
        SCENARIO C2:
        - User request for unsupported route: CCU → GOI
        - Result: TOOL_FAILED (no flights found for route)
        """
        orchestrator = TaskOrchestrator(adapter=MockPaymentProvider(mode=MockPaymentMode.SUCCESS))

        intent = TaskIntent(
            task_type=TaskType.BOOK_FLIGHT,
            user_message="Book a flight from Kolkata to Goa on September 5",
            origin="Kolkata",
            destination="Goa",
            date="2026-09-05",
            max_budget=10000.0,
        )

        response: TaskResponse = orchestrator.execute_task(db_session, task_intent=intent)

        assert response.success is False
        assert response.task_status == "TOOL_FAILED"
        assert "No flights found" in response.message

    def test_scenario_natural_language_pipeline(
        self, db_session: Session, test_seed_data
    ):
        """
        End-to-end natural language string processing for flight booking.
        Verifies:
        1. Natural language string → MockLLMProvider.parse_task_intent()
        2. TaskIntent → TaskOrchestrator.execute_task()
        3. FlightSearch tool → Selection → Policy Engine → Payment
        """
        # Expand policy limit so ₹7,450 passes
        policy = db_session.execute(select(Policy).limit(1)).scalar_one()
        policy.max_transaction_amount = 15000.0
        wallet = db_session.execute(select(Wallet).limit(1)).scalar_one()
        wallet.per_transaction_limit = 15000.0
        wallet.daily_spending_limit = 25000.0
        db_session.flush()

        orchestrator = TaskOrchestrator(adapter=MockPaymentProvider(mode=MockPaymentMode.SUCCESS))

        prompt = "Book a flight from Ahmedabad to Mumbai under ₹10,000 on September 22"
        response = orchestrator.process_natural_language(db_session, message=prompt)

        assert response.success is True
        assert response.task_status == "COMPLETED"
        assert response.amount == 7450.0  # AP101 selected
        assert response.selected_option["flight_number"] == "AP101"
        assert response.selected_option["date"] == "2026-09-22"
        assert response.payment_status == "SUCCESS"
