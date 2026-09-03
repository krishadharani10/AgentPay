"""
Day 4 Phase 1.5 — Part A: Adversarial Security Hardening Tests

Tests realistic bypass attempts against AgentPay's security boundaries.
For every failed authorization attempt, the test ALSO verifies that
the payment provider was NOT called (provider.call_count == 0 or unchanged).

Bypass attempts covered:
 1. Direct transaction status manipulation via state machine
 2. SUCCESS → PAYMENT_PENDING (blocked by state machine)
 3. SUCCESS → FAILED (blocked by state machine)
 4. REJECTED → SUCCESS (blocked by state machine)
 5. FAILED → SUCCESS (blocked by state machine, no allow_retry)
 6. Direct provider execution bypass (PaymentService always policy-checks first)
 7. PaymentAttempt duplicate-number manipulation (DB unique constraint)
 8. Attempt #3 after MAX_RETRIES exhausted (MaxRetriesExceededError)
 9. Idempotency key replay with modified amount (original transaction is returned)
10. Idempotency key replay with modified merchant (original transaction is returned)
11. Fallback without policy engine evaluation (impossible; fallback always calls evaluate_and_audit)
12. Fallback using a different wallet's payment method (PolicyViolationError)
13. Payment using an inactive wallet (WALLET_DISABLED policy rejection)
14. Payment using an unauthorized/inactive payment method (blocked before provider)
15. AI-generated request exceeding policy limits (PolicyViolationError, provider not called)
16. AI-generated request for blocked merchant/category (PolicyViolationError, provider not called)
17. Payment execution after policy rejection (second process_payment raises PolicyViolationError)
18. Rejected transaction cannot be retried
"""
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.transaction import (
    Transaction,
    TransactionStatus,
    InvalidPaymentStateError,
    MaxRetriesExceededError,
    validate_transition,
)
from app.models.payment_attempt import PaymentAttempt
from app.models.payment_method import PaymentMethod
from app.models.wallet import Wallet
from app.models.policy import Policy
from app.models.agent import Agent
from app.services.payment_adapter import (
    MockPaymentProvider,
    MockPaymentMode,
    PaymentFailureReason,
)
from app.services.payment_service import (
    PaymentService,
    PolicyViolationError,
    MAX_RETRIES,
)


class TestStateMachineBypassAttempts:
    """Tests 1-5: Direct transaction status manipulation is blocked by the state machine."""

    def _make_tx(self, status: TransactionStatus) -> Transaction:
        return Transaction(
            id=uuid.uuid4(),
            idempotency_key=f"sec_test_{uuid.uuid4().hex[:12]}",
            agent_id=uuid.uuid4(),
            wallet_id=uuid.uuid4(),
            merchant_name="Attacker Merchant",
            category="utilities",
            amount=1000.0,
            currency="INR",
            status=status.value,
        )

    def test_1_cannot_directly_set_success_via_transition_to(self):
        """Test 1: Terminal SUCCESS cannot be transitioned to anything."""
        tx = self._make_tx(TransactionStatus.SUCCESS)
        for target in TransactionStatus:
            with pytest.raises(InvalidPaymentStateError):
                tx.transition_to(target)
        assert tx.status == TransactionStatus.SUCCESS.value

    def test_2_success_to_payment_pending_blocked(self):
        """Test 2: SUCCESS → PAYMENT_PENDING is illegal."""
        tx = self._make_tx(TransactionStatus.SUCCESS)
        with pytest.raises(InvalidPaymentStateError, match="SUCCESS to PAYMENT_PENDING"):
            tx.transition_to(TransactionStatus.PAYMENT_PENDING)
        assert tx.status == TransactionStatus.SUCCESS.value

    def test_3_success_to_failed_blocked(self):
        """Test 3: SUCCESS → FAILED is illegal."""
        tx = self._make_tx(TransactionStatus.SUCCESS)
        with pytest.raises(InvalidPaymentStateError, match="SUCCESS to FAILED"):
            tx.transition_to(TransactionStatus.FAILED)
        assert tx.status == TransactionStatus.SUCCESS.value

    def test_4_rejected_to_success_blocked(self):
        """Test 4: REJECTED → SUCCESS is illegal."""
        tx = self._make_tx(TransactionStatus.REJECTED)
        with pytest.raises(InvalidPaymentStateError, match="REJECTED to SUCCESS"):
            tx.transition_to(TransactionStatus.SUCCESS)
        assert tx.status == TransactionStatus.REJECTED.value

    def test_5_failed_to_success_without_allow_retry_blocked(self):
        """Test 5: FAILED → SUCCESS is illegal without going through PAYMENT_PENDING."""
        tx = self._make_tx(TransactionStatus.FAILED)
        with pytest.raises(InvalidPaymentStateError, match="FAILED to SUCCESS"):
            tx.transition_to(TransactionStatus.SUCCESS)
        assert tx.status == TransactionStatus.FAILED.value

    def test_5b_failed_to_payment_pending_without_allow_retry_blocked(self):
        """Test 5b: FAILED → PAYMENT_PENDING is blocked without allow_retry=True."""
        tx = self._make_tx(TransactionStatus.FAILED)
        with pytest.raises(InvalidPaymentStateError):
            tx.transition_to(TransactionStatus.PAYMENT_PENDING)
        assert tx.status == TransactionStatus.FAILED.value

    def test_5c_failed_to_payment_pending_with_allow_retry_permitted(self):
        """Test 5c: FAILED → PAYMENT_PENDING is ONLY permitted with explicit allow_retry=True."""
        tx = self._make_tx(TransactionStatus.FAILED)
        # This is the ONLY valid path back from FAILED
        tx.transition_to(TransactionStatus.PAYMENT_PENDING, allow_retry=True)
        assert tx.status == TransactionStatus.PAYMENT_PENDING.value


class TestProviderBypassAttempts:
    """Test 6: Payment provider cannot be invoked without policy authorization."""

    def test_6_policy_rejection_blocks_provider(self, db_session, test_seed_data):
        """Test 6: When policy rejects, provider.call_count MUST remain 0."""
        agent = test_seed_data["agent"]
        policy = test_seed_data["policy"]

        # Set an impossibly low limit to guarantee rejection
        original_limit = policy.max_transaction_amount
        policy.max_transaction_amount = 1.0
        db_session.commit()

        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        with pytest.raises(PolicyViolationError):
            service.process_payment(
                db_session,
                merchant_name="Torrent Power",
                amount=1240.0,
                category="utilities",
                agent_id=agent.id,
            )

        # CRITICAL: Provider must NEVER be called when policy rejects
        assert provider.call_count == 0

        # Restore
        policy.max_transaction_amount = original_limit
        db_session.commit()

    def test_6b_blocked_category_blocks_provider(self, db_session, test_seed_data):
        """Test 6b: Blocked category stops payment before provider dispatch."""
        agent = test_seed_data["agent"]
        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        with pytest.raises(PolicyViolationError) as exc_info:
            service.process_payment(
                db_session,
                merchant_name="Crypto Exchange",
                amount=500.0,
                category="crypto",
                agent_id=agent.id,
            )

        assert provider.call_count == 0
        assert exc_info.value.decision_code in ("CATEGORY_BLOCKED", "MULTIPLE_POLICY_VIOLATIONS")

    def test_6c_blocked_merchant_blocks_provider(self, db_session, test_seed_data):
        """Test 6c: Blocked merchant stops payment before provider dispatch."""
        agent = test_seed_data["agent"]
        policy = test_seed_data["policy"]

        original_blocked = policy.blocked_merchants
        policy.blocked_merchants = ["EvilMerchant"]
        db_session.commit()

        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        with pytest.raises(PolicyViolationError) as exc_info:
            service.process_payment(
                db_session,
                merchant_name="EvilMerchant",
                amount=500.0,
                category="utilities",
                agent_id=agent.id,
            )

        assert provider.call_count == 0
        assert exc_info.value.decision_code in ("MERCHANT_BLOCKED", "MULTIPLE_POLICY_VIOLATIONS")

        policy.blocked_merchants = original_blocked
        db_session.commit()

    def test_6d_daily_limit_exceeded_blocks_provider(self, db_session, test_seed_data):
        """Test 6d: Daily limit exceeded stops payment before provider dispatch."""
        agent = test_seed_data["agent"]
        wallet = test_seed_data["wallet"]
        policy = test_seed_data["policy"]

        # Seed a SUCCESS transaction that fills the daily limit
        tx_existing = Transaction(
            id=uuid.uuid4(),
            idempotency_key=f"sec_fill_budget_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
            wallet_id=wallet.id,
            merchant_name="Netflix",
            category="subscriptions",
            amount=policy.daily_spending_limit,  # Fill the entire daily budget
            currency="INR",
            status=TransactionStatus.SUCCESS.value,
        )
        db_session.add(tx_existing)
        db_session.commit()

        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        with pytest.raises(PolicyViolationError) as exc_info:
            service.process_payment(
                db_session,
                merchant_name="Torrent Power",
                amount=1.0,  # Even ₹1 should be blocked
                category="utilities",
                agent_id=agent.id,
            )

        assert provider.call_count == 0
        assert exc_info.value.decision_code in ("DAILY_LIMIT_EXCEEDED", "MULTIPLE_POLICY_VIOLATIONS")


class TestPaymentAttemptManipulation:
    """Tests 7-8: PaymentAttempt number manipulation and MAX_RETRIES enforcement."""

    def test_7_duplicate_attempt_number_blocked_by_db_constraint(self, db_session, test_seed_data):
        """Test 7: DB unique constraint prevents duplicate attempt numbers per transaction."""
        agent = test_seed_data["agent"]
        wallet = test_seed_data["wallet"]

        tx = Transaction(
            id=uuid.uuid4(),
            idempotency_key=f"sec_dup_attempt_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
            wallet_id=wallet.id,
            merchant_name="Test",
            category="utilities",
            amount=100.0,
            status=TransactionStatus.FAILED.value,
        )
        db_session.add(tx)
        db_session.commit()

        attempt1 = PaymentAttempt(
            id=uuid.uuid4(),
            transaction_id=tx.id,
            attempt_number=1,
            status="FAILED",
            error_code="TIMEOUT",
        )
        db_session.add(attempt1)
        db_session.commit()

        # Duplicate attempt_number=1 for same transaction_id must fail
        attempt1_dup = PaymentAttempt(
            id=uuid.uuid4(),
            transaction_id=tx.id,
            attempt_number=1,  # duplicate!
            status="SUCCESS",
        )
        db_session.add(attempt1_dup)
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_8_attempt_3_impossible_after_max_retries(self, db_session, test_seed_data):
        """Test 8: After 2 attempts (MAX_RETRIES=1), a 3rd attempt raises MaxRetriesExceededError.
        Critically, the provider must NOT be called on the blocked 3rd attempt."""
        provider = MockPaymentProvider(mode=MockPaymentMode.DECLINED)
        service = PaymentService(provider=provider)

        res1 = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=f"sec_max_retries_{uuid.uuid4().hex[:8]}",
        )
        payment_id = uuid.UUID(res1["payment_id"])
        assert provider.call_count == 1

        # Second attempt (Attempt #2) - allowed
        service.retry_payment(db_session, payment_id=payment_id)
        assert provider.call_count == 2

        # Third attempt - MUST be rejected, provider MUST NOT be called
        with pytest.raises(MaxRetriesExceededError):
            service.retry_payment(db_session, payment_id=payment_id)

        # Provider call count must still be 2, not 3
        assert provider.call_count == 2

        # DB: Still only 2 PaymentAttempt records
        attempts = db_session.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == payment_id)
        ).scalars().all()
        assert len(attempts) == 2


class TestIdempotencyAttackAttempts:
    """Tests 9-10: Idempotency key replay with modified parameters."""

    def test_9_idempotency_replay_with_modified_amount_returns_original(self, db_session, test_seed_data):
        """Test 9: Replaying the same idempotency key with a different amount returns the
        original successful transaction, NOT a new payment at the modified amount."""
        shared_key = f"sec_idem_amount_{uuid.uuid4().hex[:8]}"
        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        # Original payment: ₹499
        res1 = service.process_payment(
            db_session,
            merchant_name="Netflix",
            amount=499.0,
            category="subscriptions",
            idempotency_key=shared_key,
        )
        assert res1["success"] is True
        assert res1["amount"] == 499.0
        original_payment_id = res1["payment_id"]
        assert provider.call_count == 1

        # Replay same key but with ₹9999 — attacker trying to pay more
        res2 = service.process_payment(
            db_session,
            merchant_name="Netflix",
            amount=9999.0,  # Modified amount!
            category="subscriptions",
            idempotency_key=shared_key,
        )

        # Must return the ORIGINAL transaction, not a new one
        assert res2["payment_id"] == original_payment_id
        assert res2["success"] is True
        # Provider must NOT have been called again
        assert provider.call_count == 1

        # Only 1 transaction in DB
        txs = db_session.execute(
            select(Transaction).where(Transaction.idempotency_key == shared_key)
        ).scalars().all()
        assert len(txs) == 1
        assert txs[0].amount == 499.0  # Original amount preserved

    def test_10_idempotency_replay_with_modified_merchant_returns_original(self, db_session, test_seed_data):
        """Test 10: Replaying the same idempotency key with a different merchant returns
        the original transaction — the modified merchant has no effect."""
        shared_key = f"sec_idem_merchant_{uuid.uuid4().hex[:8]}"
        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        # Original payment: Torrent Power
        res1 = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=shared_key,
        )
        assert res1["success"] is True
        original_payment_id = res1["payment_id"]
        assert provider.call_count == 1

        # Replay same key but with a different merchant
        res2 = service.process_payment(
            db_session,
            merchant_name="Crypto Exchange",  # Modified merchant (even a blocked one!)
            amount=1240.0,
            category="crypto",
            idempotency_key=shared_key,
        )

        # Must return the ORIGINAL transaction
        assert res2["payment_id"] == original_payment_id
        assert provider.call_count == 1  # No additional provider call


class TestFallbackBypassAttempts:
    """Tests 11-14: Fallback cannot bypass policy or use unauthorized payment methods."""

    def test_11_fallback_policy_evaluated_independently(self, db_session, test_seed_data):
        """Test 11: Fallback MUST be rejected when policy disapproves, provider NOT called."""
        agent = test_seed_data["agent"]
        policy = test_seed_data["policy"]
        wallet = test_seed_data["wallet"]

        # Primary fails
        provider = MockPaymentProvider(mode=MockPaymentMode.NETWORK_ERROR)
        service = PaymentService(provider=provider)

        res1 = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=f"sec_fb_pol_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
        )
        payment_id = uuid.UUID(res1["payment_id"])
        assert provider.call_count == 1

        # Restrict policy to block fallback
        original_limit = policy.daily_spending_limit
        policy.daily_spending_limit = 50.0  # Way below ₹1,240
        db_session.commit()

        try:
            with pytest.raises(PolicyViolationError):
                service.execute_fallback_payment(db_session, payment_id=payment_id)

            # Provider must NOT have been called for the blocked fallback
            assert provider.call_count == 1  # Still only 1 from primary attempt
        finally:
            policy.daily_spending_limit = original_limit
            db_session.commit()

    def test_12_fallback_with_cross_wallet_payment_method_blocked(self, db_session, test_seed_data):
        """Test 12: Using a payment method from a different wallet is blocked before provider."""
        agent = test_seed_data["agent"]
        wallet = test_seed_data["wallet"]

        # Create a separate "other" agent + wallet with its own payment method
        from app.models.user import User
        other_agent = Agent(
            id=uuid.uuid4(),
            user_id=agent.user_id,  # same user is fine
            name="Other Agent For Cross-Wallet Test",
            description="Test agent",
            is_active=True,
        )
        db_session.add(other_agent)
        db_session.flush()

        other_wallet = Wallet(
            id=uuid.uuid4(),
            agent_id=other_agent.id,  # Different agent → avoids unique constraint
            status="ACTIVE",
            daily_spending_limit=10000.0,
            per_transaction_limit=5000.0,
            currency="INR",
        )
        db_session.add(other_wallet)
        db_session.flush()

        other_pm = PaymentMethod(
            id=uuid.uuid4(),
            wallet_id=other_wallet.id,
            type="CARD",
            provider="Mock",
            token_or_alias="other_card_token",
            is_primary=False,
            is_active=True,
            priority=2,
        )
        db_session.add(other_pm)
        db_session.commit()

        # Primary fails on THE ORIGINAL WALLET
        provider = MockPaymentProvider(mode=MockPaymentMode.DECLINED)
        service = PaymentService(provider=provider)

        res1 = service.process_payment(
            db_session,
            merchant_name="Netflix",
            amount=499.0,
            category="subscriptions",
            idempotency_key=f"sec_cross_wallet_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
        )
        payment_id = uuid.UUID(res1["payment_id"])
        assert provider.call_count == 1

        # Try fallback using a payment method from the OTHER wallet
        with pytest.raises(PolicyViolationError) as exc_info:
            service.execute_fallback_payment(
                db_session,
                payment_id=payment_id,
                fallback_method_id=other_pm.id,  # From wrong wallet!
            )

        assert "UNAUTHORIZED_PAYMENT_METHOD" in exc_info.value.decision_code
        # Provider must NOT be called for the cross-wallet attempt
        assert provider.call_count == 1

    def test_13_payment_with_inactive_wallet_blocked(self, db_session, test_seed_data):
        """Test 13: Payment through an inactive/disabled wallet is rejected before provider."""
        agent = test_seed_data["agent"]
        wallet = test_seed_data["wallet"]

        original_status = wallet.status
        wallet.status = "DISABLED"
        db_session.commit()

        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        try:
            with pytest.raises(PolicyViolationError) as exc_info:
                service.process_payment(
                    db_session,
                    merchant_name="Torrent Power",
                    amount=1240.0,
                    category="utilities",
                    agent_id=agent.id,
                )

            # Provider MUST NOT be called when wallet is disabled
            assert provider.call_count == 0
            assert exc_info.value.decision_code in ("WALLET_DISABLED", "MULTIPLE_POLICY_VIOLATIONS")
        finally:
            wallet.status = original_status
            db_session.commit()

    def test_14_inactive_fallback_payment_method_blocked_before_provider(self, db_session, test_seed_data):
        """Test 14: Inactive fallback payment method blocked before provider call."""
        agent = test_seed_data["agent"]
        wallet = test_seed_data["wallet"]

        # Get the fallback payment method and deactivate it
        fallback_pm = db_session.execute(
            select(PaymentMethod).where(
                PaymentMethod.wallet_id == wallet.id,
                PaymentMethod.is_primary == False,
            )
        ).scalar_one()

        original_active = fallback_pm.is_active
        fallback_pm.is_active = False
        db_session.commit()

        provider = MockPaymentProvider(
            mode_sequence=[MockPaymentMode.DECLINED, MockPaymentMode.SUCCESS]
        )
        service = PaymentService(provider=provider)

        res1 = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=f"sec_inactive_pm_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
        )
        payment_id = uuid.UUID(res1["payment_id"])
        assert provider.call_count == 1

        # Try fallback with the inactive method
        with pytest.raises(InvalidPaymentStateError, match="inactive"):
            service.execute_fallback_payment(
                db_session,
                payment_id=payment_id,
                fallback_method_id=fallback_pm.id,
            )

        # Provider MUST NOT be called for the inactive payment method
        assert provider.call_count == 1

        fallback_pm.is_active = original_active
        db_session.commit()


class TestAIAgentPolicyBoundary:
    """Tests 15-18: AI/Agent-generated requests cannot bypass policy boundaries."""

    def test_15_agent_request_exceeding_tx_limit_blocked(self, db_session, test_seed_data):
        """Test 15: AI-generated request exceeding per-transaction limit is rejected.
        Provider is NOT called."""
        agent = test_seed_data["agent"]
        policy = test_seed_data["policy"]

        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        # Try to pay ₹50,000 — well above policy max of ₹5,000
        with pytest.raises(PolicyViolationError) as exc_info:
            service.process_payment(
                db_session,
                merchant_name="MakeMyTrip",
                amount=50000.0,
                category="travel",
                agent_id=agent.id,
            )

        assert provider.call_count == 0
        assert exc_info.value.decision_code in ("TX_LIMIT_EXCEEDED", "MULTIPLE_POLICY_VIOLATIONS")

    def test_16_agent_request_blocked_merchant_rejected(self, db_session, test_seed_data):
        """Test 16: AI-generated request for blocked merchant rejected before provider."""
        agent = test_seed_data["agent"]
        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        with pytest.raises(PolicyViolationError) as exc_info:
            service.process_payment(
                db_session,
                merchant_name="Casino Royal",
                amount=100.0,
                category="gambling",  # Blocked category
                agent_id=agent.id,
            )

        assert provider.call_count == 0
        assert exc_info.value.decision_code in (
            "CATEGORY_BLOCKED", "CATEGORY_NOT_ALLOWED", "MULTIPLE_POLICY_VIOLATIONS"
        )

    def test_17_payment_execution_after_policy_rejection_still_blocked(self, db_session, test_seed_data):
        """Test 17: After a transaction is REJECTED by policy, a second identical request
        for the same idempotency key is also rejected. Provider is NOT called on either."""
        agent = test_seed_data["agent"]
        policy = test_seed_data["policy"]

        shared_key = f"sec_post_rej_{uuid.uuid4().hex[:8]}"
        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        original_limit = policy.max_transaction_amount
        policy.max_transaction_amount = 1.0  # Force rejection
        db_session.commit()

        try:
            # First request: REJECTED by policy
            with pytest.raises(PolicyViolationError):
                service.process_payment(
                    db_session,
                    merchant_name="Torrent Power",
                    amount=1240.0,
                    category="utilities",
                    idempotency_key=shared_key,
                    agent_id=agent.id,
                )
            assert provider.call_count == 0

            # Second request with same key: also REJECTED (returns previously rejected transaction)
            with pytest.raises(PolicyViolationError) as exc_info:
                service.process_payment(
                    db_session,
                    merchant_name="Torrent Power",
                    amount=1240.0,
                    category="utilities",
                    idempotency_key=shared_key,
                    agent_id=agent.id,
                )
            assert provider.call_count == 0
            assert exc_info.value.decision_code == "PREVIOUSLY_REJECTED"
        finally:
            policy.max_transaction_amount = original_limit
            db_session.commit()

    def test_18_rejected_transaction_cannot_be_retried(self, db_session, test_seed_data):
        """Test 18: A REJECTED transaction CANNOT be retried via retry_payment.
        Provider is NOT called on retry attempt of a rejected transaction."""
        agent = test_seed_data["agent"]
        wallet = test_seed_data["wallet"]

        rejected_tx = Transaction(
            id=uuid.uuid4(),
            idempotency_key=f"sec_rej_retry_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
            wallet_id=wallet.id,
            merchant_name="Crypto Exchange",
            category="crypto",
            amount=500.0,
            status=TransactionStatus.REJECTED.value,
            decision_reason="Category 'crypto' is blocked by policy.",
        )
        db_session.add(rejected_tx)
        db_session.commit()

        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        with pytest.raises(InvalidPaymentStateError, match="REJECTED by policy"):
            service.retry_payment(db_session, payment_id=rejected_tx.id)

        # Provider absolutely must NOT be called
        assert provider.call_count == 0
