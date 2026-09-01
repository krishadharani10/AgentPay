"""
Day 3 Phase 1: Transaction State Machine Tests
Tests the formal TransactionStatus enum, transition matrix, and transition guard.
"""
import uuid
import pytest
from app.models.transaction import (
    Transaction,
    TransactionStatus,
    InvalidPaymentStateError,
    VALID_STATE_TRANSITIONS,
    validate_transition,
)


class TestTransactionStatusEnum:
    """Verify the TransactionStatus enum members and string values."""

    def test_all_expected_states_exist(self):
        expected = {"REQUESTED", "POLICY_CHECK", "APPROVED", "REJECTED", "PAYMENT_PENDING", "SUCCESS", "FAILED"}
        actual = {s.value for s in TransactionStatus}
        assert actual == expected

    def test_enum_is_str_subclass(self):
        """TransactionStatus values are usable as strings."""
        assert TransactionStatus.REQUESTED == "REQUESTED"
        assert isinstance(TransactionStatus.SUCCESS, str)


class TestValidTransitionMatrix:
    """Verify the static transition matrix is correctly defined."""

    def test_requested_can_only_go_to_policy_check(self):
        assert VALID_STATE_TRANSITIONS[TransactionStatus.REQUESTED] == {TransactionStatus.POLICY_CHECK}

    def test_policy_check_can_go_to_approved_or_rejected(self):
        assert VALID_STATE_TRANSITIONS[TransactionStatus.POLICY_CHECK] == {
            TransactionStatus.APPROVED, TransactionStatus.REJECTED,
        }

    def test_approved_can_only_go_to_payment_pending(self):
        assert VALID_STATE_TRANSITIONS[TransactionStatus.APPROVED] == {TransactionStatus.PAYMENT_PENDING}

    def test_payment_pending_can_go_to_success_or_failed(self):
        assert VALID_STATE_TRANSITIONS[TransactionStatus.PAYMENT_PENDING] == {
            TransactionStatus.SUCCESS, TransactionStatus.FAILED,
        }

    def test_success_is_terminal(self):
        assert VALID_STATE_TRANSITIONS[TransactionStatus.SUCCESS] == set()

    def test_rejected_is_terminal(self):
        assert VALID_STATE_TRANSITIONS[TransactionStatus.REJECTED] == set()

    def test_failed_is_terminal(self):
        assert VALID_STATE_TRANSITIONS[TransactionStatus.FAILED] == set()


class TestValidateTransitionFunction:
    """Test the standalone validate_transition guard function."""

    # ── Valid Transitions ──

    def test_requested_to_policy_check(self):
        validate_transition(TransactionStatus.REQUESTED, TransactionStatus.POLICY_CHECK)

    def test_policy_check_to_approved(self):
        validate_transition(TransactionStatus.POLICY_CHECK, TransactionStatus.APPROVED)

    def test_policy_check_to_rejected(self):
        validate_transition(TransactionStatus.POLICY_CHECK, TransactionStatus.REJECTED)

    def test_approved_to_payment_pending(self):
        validate_transition(TransactionStatus.APPROVED, TransactionStatus.PAYMENT_PENDING)

    def test_payment_pending_to_success(self):
        validate_transition(TransactionStatus.PAYMENT_PENDING, TransactionStatus.SUCCESS)

    def test_payment_pending_to_failed(self):
        validate_transition(TransactionStatus.PAYMENT_PENDING, TransactionStatus.FAILED)

    # ── Valid transitions using string values ──

    def test_string_values_accepted(self):
        validate_transition("REQUESTED", "POLICY_CHECK")
        validate_transition("POLICY_CHECK", "APPROVED")
        validate_transition("APPROVED", "PAYMENT_PENDING")

    # ── Invalid Transitions ──

    def test_requested_to_success_raises(self):
        with pytest.raises(InvalidPaymentStateError, match="cannot transition from REQUESTED to SUCCESS"):
            validate_transition(TransactionStatus.REQUESTED, TransactionStatus.SUCCESS)

    def test_requested_to_payment_pending_raises(self):
        with pytest.raises(InvalidPaymentStateError, match="cannot transition from REQUESTED to PAYMENT_PENDING"):
            validate_transition(TransactionStatus.REQUESTED, TransactionStatus.PAYMENT_PENDING)

    def test_success_to_payment_pending_raises(self):
        with pytest.raises(InvalidPaymentStateError, match="cannot transition from SUCCESS to PAYMENT_PENDING"):
            validate_transition(TransactionStatus.SUCCESS, TransactionStatus.PAYMENT_PENDING)

    def test_success_to_failed_raises(self):
        with pytest.raises(InvalidPaymentStateError, match="cannot transition from SUCCESS to FAILED"):
            validate_transition(TransactionStatus.SUCCESS, TransactionStatus.FAILED)

    def test_rejected_to_success_raises(self):
        with pytest.raises(InvalidPaymentStateError, match="cannot transition from REJECTED to SUCCESS"):
            validate_transition(TransactionStatus.REJECTED, TransactionStatus.SUCCESS)

    def test_rejected_to_payment_pending_raises(self):
        with pytest.raises(InvalidPaymentStateError, match="cannot transition from REJECTED to PAYMENT_PENDING"):
            validate_transition(TransactionStatus.REJECTED, TransactionStatus.PAYMENT_PENDING)

    def test_approved_to_success_raises(self):
        with pytest.raises(InvalidPaymentStateError, match="cannot transition from APPROVED to SUCCESS"):
            validate_transition(TransactionStatus.APPROVED, TransactionStatus.SUCCESS)

    def test_payment_pending_to_approved_raises(self):
        with pytest.raises(InvalidPaymentStateError, match="cannot transition from PAYMENT_PENDING to APPROVED"):
            validate_transition(TransactionStatus.PAYMENT_PENDING, TransactionStatus.APPROVED)

    # ── Terminal states cannot transition to anything ──

    def test_success_to_any_raises(self):
        for target in TransactionStatus:
            with pytest.raises(InvalidPaymentStateError):
                validate_transition(TransactionStatus.SUCCESS, target)

    def test_rejected_to_any_raises(self):
        for target in TransactionStatus:
            with pytest.raises(InvalidPaymentStateError):
                validate_transition(TransactionStatus.REJECTED, target)

    # ── Invalid / unrecognized status strings ──

    def test_unknown_current_status_raises(self):
        with pytest.raises(InvalidPaymentStateError, match="not a valid TransactionStatus"):
            validate_transition("BOGUS_STATE", TransactionStatus.SUCCESS)

    def test_unknown_target_status_raises(self):
        with pytest.raises(InvalidPaymentStateError, match="not a valid TransactionStatus"):
            validate_transition(TransactionStatus.REQUESTED, "BOGUS_STATE")


class TestTransactionTransitionTo:
    """Test the Transaction.transition_to() instance method on the model."""

    def _make_transaction(self, status: TransactionStatus) -> Transaction:
        """Helper: create a Transaction instance with a given initial status."""
        return Transaction(
            id=uuid.uuid4(),
            idempotency_key=f"test_{uuid.uuid4().hex[:12]}",
            agent_id=uuid.uuid4(),
            wallet_id=uuid.uuid4(),
            merchant_name="Test Merchant",
            category="test",
            amount=100.0,
            currency="INR",
            status=status.value,
        )

    # ── Valid transitions via transition_to ──

    def test_requested_to_policy_check(self):
        tx = self._make_transaction(TransactionStatus.REQUESTED)
        tx.transition_to(TransactionStatus.POLICY_CHECK)
        assert tx.status == TransactionStatus.POLICY_CHECK.value

    def test_policy_check_to_approved(self):
        tx = self._make_transaction(TransactionStatus.POLICY_CHECK)
        tx.transition_to(TransactionStatus.APPROVED)
        assert tx.status == TransactionStatus.APPROVED.value

    def test_policy_check_to_rejected(self):
        tx = self._make_transaction(TransactionStatus.POLICY_CHECK)
        tx.transition_to(TransactionStatus.REJECTED)
        assert tx.status == TransactionStatus.REJECTED.value

    def test_approved_to_payment_pending(self):
        tx = self._make_transaction(TransactionStatus.APPROVED)
        tx.transition_to(TransactionStatus.PAYMENT_PENDING)
        assert tx.status == TransactionStatus.PAYMENT_PENDING.value

    def test_payment_pending_to_success(self):
        tx = self._make_transaction(TransactionStatus.PAYMENT_PENDING)
        tx.transition_to(TransactionStatus.SUCCESS)
        assert tx.status == TransactionStatus.SUCCESS.value

    def test_payment_pending_to_failed(self):
        tx = self._make_transaction(TransactionStatus.PAYMENT_PENDING)
        tx.transition_to(TransactionStatus.FAILED)
        assert tx.status == TransactionStatus.FAILED.value

    # ── Full lifecycle walk-through ──

    def test_full_lifecycle_success(self):
        tx = self._make_transaction(TransactionStatus.REQUESTED)
        tx.transition_to(TransactionStatus.POLICY_CHECK)
        tx.transition_to(TransactionStatus.APPROVED)
        tx.transition_to(TransactionStatus.PAYMENT_PENDING)
        tx.transition_to(TransactionStatus.SUCCESS)
        assert tx.status == TransactionStatus.SUCCESS.value

    def test_full_lifecycle_rejected(self):
        tx = self._make_transaction(TransactionStatus.REQUESTED)
        tx.transition_to(TransactionStatus.POLICY_CHECK)
        tx.transition_to(TransactionStatus.REJECTED)
        assert tx.status == TransactionStatus.REJECTED.value

    def test_full_lifecycle_failed(self):
        tx = self._make_transaction(TransactionStatus.REQUESTED)
        tx.transition_to(TransactionStatus.POLICY_CHECK)
        tx.transition_to(TransactionStatus.APPROVED)
        tx.transition_to(TransactionStatus.PAYMENT_PENDING)
        tx.transition_to(TransactionStatus.FAILED)
        assert tx.status == TransactionStatus.FAILED.value

    # ── Invalid transitions via transition_to ──

    def test_requested_to_success_raises(self):
        tx = self._make_transaction(TransactionStatus.REQUESTED)
        with pytest.raises(InvalidPaymentStateError):
            tx.transition_to(TransactionStatus.SUCCESS)
        # Status must NOT have changed
        assert tx.status == TransactionStatus.REQUESTED.value

    def test_requested_to_payment_pending_raises(self):
        tx = self._make_transaction(TransactionStatus.REQUESTED)
        with pytest.raises(InvalidPaymentStateError):
            tx.transition_to(TransactionStatus.PAYMENT_PENDING)
        assert tx.status == TransactionStatus.REQUESTED.value

    def test_success_to_payment_pending_raises(self):
        tx = self._make_transaction(TransactionStatus.SUCCESS)
        with pytest.raises(InvalidPaymentStateError):
            tx.transition_to(TransactionStatus.PAYMENT_PENDING)
        assert tx.status == TransactionStatus.SUCCESS.value

    def test_success_to_failed_raises(self):
        tx = self._make_transaction(TransactionStatus.SUCCESS)
        with pytest.raises(InvalidPaymentStateError):
            tx.transition_to(TransactionStatus.FAILED)
        assert tx.status == TransactionStatus.SUCCESS.value

    def test_rejected_to_success_raises(self):
        tx = self._make_transaction(TransactionStatus.REJECTED)
        with pytest.raises(InvalidPaymentStateError):
            tx.transition_to(TransactionStatus.SUCCESS)
        assert tx.status == TransactionStatus.REJECTED.value

    def test_rejected_to_payment_pending_raises(self):
        tx = self._make_transaction(TransactionStatus.REJECTED)
        with pytest.raises(InvalidPaymentStateError):
            tx.transition_to(TransactionStatus.PAYMENT_PENDING)
        assert tx.status == TransactionStatus.REJECTED.value

    def test_approved_to_success_raises(self):
        tx = self._make_transaction(TransactionStatus.APPROVED)
        with pytest.raises(InvalidPaymentStateError):
            tx.transition_to(TransactionStatus.SUCCESS)
        assert tx.status == TransactionStatus.APPROVED.value

    def test_payment_pending_to_approved_raises(self):
        tx = self._make_transaction(TransactionStatus.PAYMENT_PENDING)
        with pytest.raises(InvalidPaymentStateError):
            tx.transition_to(TransactionStatus.APPROVED)
        assert tx.status == TransactionStatus.PAYMENT_PENDING.value

    # ── Terminal states: exhaustive check ──

    def test_success_terminal_no_transitions(self):
        tx = self._make_transaction(TransactionStatus.SUCCESS)
        for target in TransactionStatus:
            with pytest.raises(InvalidPaymentStateError):
                tx.transition_to(target)
            assert tx.status == TransactionStatus.SUCCESS.value

    def test_rejected_terminal_no_transitions(self):
        tx = self._make_transaction(TransactionStatus.REJECTED)
        for target in TransactionStatus:
            with pytest.raises(InvalidPaymentStateError):
                tx.transition_to(target)
            assert tx.status == TransactionStatus.REJECTED.value

    # ── String input accepted by transition_to ──

    def test_transition_to_accepts_string(self):
        tx = self._make_transaction(TransactionStatus.REQUESTED)
        tx.transition_to("POLICY_CHECK")
        assert tx.status == TransactionStatus.POLICY_CHECK.value
