import uuid
import pytest
from sqlalchemy import select
from app.agents.orchestrator import AgentOrchestrator
from app.agents.llm_provider import LLMProvider, MockLLMProvider
from app.schemas.agent_types import TransactionIntent, AgentResponse
from app.services.payment_adapter import MockPaymentAdapter
from app.models.transaction import Transaction
from app.models.audit_log import AuditLog
from app.models.policy import Policy


class CustomMockLLM(LLMProvider):
    """Configurable Mock LLM for precise testing of mock responses."""
    def __init__(self, intent: TransactionIntent):
        self._intent = intent

    def parse_payment_intent(self, message: str) -> TransactionIntent:
        return self._intent


class TestAgentLLMOrchestration:
    def test_1_natural_language_converted_to_transaction_intent(self):
        """1. Verify natural language prompt is converted into correct TransactionIntent."""
        provider = MockLLMProvider()

        # Electricity bill
        intent1 = provider.parse_payment_intent("Pay my Torrent Power electricity bill of ₹1,240")
        assert intent1.merchant == "Torrent Power"
        assert intent1.amount == 1240.0
        assert intent1.currency == "INR"
        assert intent1.category == "utilities"

        # Subscription
        intent2 = provider.parse_payment_intent("Pay my Netflix subscription of 499")
        assert intent2.merchant == "Netflix"
        assert intent2.amount == 499.0
        assert intent2.category == "subscriptions"

        # Travel booking
        intent3 = provider.parse_payment_intent("Book flight on MakeMyTrip for 3500")
        assert intent3.merchant == "MakeMyTrip"
        assert intent3.amount == 3500.0
        assert intent3.category == "travel"

    def test_2_allowed_payment_flow(self, db_session, test_seed_data):
        """2. Allowed payment: mocked LLM -> TransactionIntent -> Policy Engine ALLOW -> PaymentService called."""
        orchestrator = AgentOrchestrator(
            adapter=MockPaymentAdapter(default_failure=False),
            llm_provider=MockLLMProvider(),
        )
        response = orchestrator.process_with_llm(
            db_session,
            message="Pay my Torrent Power electricity bill of 1240",
        )

        assert isinstance(response, AgentResponse)
        assert response.success is True
        assert response.decision == "ALLOWED"
        assert response.decision_code == "APPROVED"
        assert response.payment_status == "SUCCESS"
        assert response.payment_id is not None
        assert response.amount == 1240.0
        assert response.merchant_name == "Torrent Power"

        # Verify transaction persisted in DB
        tx = db_session.get(Transaction, uuid.UUID(response.payment_id))
        assert tx is not None
        assert tx.status == "SUCCESS"
        assert tx.amount == 1240.0

    def test_3_denied_payment_flow_policy_limit_exceeded(self, db_session, test_seed_data):
        """3. Denied payment: mocked LLM -> TransactionIntent -> Policy Engine DENY -> PaymentService NOT called."""
        orchestrator = AgentOrchestrator(
            adapter=MockPaymentAdapter(),
            llm_provider=MockLLMProvider(),
        )
        response = orchestrator.process_with_llm(
            db_session,
            message="Book a holiday for 6000 on MakeMyTrip",
        )

        assert isinstance(response, AgentResponse)
        assert response.success is False
        assert response.decision == "DENIED"
        assert response.payment_id is None
        assert response.payment_status == "REJECTED"
        assert response.decision_code in ["TX_LIMIT_EXCEEDED", "MULTIPLE_POLICY_VIOLATIONS"]

        # Verify no transaction was created for 6000
        tx = db_session.execute(
            select(Transaction).where(Transaction.amount == 6000.0)
        ).scalar_one_or_none()
        assert tx is None

    def test_4_llm_cannot_bypass_policy_engine(self, db_session, test_seed_data):
        """4. Verify the LLM cannot bypass the policy engine (e.g. LLM generates intent for blocked category)."""
        # Even if a rogue or hallucinating LLM generates an intent for a blocked category
        rogue_intent = TransactionIntent(
            merchant="Crypto Casino",
            amount=500.0,
            currency="INR",
            category="gambling",
            description="High stakes gamble",
        )
        orchestrator = AgentOrchestrator(
            adapter=MockPaymentAdapter(),
            llm_provider=CustomMockLLM(rogue_intent),
        )

        response = orchestrator.process_with_llm(
            db_session,
            message="Invest 500 in crypto casino game",
        )

        # Policy engine MUST reject regardless of what LLM requested
        assert response.success is False
        assert response.decision == "DENIED"
        assert response.payment_id is None
        assert response.decision_code == "CATEGORY_BLOCKED"

    def test_5_agent_response_explains_rejection(self, db_session, test_seed_data):
        """5. Verify the AgentResponse correctly explains a policy rejection."""
        orchestrator = AgentOrchestrator(
            adapter=MockPaymentAdapter(),
            llm_provider=MockLLMProvider(),
        )
        response = orchestrator.process_with_llm(
            db_session,
            message="Book luxury flights on MakeMyTrip for 8000",
        )

        assert response.success is False
        assert response.decision == "DENIED"
        assert "DENIED" in response.message
        assert "exceeds" in response.message.lower() or "limit" in response.message.lower()
        assert response.explanation != ""
        assert len(response.rules_checked) > 0

    def test_6_payment_result_reflected_in_agent_response(self, db_session, test_seed_data):
        """6. Verify payment result (e.g. gateway failure) is reflected in AgentResponse."""
        failing_adapter = MockPaymentAdapter(default_failure=True, failure_reason="Bank network timeout")
        orchestrator = AgentOrchestrator(
            adapter=failing_adapter,
            llm_provider=MockLLMProvider(),
        )

        response = orchestrator.process_with_llm(
            db_session,
            message="Pay my Netflix subscription of 499",
            force_failure=True,
        )

        assert response.success is False
        assert response.decision == "ALLOWED"  # Policy allowed it
        assert response.payment_status == "FAILED"  # But gateway failed
        assert response.payment_id is not None
        assert "Bank network timeout" in response.message or "failed" in response.message.lower()

    def test_7_agent_and_payment_actions_recorded_in_audit_log(self, db_session, test_seed_data):
        """7. Verify important agent/payment actions are recorded in AuditLog."""
        orchestrator = AgentOrchestrator(
            adapter=MockPaymentAdapter(default_failure=False),
            llm_provider=MockLLMProvider(),
        )
        response = orchestrator.process_with_llm(
            db_session,
            message="Pay my Torrent Power electricity bill of 1240",
        )
        assert response.success is True

        # Check audit log entries
        logs = db_session.execute(
            select(AuditLog).order_by(AuditLog.created_at.asc())
        ).scalars().all()

        event_types = [l.event_type for l in logs]
        assert "AGENT_REQUEST" in event_types
        assert "INTENT_CREATED" in event_types
        assert "POLICY_EVALUATION" in event_types
        assert "PAYMENT_ATTEMPT" in event_types
        assert "PAYMENT_RESULT" in event_types
