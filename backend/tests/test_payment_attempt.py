"""
Day 3 Phase 1 Step 3: PaymentAttempt Entity & Relationship Tests
Verifies the PaymentAttempt persistence layer, Transaction relationship,
and (transaction_id, attempt_number) uniqueness constraints.
"""
import uuid
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from app.models.transaction import Transaction, TransactionStatus
from app.models.payment_attempt import PaymentAttempt
from app.models.payment_method import PaymentMethod


class TestPaymentAttemptPersistence:
    """Test suite for PaymentAttempt model, relationships, and constraints."""

    def _create_tx(self, db_session, test_seed_data, custom_id=None) -> Transaction:
        agent = test_seed_data["agent"]
        wallet = test_seed_data["wallet"]
        tx = Transaction(
            id=custom_id or uuid.uuid4(),
            idempotency_key=f"tx_test_{uuid.uuid4().hex[:12]}",
            agent_id=agent.id,
            wallet_id=wallet.id,
            merchant_name="Netflix",
            category="subscriptions",
            amount=499.0,
            currency="INR",
            status=TransactionStatus.PAYMENT_PENDING.value,
        )
        db_session.add(tx)
        db_session.commit()
        db_session.refresh(tx)
        return tx

    def test_1_payment_attempt_creation(self, db_session, test_seed_data):
        """1. A PaymentAttempt can be created for a Transaction."""
        tx = self._create_tx(db_session, test_seed_data)

        attempt = PaymentAttempt(
            id=uuid.uuid4(),
            transaction_id=tx.id,
            attempt_number=1,
            status="SUCCESS",
            provider_payment_id="pay_mock_12345",
            error_code=None,
            error_message=None,
            response_payload={"gateway": "mock", "code": 200},
        )
        db_session.add(attempt)
        db_session.commit()
        db_session.refresh(attempt)

        assert attempt.id is not None
        assert attempt.transaction_id == tx.id
        assert attempt.attempt_number == 1
        assert attempt.status == "SUCCESS"
        assert attempt.provider_payment_id == "pay_mock_12345"
        assert attempt.response_payload == {"gateway": "mock", "code": 200}
        assert attempt.created_at is not None
        assert attempt.updated_at is not None

    def test_2_payment_attempt_to_transaction_relationship(self, db_session, test_seed_data):
        """2. PaymentAttempt.transaction relationship works."""
        tx = self._create_tx(db_session, test_seed_data)

        attempt = PaymentAttempt(
            id=uuid.uuid4(),
            transaction_id=tx.id,
            attempt_number=1,
            status="FAILED",
            error_code="GATEWAY_REJECTED",
            error_message="Card expired",
        )
        db_session.add(attempt)
        db_session.commit()
        db_session.refresh(attempt)

        # Access relationship from attempt to transaction
        assert attempt.transaction is not None
        assert attempt.transaction.id == tx.id
        assert attempt.transaction.merchant_name == "Netflix"
        assert attempt.transaction.amount == 499.0

    def test_3_transaction_to_payment_attempts_relationship(self, db_session, test_seed_data):
        """3. Transaction.payment_attempts returns the associated attempts."""
        tx = self._create_tx(db_session, test_seed_data)

        attempt = PaymentAttempt(
            id=uuid.uuid4(),
            transaction_id=tx.id,
            attempt_number=1,
            status="SUCCESS",
            provider_payment_id="pay_attempt_001",
        )
        db_session.add(attempt)
        db_session.commit()
        db_session.refresh(tx)

        # Access relationship from transaction to attempts
        assert len(tx.payment_attempts) == 1
        assert tx.payment_attempts[0].id == attempt.id
        assert tx.payment_attempts[0].provider_payment_id == "pay_attempt_001"

    def test_4_multiple_attempts_belonging_to_same_transaction(self, db_session, test_seed_data):
        """4. Multiple attempts can belong to the same transaction."""
        tx = self._create_tx(db_session, test_seed_data)

        attempt_1 = PaymentAttempt(
            id=uuid.uuid4(),
            transaction_id=tx.id,
            attempt_number=1,
            status="FAILED",
            error_code="NETWORK_ERROR",
            error_message="Connection timed out",
        )
        attempt_2 = PaymentAttempt(
            id=uuid.uuid4(),
            transaction_id=tx.id,
            attempt_number=2,
            status="SUCCESS",
            provider_payment_id="pay_retry_success_002",
        )
        db_session.add_all([attempt_1, attempt_2])
        db_session.commit()
        db_session.refresh(tx)

        assert len(tx.payment_attempts) == 2
        statuses = [a.status for a in tx.payment_attempts]
        assert statuses == ["FAILED", "SUCCESS"]

    def test_5_attempt_numbers_1_and_2_coexist(self, db_session, test_seed_data):
        """5. attempt_number 1 and 2 can coexist for the same transaction."""
        tx = self._create_tx(db_session, test_seed_data)

        attempt_1 = PaymentAttempt(
            id=uuid.uuid4(),
            transaction_id=tx.id,
            attempt_number=1,
            status="FAILED",
        )
        attempt_2 = PaymentAttempt(
            id=uuid.uuid4(),
            transaction_id=tx.id,
            attempt_number=2,
            status="SUCCESS",
        )
        db_session.add_all([attempt_1, attempt_2])
        db_session.commit()
        db_session.refresh(tx)

        numbers = [a.attempt_number for a in tx.payment_attempts]
        assert numbers == [1, 2]

    def test_6_duplicate_transaction_and_attempt_number_rejected(self, db_session, test_seed_data):
        """6. Duplicate (transaction_id, attempt_number) is rejected by the database uniqueness constraint."""
        tx = self._create_tx(db_session, test_seed_data)

        attempt_1 = PaymentAttempt(
            id=uuid.uuid4(),
            transaction_id=tx.id,
            attempt_number=1,
            status="FAILED",
        )
        db_session.add(attempt_1)
        db_session.commit()

        # Attempt to insert a second record with the identical transaction_id and attempt_number=1
        attempt_duplicate = PaymentAttempt(
            id=uuid.uuid4(),
            transaction_id=tx.id,
            attempt_number=1,
            status="SUCCESS",
        )
        db_session.add(attempt_duplicate)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

    def test_7_different_transactions_can_each_have_attempt_number_1(self, db_session, test_seed_data):
        """7. Different transactions can each have attempt_number 1 without conflict."""
        tx_a = self._create_tx(db_session, test_seed_data)
        tx_b = self._create_tx(db_session, test_seed_data)

        attempt_a = PaymentAttempt(
            id=uuid.uuid4(),
            transaction_id=tx_a.id,
            attempt_number=1,
            status="SUCCESS",
            provider_payment_id="pay_a_001",
        )
        attempt_b = PaymentAttempt(
            id=uuid.uuid4(),
            transaction_id=tx_b.id,
            attempt_number=1,
            status="SUCCESS",
            provider_payment_id="pay_b_001",
        )
        db_session.add_all([attempt_a, attempt_b])
        db_session.commit()

        db_session.refresh(tx_a)
        db_session.refresh(tx_b)

        assert len(tx_a.payment_attempts) == 1
        assert tx_a.payment_attempts[0].attempt_number == 1
        assert len(tx_b.payment_attempts) == 1
        assert tx_b.payment_attempts[0].attempt_number == 1

    def test_8_payment_method_association(self, db_session, test_seed_data):
        """Verify optional PaymentMethod association with PaymentAttempt."""
        tx = self._create_tx(db_session, test_seed_data)
        wallet = test_seed_data["wallet"]
        primary_pm = db_session.execute(
            select(PaymentMethod).where(PaymentMethod.wallet_id == wallet.id)
        ).scalars().first()

        attempt = PaymentAttempt(
            id=uuid.uuid4(),
            transaction_id=tx.id,
            payment_method_id=primary_pm.id if primary_pm else None,
            attempt_number=1,
            status="SUCCESS",
        )
        db_session.add(attempt)
        db_session.commit()
        db_session.refresh(attempt)

        if primary_pm:
            assert attempt.payment_method is not None
            assert attempt.payment_method.id == primary_pm.id
