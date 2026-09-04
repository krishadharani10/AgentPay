"""
Integration and Unit Tests for Autonomous Task Understanding & Existing AgentPay System.

Tests cover:
  1. Direct payment classification
  2. Flight classification
  3. Restaurant classification
  4. Missing required flight information handling
  5. Missing required restaurant information handling
  6. Invalid budget handling (negative budget validation)
  7. Correct TaskIntent creation & validation
  8. Existing direct-payment backwards compatibility
"""
import uuid
import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.schemas.task_types import TaskType, TaskIntent, TaskResponse
from app.agents.llm_provider import MockLLMProvider
from app.agents.task_orchestrator import TaskOrchestrator
from app.agents.orchestrator import AgentOrchestrator
from app.services.payment_adapter import MockPaymentProvider, MockPaymentMode


class TestAgentTaskUnderstandingAndIntegration:

    @pytest.fixture
    def llm(self) -> MockLLMProvider:
        return MockLLMProvider()

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Direct Payment Classification
    # ─────────────────────────────────────────────────────────────────────────

    def test_1_direct_payment_classification(self, llm: MockLLMProvider):
        """
        Verify natural language direct payment requests are correctly classified
        as DIRECT_PAYMENT with extracted merchant, budget, and category.
        """
        # Test Netflix direct payment
        intent1 = llm.parse_task_intent("Pay Netflix ₹2,000")
        assert intent1.task_type == TaskType.DIRECT_PAYMENT
        assert intent1.merchant == "Netflix"
        assert intent1.budget == 2000.0
        assert intent1.category == "subscriptions"

        # Test Torrent Power electricity bill payment
        intent2 = llm.parse_task_intent("Pay ₹1,240 to Torrent Power for electricity bill")
        assert intent2.task_type == TaskType.DIRECT_PAYMENT
        assert intent2.merchant == "Torrent Power"
        assert intent2.budget == 1240.0
        assert intent2.category == "utilities"

        # Test Amazon shopping payment
        intent3 = llm.parse_task_intent("Pay ₹899 to Amazon for supplies")
        assert intent3.task_type == TaskType.DIRECT_PAYMENT
        assert intent3.merchant == "Amazon"
        assert intent3.budget == 899.0
        assert intent3.category == "shopping"

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Flight Classification & Extraction
    # ─────────────────────────────────────────────────────────────────────────

    def test_2_flight_classification_and_extraction(self, llm: MockLLMProvider):
        """
        Verify natural language flight requests are classified as BOOK_FLIGHT
        with origin, destination, date, and max_budget properly extracted.
        """
        prompt = "Book a flight from Ahmedabad to Mumbai under ₹10,000 on September 22"
        intent = llm.parse_task_intent(prompt)

        assert intent.task_type == TaskType.BOOK_FLIGHT
        assert intent.origin == "Ahmedabad"
        assert intent.destination == "Mumbai"
        assert intent.date == "2026-09-22"
        assert intent.max_budget == 10000.0
        assert intent.category == "travel"

        # Verify task requirements pass validation
        is_valid, missing = intent.validate_task_requirements()
        assert is_valid is True
        assert len(missing) == 0

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Restaurant Classification & Extraction
    # ─────────────────────────────────────────────────────────────────────────

    def test_3_restaurant_classification_and_extraction(self, llm: MockLLMProvider):
        """
        Verify natural language restaurant requests are classified as RESERVE_RESTAURANT
        with city, venue, party_size, time, date, and max_budget properly extracted.
        """
        prompt = "Reserve a table in ITC Narmada, Ahmedabad for 2 people at 8 PM on September 22 under ₹3,000."
        intent = llm.parse_task_intent(prompt)

        assert intent.task_type == TaskType.RESERVE_RESTAURANT
        assert intent.city == "Ahmedabad"
        assert intent.merchant == "ITC Narmada"
        assert intent.party_size == 2
        assert intent.time == "8 PM"
        assert intent.date == "2026-09-22"
        assert intent.max_budget == 3000.0
        assert intent.category == "dining"

        # Verify task requirements pass validation
        is_valid, missing = intent.validate_task_requirements()
        assert is_valid is True
        assert len(missing) == 0

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Missing Required Flight Information Handling
    # ─────────────────────────────────────────────────────────────────────────

    def test_4_missing_required_flight_information(self, db_session: Session, test_seed_data):
        """
        When flight intent is missing destination or budget:
        Validation fails before reaching Policy Engine or PaymentService.
        """
        orchestrator = TaskOrchestrator(adapter=MockPaymentProvider(mode=MockPaymentMode.SUCCESS))

        # Incomplete flight intent: missing destination and budget
        incomplete_intent = TaskIntent(
            task_type=TaskType.BOOK_FLIGHT,
            user_message="Book a flight from Ahmedabad",
            origin="Ahmedabad",
            destination=None,
            date="2026-09-22",
            max_budget=None,
        )

        is_valid, missing = incomplete_intent.validate_task_requirements()
        assert is_valid is False
        assert "destination" in missing
        assert "max_budget" in missing

        response = orchestrator.execute_task(db_session, task_intent=incomplete_intent)
        assert response.success is False
        assert response.task_status == "INVALID_INTENT"
        assert "Missing required information for BOOK_FLIGHT" in response.message
        assert response.payment_id is None

    # ─────────────────────────────────────────────────────────────────────────
    # 5. Missing Required Restaurant Information Handling
    # ─────────────────────────────────────────────────────────────────────────

    def test_5_missing_required_restaurant_information(self, db_session: Session, test_seed_data):
        """
        When restaurant reservation intent is missing city:
        Validation fails before reaching Policy Engine or PaymentService.
        """
        orchestrator = TaskOrchestrator(adapter=MockPaymentProvider(mode=MockPaymentMode.SUCCESS))

        # Incomplete restaurant intent: missing city and budget
        incomplete_intent = TaskIntent(
            task_type=TaskType.RESERVE_RESTAURANT,
            user_message="Reserve a table for 2 people on September 22",
            city=None,
            date="2026-09-22",
            time="8:00 PM",
            party_size=2,
            max_budget=None,
        )

        is_valid, missing = incomplete_intent.validate_task_requirements()
        assert is_valid is False
        assert "city" in missing
        assert "max_budget" in missing

        response = orchestrator.execute_task(db_session, task_intent=incomplete_intent)
        assert response.success is False
        assert response.task_status == "INVALID_INTENT"
        assert "Missing required information for RESERVE_RESTAURANT" in response.message
        assert response.payment_id is None

    # ─────────────────────────────────────────────────────────────────────────
    # 6. Invalid Budget Handling
    # ─────────────────────────────────────────────────────────────────────────

    def test_6_invalid_negative_budget(self):
        """
        Pydantic validation should reject negative budget numbers with a clear error.
        """
        with pytest.raises(ValidationError) as exc_info:
            TaskIntent(
                task_type=TaskType.BOOK_FLIGHT,
                user_message="Book a flight",
                origin="AMD",
                destination="BOM",
                date="2026-09-22",
                max_budget=-500.0,
            )
        assert "Budget cannot be negative" in str(exc_info.value)

    def test_6_invalid_party_size(self):
        """
        Pydantic validation should reject non-positive party sizes.
        """
        with pytest.raises(ValidationError) as exc_info:
            TaskIntent(
                task_type=TaskType.RESERVE_RESTAURANT,
                user_message="Reserve table",
                city="Ahmedabad",
                date="2026-09-22",
                time="8:00 PM",
                party_size=0,
                max_budget=2000.0,
            )
        assert "Party size must be greater than zero" in str(exc_info.value)

    # ─────────────────────────────────────────────────────────────────────────
    # 7. Correct TaskIntent Creation & Serialization
    # ─────────────────────────────────────────────────────────────────────────

    def test_7_correct_task_intent_creation_and_serialization(self):
        """
        Verify structured TaskIntent serializes to JSON dictionary cleanly.
        """
        intent = TaskIntent(
            task_type=TaskType.BOOK_FLIGHT,
            user_message="Book a flight from Ahmedabad to Mumbai under ₹10,000 on September 22",
            origin="Ahmedabad",
            destination="Mumbai",
            date="2026-09-22",
            max_budget=10000.0,
            category="travel",
            merchant="AirDemo",
        )

        d = intent.model_dump(mode="json")
        assert d["task_type"] == "BOOK_FLIGHT"
        assert d["origin"] == "Ahmedabad"
        assert d["destination"] == "Mumbai"
        assert d["date"] == "2026-09-22"
        assert d["max_budget"] == 10000.0
        assert d["category"] == "travel"

    # ─────────────────────────────────────────────────────────────────────────
    # 8. Backward Compatibility for Existing Direct Payments
    # ─────────────────────────────────────────────────────────────────────────

    def test_8_existing_direct_payment_backward_compatibility(
        self, db_session: Session, test_seed_data
    ):
        """
        Verify that existing direct payments continue working unchanged through AgentOrchestrator.
        """
        orchestrator = AgentOrchestrator(adapter=MockPaymentProvider(mode=MockPaymentMode.SUCCESS))

        # Direct payment for Torrent Power bill
        result = orchestrator.process_request(
            db_session,
            message="Pay ₹1,240 to Torrent Power for electricity",
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
        )

        assert result["success"] is True
        assert result["decision"] == "ALLOWED"
        assert result["decision_code"] == "APPROVED"
        assert result["amount"] == 1240.0
        assert result["merchant_name"] == "Torrent Power"
        assert result["payment_id"] is not None

        # Direct payment for Amazon
        result_amazon = orchestrator.process_request(
            db_session,
            message="Pay ₹899 to Amazon for office supplies",
            merchant_name="Amazon",
            amount=899.0,
            category="shopping",
        )

        assert result_amazon["success"] is True
        assert result_amazon["decision"] == "ALLOWED"
        assert result_amazon["amount"] == 899.0
        assert result_amazon["merchant_name"] == "Amazon"
