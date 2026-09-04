"""
Integration and unit tests for TaskOrchestrator and Autonomous Commerce Demos.
"""
import uuid
import pytest
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.models.audit_log import AuditLog
from app.schemas.task_types import TaskType, TaskIntent, TaskResponse
from app.agents.task_orchestrator import TaskOrchestrator
from app.services.payment_adapter import MockPaymentProvider, MockPaymentMode


class TestTaskOrchestrator:

    def test_1_book_flight_end_to_end_success(self, db_session: Session, test_seed_data):
        """
        User requests flight booking → TaskOrchestrator selects flight → converts to TransactionIntent
        → Policy Engine authorizes → PaymentService executes → returns TaskResponse(COMPLETED).
        """
        orchestrator = TaskOrchestrator(adapter=MockPaymentProvider(mode=MockPaymentMode.SUCCESS))

        intent = TaskIntent(
            task_type=TaskType.BOOK_FLIGHT,
            user_message="Book a flight from Mumbai to Delhi under ₹5,000",
            origin="Mumbai",
            destination="Delhi",
            max_budget=5000.0,
            date="2026-09-11",
        )

        response: TaskResponse = orchestrator.execute_task(db_session, task_intent=intent)

        assert response.success is True
        assert response.task_status == "COMPLETED"
        assert response.decision == "ALLOWED"
        assert response.decision_code == "APPROVED"
        assert response.amount == 3800.0  # AP701 ₹3,800
        assert response.merchant_name == "AirDemo"
        assert response.payment_id is not None
        assert response.selected_option is not None
        assert response.selected_option["airline"] == "AirDemo"
        assert response.selected_option["flight_number"] == "AP701"
        assert response.selected_option["price"] == 3800.0
        assert response.transaction_intent is not None
        assert response.transaction_intent.category == "travel"

        # Verify transaction in database
        tx = db_session.get(Transaction, uuid.UUID(response.payment_id))
        assert tx is not None
        assert tx.status == "SUCCESS"
        assert tx.amount == 3800.0
        assert tx.category == "travel"

    def test_2_reserve_restaurant_end_to_end_success(self, db_session: Session, test_seed_data):
        """
        User requests table reservation → TaskOrchestrator selects restaurant → converts to TransactionIntent
        → Policy Engine authorizes → PaymentService executes → returns TaskResponse(COMPLETED).
        """
        orchestrator = TaskOrchestrator(adapter=MockPaymentProvider(mode=MockPaymentMode.SUCCESS))

        intent = TaskIntent(
            task_type=TaskType.RESERVE_RESTAURANT,
            user_message="Reserve a table for 2 at Trishna in Mumbai tonight",
            city="Mumbai",
            merchant="Trishna",
            party_size=2,
            max_budget=2500.0,
            date="2026-09-04",
            time="20:30",
        )

        response: TaskResponse = orchestrator.execute_task(db_session, task_intent=intent)

        assert response.success is True
        assert response.task_status == "COMPLETED"
        assert response.decision == "ALLOWED"
        assert response.decision_code == "APPROVED"
        assert response.amount == 1800.0  # Trishna table deposit
        assert response.payment_id is not None
        assert response.selected_option is not None
        assert response.selected_option["restaurant_name"] == "Trishna"
        assert response.transaction_intent is not None
        assert response.transaction_intent.category == "dining"

        # Verify transaction in database
        tx = db_session.get(Transaction, uuid.UUID(response.payment_id))
        assert tx is not None
        assert tx.status == "SUCCESS"
        assert tx.amount == 1800.0
        assert tx.category == "dining"

    def test_3_flight_policy_rejection_exceeds_tx_limit(self, db_session: Session, test_seed_data):
        """
        Flight that passes tool search (AP420 @ ₹11,500 <= user budget ₹15,000)
        but exceeds Policy Engine limit (max_transaction_amount=8000) is strictly REJECTED.
        """
        orchestrator = TaskOrchestrator(adapter=MockPaymentProvider(mode=MockPaymentMode.SUCCESS))

        intent = TaskIntent(
            task_type=TaskType.BOOK_FLIGHT,
            user_message="Book a flight from Ahmedabad to Mumbai under ₹15,000 on September 8",
            origin="AMD",
            destination="BOM",
            date="2026-09-08",
            max_budget=15000.0,
        )

        response: TaskResponse = orchestrator.execute_task(db_session, task_intent=intent)

        assert response.success is False
        assert response.task_status == "REJECTED_POLICY"
        assert response.decision == "DENIED"
        assert response.decision_code == "TX_LIMIT_EXCEEDED"
        assert response.payment_id is None
        assert response.amount == 11500.0

    def test_4_tool_failure_when_no_flight_in_budget(self, db_session: Session, test_seed_data):
        """
        When flight tool cannot find any option within unrealistic budget, returns TOOL_FAILED.
        Policy Engine and PaymentService are never called.
        """
        orchestrator = TaskOrchestrator(adapter=MockPaymentProvider(mode=MockPaymentMode.SUCCESS))

        intent = TaskIntent(
            task_type=TaskType.BOOK_FLIGHT,
            user_message="Book a flight from Mumbai to Delhi under ₹500",
            origin="BOM",
            destination="DEL",
            max_budget=500.0,
        )

        response: TaskResponse = orchestrator.execute_task(db_session, task_intent=intent)

        assert response.success is False
        assert response.task_status == "TOOL_FAILED"
        assert "No flights found" in response.message
        assert response.payment_id is None
        assert response.selected_option is None

    def test_5_direct_payment_preserved(self, db_session: Session, test_seed_data):
        """
        Direct payment tasks continue to execute cleanly through TaskOrchestrator.
        """
        orchestrator = TaskOrchestrator(adapter=MockPaymentProvider(mode=MockPaymentMode.SUCCESS))

        intent = TaskIntent(
            task_type=TaskType.DIRECT_PAYMENT,
            user_message="Pay ₹899 to Amazon for office supplies",
            merchant="Amazon",
            budget=899.0,
            category="shopping",
        )

        response: TaskResponse = orchestrator.execute_task(db_session, task_intent=intent)

        assert response.success is True
        assert response.task_status == "COMPLETED"
        assert response.decision == "ALLOWED"
        assert response.amount == 899.0
        assert response.merchant_name == "Amazon"

    def test_6_process_natural_language_flight_prompt(self, db_session: Session, test_seed_data):
        """
        process_natural_language parses raw user flight command and completes the booking.
        """
        orchestrator = TaskOrchestrator(adapter=MockPaymentProvider(mode=MockPaymentMode.SUCCESS))

        prompt = "Book a flight from Mumbai to Delhi under ₹5,000 on Friday"
        response = orchestrator.process_natural_language(db_session, message=prompt)

        assert response.success is True
        assert response.task_type == TaskType.BOOK_FLIGHT
        assert response.task_status == "COMPLETED"
        assert response.amount == 3800.0

    def test_7_process_natural_language_restaurant_prompt(self, db_session: Session, test_seed_data):
        """
        process_natural_language parses raw user restaurant command and reserves the table.
        """
        orchestrator = TaskOrchestrator(adapter=MockPaymentProvider(mode=MockPaymentMode.SUCCESS))

        prompt = "Reserve a table for 2 at Trishna in Mumbai tonight under ₹2,000"
        response = orchestrator.process_natural_language(db_session, message=prompt)

        assert response.success is True
        assert response.task_type == TaskType.RESERVE_RESTAURANT
        assert response.task_status == "COMPLETED"
        assert response.amount == 1800.0
