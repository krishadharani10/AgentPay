"""
Complete End-to-End Test Suite for Deterministic Autonomous Restaurant Reservation.

Covers all core scenarios required for AgentPay:
  Scenario A: Restaurant reservation success → PASS → SUCCESS → CONFIRMED
  Scenario B: Restaurant rejected by AgentPay policy → POLICY REJECT → NO PAYMENT → NO RESERVATION
  Scenario C: No suitable restaurant → TASK REJECTED before payment
  Scenario D: Full audit trail lifecycle recorded in existing AuditLog with RESERVATION_CONFIRMED
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


class TestRestaurantReservationCompleteDemo:

    def test_scenario_a_restaurant_reservation_success(
        self, db_session: Session, test_seed_data
    ):
        """
        SCENARIO A:
        - User request: Reserve a table in ITC Narmada, Ahmedabad for 2 people at 8 PM on September 22 under ₹3,000
        - Restaurant tool finds ITC Narmada (Deposit: ₹1,000)
        - Deposit constraint: ₹1,000 <= ₹3,000 (Passes user budget)
        - Policy Engine: ALLOWED / APPROVED (dining category enabled, ₹1,000 <= limit)
        - Payment rail: SUCCESS
        - Reservation: CONFIRMED
        """
        orchestrator = TaskOrchestrator(adapter=MockPaymentProvider(mode=MockPaymentMode.SUCCESS))

        intent = TaskIntent(
            task_type=TaskType.RESERVE_RESTAURANT,
            user_message="Reserve a table in ITC Narmada, Ahmedabad for 2 people at 8 PM on September 22 under ₹3,000",
            city="Ahmedabad",
            merchant="ITC Narmada",
            party_size=2,
            date="2026-09-22",
            time="8:00 PM",
            max_budget=3000.0,
        )

        response: TaskResponse = orchestrator.execute_task(db_session, task_intent=intent)

        # 1. Verification of task response
        assert response.success is True
        assert response.task_status == "COMPLETED"
        assert response.decision == "ALLOWED"
        assert response.decision_code == "APPROVED"
        assert response.payment_status == "SUCCESS"
        assert response.amount == 1000.0
        assert response.merchant_name == "ITC Narmada"
        assert response.selected_option is not None
        assert response.selected_option["restaurant_name"] == "ITC Narmada"
        assert response.selected_option["city"] == "Ahmedabad"
        assert response.selected_option["deposit_amount"] == 1000.0
        assert "Reservation confirmed at ITC Narmada (Ahmedabad)" in response.message
        assert "Deposit of ₹1,000.00 successfully captured" in response.message

        # 2. Verification of transaction in database
        assert response.payment_id is not None
        tx = db_session.get(Transaction, uuid.UUID(response.payment_id))
        assert tx is not None
        assert tx.status == "SUCCESS"
        assert tx.merchant_name == "ITC Narmada"
        assert tx.amount == 1000.0
        assert tx.category == "dining"
        assert "complies with all wallet and policy rules" in tx.decision_reason.lower()

        # 3. Verification of audit log events
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
        assert "RESERVATION_CONFIRMED" in audit_events

    def test_scenario_b_policy_rejects_restaurant_deposit(
        self, db_session: Session, test_seed_data
    ):
        """
        SCENARIO B:
        - Task is valid: ITC Narmada deposit is ₹1,000 (within user's ₹3,000 budget)
        - BUT Policy Engine has blocked "dining" category or per_transaction_limit < ₹1,000
        - Policy Engine: DENIED / REJECTED
        - NO payment executed
        - NO reservation confirmed
        """
        orchestrator = TaskOrchestrator(adapter=MockPaymentProvider(mode=MockPaymentMode.SUCCESS))

        # Restrict policy: block dining category
        policy = db_session.execute(select(Policy).limit(1)).scalar_one()
        policy.blocked_categories = ["dining", "gambling", "crypto"]
        if "dining" in policy.allowed_categories:
            policy.allowed_categories.remove("dining")
        db_session.flush()

        intent = TaskIntent(
            task_type=TaskType.RESERVE_RESTAURANT,
            user_message="Reserve a table in ITC Narmada, Ahmedabad for 2 people at 8 PM on September 22 under ₹3,000",
            city="Ahmedabad",
            merchant="ITC Narmada",
            party_size=2,
            date="2026-09-22",
            time="8:00 PM",
            max_budget=3000.0,
        )

        response: TaskResponse = orchestrator.execute_task(db_session, task_intent=intent)

        # Must be rejected by policy engine
        assert response.success is False
        assert response.task_status == "REJECTED_POLICY"
        assert response.decision == "DENIED"
        assert response.payment_status == "REJECTED"
        assert response.payment_id is None
        assert "REJECTED by Policy Engine" in response.message

        # Verify no successful payment in DB
        txs = db_session.execute(
            select(Transaction).where(Transaction.amount == 1000.0, Transaction.status == "SUCCESS")
        ).scalars().all()
        assert len(txs) == 0

    def test_scenario_c_no_suitable_restaurant_under_budget(
        self, db_session: Session, test_seed_data
    ):
        """
        SCENARIO C1:
        - User requests table in Ahmedabad with unrealistic deposit budget ₹200
        - Tool fails before payment
        - Policy Engine is NEVER called
        - Payment rail is NEVER called
        """
        orchestrator = TaskOrchestrator(adapter=MockPaymentProvider(mode=MockPaymentMode.SUCCESS))

        intent = TaskIntent(
            task_type=TaskType.RESERVE_RESTAURANT,
            user_message="Reserve a table in Ahmedabad for 2 people under ₹200 on September 22",
            city="Ahmedabad",
            party_size=2,
            date="2026-09-22",
            max_budget=200.0,
        )

        response: TaskResponse = orchestrator.execute_task(db_session, task_intent=intent)

        assert response.success is False
        assert response.task_status == "TOOL_FAILED"
        assert response.payment_id is None
        assert "none within deposit budget" in response.message

    def test_scenario_c_unsupported_city(
        self, db_session: Session, test_seed_data
    ):
        """
        SCENARIO C2:
        - User requests table in unsupported city: Surat
        - Result: TOOL_FAILED
        """
        orchestrator = TaskOrchestrator(adapter=MockPaymentProvider(mode=MockPaymentMode.SUCCESS))

        intent = TaskIntent(
            task_type=TaskType.RESERVE_RESTAURANT,
            user_message="Reserve a table in Surat for 2 people on September 22",
            city="Surat",
            party_size=2,
            date="2026-09-22",
            max_budget=2000.0,
        )

        response: TaskResponse = orchestrator.execute_task(db_session, task_intent=intent)

        assert response.success is False
        assert response.task_status == "TOOL_FAILED"
        assert "No restaurant reservations found" in response.message

    def test_scenario_natural_language_pipeline_itc_narmada(
        self, db_session: Session, test_seed_data
    ):
        """
        SCENARIO D:
        Natural language string:
        "Reserve a table in ITC Narmada, Ahmedabad for 2 people at 8 PM on September 22 under ₹3,000."
        End-to-end processing: NL -> TaskIntent -> Search -> Select -> Policy -> Payment -> Reservation Confirmed.
        """
        orchestrator = TaskOrchestrator(adapter=MockPaymentProvider(mode=MockPaymentMode.SUCCESS))

        prompt = "Reserve a table in ITC Narmada, Ahmedabad for 2 people at 8 PM on September 22 under ₹3,000."
        response = orchestrator.process_natural_language(db_session, message=prompt)

        assert response.success is True
        assert response.task_status == "COMPLETED"
        assert response.amount == 1000.0
        assert response.selected_option["restaurant_name"] == "ITC Narmada"
        assert response.selected_option["city"] == "Ahmedabad"
        assert response.selected_option["date"] == "2026-09-22"
        assert response.payment_status == "SUCCESS"
        assert "Reservation confirmed" in response.message
