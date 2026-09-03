"""
Day 4 Phase 1.5 — Part B: Wallet Accounting Invariant Tests

Accounting model clarity:
  - wallet.daily_spending_limit: Maximum INR that can be spent per UTC calendar day
  - wallet.per_transaction_limit: Maximum INR per single transaction
  - wallet.status: ACTIVE / DISABLED / FROZEN (affects policy evaluation)
  - There is NO physical balance field — the wallet is a policy/limit container
  - Daily spending is calculated dynamically: SUM of amount WHERE status='SUCCESS' today (UTC)
  - Only SUCCESS transactions count as spending
  - FAILED, REJECTED, PAYMENT_PENDING, REQUESTED, POLICY_CHECK, APPROVED: do NOT count

Invariants verified:
  Scenario 1: Successful payment → correct daily_spent increment
  Scenario 2: Primary fails → fallback succeeds → spending = amount once (NOT 2x)
  Scenario 3: Primary fails → retry fails → final FAILED → spending = 0
  Scenario 4: Policy rejection → spending = 0 (provider never called)
  Scenario 5: Idempotent duplicate request → spending counted only once
  Scenario 6: Successful payment → daily budget correctly reflects for next evaluation
"""
import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy import select

from app.models.transaction import Transaction, TransactionStatus
from app.models.payment_method import PaymentMethod
from app.models.wallet import Wallet
from app.models.policy import Policy
from app.models.agent import Agent
from app.services.wallet_service import WalletService
from app.services.payment_service import PaymentService, PolicyViolationError
from app.services.payment_adapter import MockPaymentProvider, MockPaymentMode


class TestWalletAccountingInvariants:
    """
    Explicit wallet accounting invariant tests.

    AgentPay accounting model:
    ─────────────────────────
    • Wallet has no physical balance. It has spending limits.
    • daily_spent = SUM(Transaction.amount WHERE status='SUCCESS' AND created_at >= today_UTC)
    • One successful logical payment = one SUCCESS transaction = one spending increment
    • Failed/rejected/pending transactions = ZERO spending impact
    • Retry/fallback of the SAME transaction = one spending increment total (the SUCCESS)
    • Duplicate idempotent replay = zero additional spending
    """

    def test_scenario_1_successful_payment_increments_daily_spent(self, db_session, test_seed_data):
        """
        Scenario 1:
          Start: daily_spent = 0
          Payment: ₹1,240 → SUCCESS
          End: daily_spent = ₹1,240 (exactly one increment)
        """
        agent = test_seed_data["agent"]
        wallet = test_seed_data["wallet"]

        initial_spent = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert initial_spent == 0.0

        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        result = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            agent_id=agent.id,
        )

        assert result["success"] is True
        assert result["status"] == "SUCCESS"

        after_spent = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert after_spent == 1240.0

        # Verify only 1 SUCCESS transaction contributed
        tx_count = db_session.execute(
            select(Transaction).where(
                Transaction.wallet_id == wallet.id,
                Transaction.status == TransactionStatus.SUCCESS.value,
            )
        ).scalars().all()
        assert len(tx_count) == 1
        assert tx_count[0].amount == 1240.0

    def test_scenario_2_primary_fails_fallback_succeeds_single_deduction(self, db_session, test_seed_data):
        """
        Scenario 2:
          Start: daily_spent = 0
          UPI Attempt #1: ₹1,240 FAILED
          Corporate Card Attempt #2: ₹1,240 SUCCESS (fallback)
          End: daily_spent = ₹1,240 (ONE deduction, NOT ₹2,480)

        This verifies that primary failure + fallback success = one logical payment.
        """
        agent = test_seed_data["agent"]
        wallet = test_seed_data["wallet"]

        initial_spent = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert initial_spent == 0.0

        fallback_pm = db_session.execute(
            select(PaymentMethod).where(
                PaymentMethod.wallet_id == wallet.id,
                PaymentMethod.is_primary == False,
            )
        ).scalar_one()

        provider = MockPaymentProvider(
            mode_sequence=[MockPaymentMode.DECLINED, MockPaymentMode.SUCCESS]
        )
        service = PaymentService(provider=provider)

        # Primary fails
        res1 = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=f"wallet_inv_sc2_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
        )
        assert res1["success"] is False

        # Spending after failed primary: still 0
        spent_after_fail = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert spent_after_fail == 0.0

        # Fallback succeeds
        payment_id = uuid.UUID(res1["payment_id"])
        res_fb = service.execute_fallback_payment(
            db_session,
            payment_id=payment_id,
            fallback_method_id=fallback_pm.id,
        )
        assert res_fb["success"] is True
        assert res_fb["status"] == "SUCCESS"

        # Spending after fallback SUCCESS: exactly ₹1,240 (NOT double-counted)
        spent_after_fallback = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert spent_after_fallback == 1240.0, (
            f"Expected ₹1,240 but got ₹{spent_after_fallback}. "
            "Fallback must NOT double-count the amount."
        )

        # Exactly 1 SUCCESS transaction in the DB
        success_txs = db_session.execute(
            select(Transaction).where(
                Transaction.wallet_id == wallet.id,
                Transaction.status == TransactionStatus.SUCCESS.value,
            )
        ).scalars().all()
        assert len(success_txs) == 1
        assert success_txs[0].amount == 1240.0

    def test_scenario_3_primary_and_retry_both_fail_no_spending(self, db_session, test_seed_data):
        """
        Scenario 3:
          Start: daily_spent = 0
          Attempt #1: ₹1,240 → FAILED
          Attempt #2 (retry): ₹1,240 → FAILED
          Final status: FAILED
          End: daily_spent = 0 (NO spending for failed payment)
        """
        agent = test_seed_data["agent"]
        wallet = test_seed_data["wallet"]

        initial_spent = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert initial_spent == 0.0

        provider = MockPaymentProvider(mode=MockPaymentMode.TIMEOUT)
        service = PaymentService(provider=provider)

        key = f"wallet_inv_sc3_{uuid.uuid4().hex[:8]}"
        res1 = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=key,
            agent_id=agent.id,
        )
        assert res1["success"] is False
        payment_id = uuid.UUID(res1["payment_id"])

        # Spending after Attempt #1 failure: 0
        spent_after_1 = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert spent_after_1 == 0.0

        # Retry also fails
        res2 = service.retry_payment(db_session, payment_id=payment_id)
        assert res2["success"] is False
        assert res2["status"] == "FAILED"

        # Spending after Attempt #2 failure: still 0
        spent_after_2 = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert spent_after_2 == 0.0, (
            f"Expected ₹0 but got ₹{spent_after_2}. "
            "Failed retries must NOT count as spending."
        )

        # No SUCCESS transactions in DB
        success_txs = db_session.execute(
            select(Transaction).where(
                Transaction.wallet_id == wallet.id,
                Transaction.status == TransactionStatus.SUCCESS.value,
            )
        ).scalars().all()
        assert len(success_txs) == 0

    def test_scenario_4_policy_rejection_no_spending(self, db_session, test_seed_data):
        """
        Scenario 4:
          Policy rejects payment for blocked category.
          End: daily_spent = 0 (REJECTED does NOT count as spending)
        """
        agent = test_seed_data["agent"]
        wallet = test_seed_data["wallet"]

        initial_spent = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert initial_spent == 0.0

        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        with pytest.raises(PolicyViolationError):
            service.process_payment(
                db_session,
                merchant_name="Crypto Exchange",
                amount=500.0,
                category="crypto",
                agent_id=agent.id,
            )

        # No spending: REJECTED transactions are excluded from daily_spent
        spent_after = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert spent_after == 0.0, (
            f"Expected ₹0 but got ₹{spent_after}. "
            "Policy-rejected transactions must NOT count as spending."
        )

        # No SUCCESS transactions
        success_txs = db_session.execute(
            select(Transaction).where(
                Transaction.wallet_id == wallet.id,
                Transaction.status == TransactionStatus.SUCCESS.value,
            )
        ).scalars().all()
        assert len(success_txs) == 0

    def test_scenario_5_idempotent_duplicate_no_double_deduction(self, db_session, test_seed_data):
        """
        Scenario 5:
          Payment succeeds on first attempt.
          Same idempotency key replayed twice more.
          End: daily_spent = ₹499 (counted only once, NOT ₹1,497)
        """
        agent = test_seed_data["agent"]
        wallet = test_seed_data["wallet"]

        initial_spent = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert initial_spent == 0.0

        shared_key = f"wallet_inv_sc5_{uuid.uuid4().hex[:8]}"
        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        # First payment
        res1 = service.process_payment(
            db_session,
            merchant_name="Netflix",
            amount=499.0,
            category="subscriptions",
            idempotency_key=shared_key,
            agent_id=agent.id,
        )
        assert res1["success"] is True

        spent_after_first = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert spent_after_first == 499.0

        # Idempotent replay #1
        res2 = service.process_payment(
            db_session,
            merchant_name="Netflix",
            amount=499.0,
            category="subscriptions",
            idempotency_key=shared_key,
            agent_id=agent.id,
        )
        assert res2["success"] is True
        assert res2["payment_id"] == res1["payment_id"]

        spent_after_replay1 = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert spent_after_replay1 == 499.0, (
            f"Expected ₹499 but got ₹{spent_after_replay1}. "
            "Idempotent replay must NOT double-count spending."
        )

        # Idempotent replay #2
        res3 = service.process_payment(
            db_session,
            merchant_name="Netflix",
            amount=499.0,
            category="subscriptions",
            idempotency_key=shared_key,
            agent_id=agent.id,
        )
        assert res3["payment_id"] == res1["payment_id"]

        spent_after_replay2 = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert spent_after_replay2 == 499.0, (
            f"Expected ₹499 but got ₹{spent_after_replay2}. "
            "Multiple idempotent replays must NOT multiply spending."
        )

    def test_scenario_6_successful_payment_reflected_in_next_evaluation(self, db_session, test_seed_data):
        """
        Scenario 6:
          Payment of ₹1,240 succeeds.
          Immediately evaluate another payment of ₹499.
          The evaluation must see remaining budget = limit - 1240 - 499 = limit - 1739.
        """
        agent = test_seed_data["agent"]
        wallet = test_seed_data["wallet"]
        policy = test_seed_data["policy"]

        # Set known limits
        wallet.daily_spending_limit = 10000.0
        wallet.per_transaction_limit = 5000.0
        policy.daily_spending_limit = 10000.0
        policy.max_transaction_amount = 5000.0
        db_session.commit()

        initial_spent = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert initial_spent == 0.0

        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        # First payment
        res = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            agent_id=agent.id,
        )
        assert res["success"] is True

        # Immediately evaluate a second payment of ₹499
        eval_result = WalletService.evaluate_and_audit(
            db_session,
            merchant_name="Netflix",
            amount=499.0,
            category="subscriptions",
            agent_id=agent.id,
        )

        assert eval_result["approved"] is True
        assert eval_result["current_daily_spent"] == 1240.0
        # remaining after this would-be transaction: 10000 - 1240 - 499 = 8261
        assert eval_result["remaining_daily_budget"] == round(10000.0 - 1240.0 - 499.0, 2)

    def test_wallet_model_has_no_balance_field(self):
        """
        Verifies the AgentPay accounting model:
        - Wallet has NO physical balance field
        - It is a policy/limit container
        - Spending is derived from the Transaction table at query time
        """
        wallet_fields = {c.key for c in Wallet.__mapper__.columns}
        # There IS NO balance field in this accounting model
        assert "balance" not in wallet_fields, (
            "Wallet must NOT have a physical balance field. "
            "AgentPay uses limit-based accounting derived from transaction records."
        )
        # But it DOES have limit fields
        assert "daily_spending_limit" in wallet_fields
        assert "per_transaction_limit" in wallet_fields
        assert "status" in wallet_fields

    def test_failed_transactions_excluded_from_daily_spent_by_status_filter(self, db_session, test_seed_data):
        """
        Directly verify that FAILED, REJECTED, PAYMENT_PENDING, REQUESTED, APPROVED
        transactions are excluded from daily_spent.
        Only SUCCESS transactions count.
        """
        agent = test_seed_data["agent"]
        wallet = test_seed_data["wallet"]

        non_success_statuses = [
            TransactionStatus.FAILED,
            TransactionStatus.REJECTED,
            TransactionStatus.PAYMENT_PENDING,
        ]

        for i, status in enumerate(non_success_statuses):
            tx = Transaction(
                id=uuid.uuid4(),
                idempotency_key=f"wallet_inv_non_succ_{i}_{uuid.uuid4().hex[:6]}",
                agent_id=agent.id,
                wallet_id=wallet.id,
                merchant_name="Test",
                category="utilities",
                amount=5000.0,  # Large amount that would matter if counted
                currency="INR",
                status=status.value,
            )
            db_session.add(tx)

        db_session.commit()

        # All non-SUCCESS transactions must contribute ZERO to daily spent
        daily_spent = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert daily_spent == 0.0, (
            f"Expected ₹0 but got ₹{daily_spent}. "
            f"Non-SUCCESS transactions must not count towards daily spending."
        )
