"""
Day 3 Phase 2 Step 4: Wallet Daily Spending Database Calculation & Verification Tests.
Verifies that:
1. Wallet spending limits are calculated directly from persisted database Transaction records.
2. In-memory counters or audit logs are not used as the financial source of truth.
3. Only successful/completed payments (status='SUCCESS') count towards daily spent.
4. Failed, pending, and rejected payment attempts do NOT increase wallet spent totals.
5. Exact scenario:
   - Daily limit = ₹5,000
   - Existing SUCCESS txs: ₹1,000 + ₹1,500 = ₹2,500
   - New tx = ₹1,240 -> Projected ₹3,740 -> Policy APPROVED (Remaining: ₹1,260).
   - Rejection case: Existing SUCCESS = ₹4,000 + New ₹1,240 -> Projected ₹5,240 -> REJECTED.
6. Recalculation after new successful payment immediately reflects in PostgreSQL queries.
"""
import uuid
from datetime import datetime, timezone, timedelta
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


class TestWalletDailySpendingCalculation:
    """Test suite for database-backed daily spending calculation and policy integration."""

    def test_1_database_spending_calculation_with_existing_transactions(self, db_session, test_seed_data):
        """
        Scenario 1:
        - Wallet daily limit = ₹5,000
        - Existing successful transactions today: ₹1,000 and ₹1,500
        - Current transaction = ₹1,240
        - Expected calculated spending before current transaction = ₹2,500
        - Expected projected spending = ₹3,740
        - Policy evaluates and APPROVES (remaining budget: ₹1,260).
        """
        wallet: Wallet = test_seed_data["wallet"]
        agent: Agent = test_seed_data["agent"]
        policy: Policy = test_seed_data["policy"]

        # Ensure wallet and policy daily limit = ₹5,000
        wallet.daily_spending_limit = 5000.0
        wallet.per_transaction_limit = 5000.0
        policy.daily_spending_limit = 5000.0
        policy.max_transaction_amount = 5000.0
        db_session.commit()

        # Seed Tx 1: ₹1,000 SUCCESS
        tx1 = Transaction(
            id=uuid.uuid4(),
            idempotency_key=f"db_spent_tx1_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
            wallet_id=wallet.id,
            merchant_name="Torrent Power",
            category="utilities",
            amount=1000.0,
            currency="INR",
            status="SUCCESS",
            created_at=datetime.now(timezone.utc),
        )
        # Seed Tx 2: ₹1,500 SUCCESS
        tx2 = Transaction(
            id=uuid.uuid4(),
            idempotency_key=f"db_spent_tx2_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
            wallet_id=wallet.id,
            merchant_name="Netflix",
            category="subscriptions",
            amount=1500.0,
            currency="INR",
            status="SUCCESS",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add_all([tx1, tx2])
        db_session.commit()

        # 1. Verify calculated spending before current transaction = ₹2,500
        spent_before = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert spent_before == 2500.0

        # 2. Evaluate ₹1,240 transaction
        eval_result = WalletService.evaluate_and_audit(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            agent_id=agent.id,
        )

        assert eval_result["approved"] is True
        assert eval_result["decision_code"] == "APPROVED"
        assert eval_result["current_daily_spent"] == 2500.0
        # Projected spending: ₹2,500 + ₹1,240 = ₹3,740. Remaining daily budget = ₹5,000 - ₹3,740 = ₹1,260
        assert eval_result["remaining_daily_budget"] == 1260.0

    def test_2_rejection_when_projected_spending_exceeds_daily_limit(self, db_session, test_seed_data):
        """
        Scenario 2:
        - Wallet daily limit = ₹5,000
        - Existing successful spending = ₹4,000
        - New transaction = ₹1,240
        - Projected spending = ₹5,240
        - Policy must REJECT with DAILY_LIMIT_EXCEEDED.
        """
        wallet: Wallet = test_seed_data["wallet"]
        agent: Agent = test_seed_data["agent"]
        policy: Policy = test_seed_data["policy"]

        wallet.daily_spending_limit = 5000.0
        policy.daily_spending_limit = 5000.0
        db_session.commit()

        # Seed existing SUCCESS transactions totaling ₹4,000
        tx_existing = Transaction(
            id=uuid.uuid4(),
            idempotency_key=f"db_spent_tx4k_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
            wallet_id=wallet.id,
            merchant_name="MakeMyTrip",
            category="travel",
            amount=4000.0,
            currency="INR",
            status="SUCCESS",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(tx_existing)
        db_session.commit()

        # Verify initial spending is ₹4,000
        spent_before = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert spent_before == 4000.0

        # Attempt to process payment of ₹1,240 -> Projected ₹5,240 > ₹5,000 limit
        service = PaymentService()
        with pytest.raises(PolicyViolationError) as exc_info:
            service.process_payment(
                db_session,
                merchant_name="Torrent Power",
                amount=1240.0,
                category="utilities",
                agent_id=agent.id,
            )

        assert exc_info.value.decision_code in ["DAILY_LIMIT_EXCEEDED", "MULTIPLE_POLICY_VIOLATIONS"]
        assert "daily spending limit exceeded" in str(exc_info.value).lower()
        assert "1,240" in str(exc_info.value)
        assert "1,000" in str(exc_info.value)

    def test_3_failed_and_pending_transactions_do_not_increase_spent(self, db_session, test_seed_data):
        """
        Scenario 3:
        - Failed payment attempts, pending requests, and rejected transactions
          must NOT increment wallet daily spent.
        """
        wallet: Wallet = test_seed_data["wallet"]
        agent: Agent = test_seed_data["agent"]

        # 1. Add ₹1,000 SUCCESS
        tx_success = Transaction(
            id=uuid.uuid4(),
            idempotency_key=f"tx_succ_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
            wallet_id=wallet.id,
            merchant_name="Netflix",
            category="subscriptions",
            amount=1000.0,
            currency="INR",
            status="SUCCESS",
        )
        # 2. Add ₹2,500 FAILED
        tx_failed = Transaction(
            id=uuid.uuid4(),
            idempotency_key=f"tx_fail_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
            wallet_id=wallet.id,
            merchant_name="MakeMyTrip",
            category="travel",
            amount=2500.0,
            currency="INR",
            status="FAILED",
        )
        # 3. Add ₹1,200 PAYMENT_PENDING
        tx_pending = Transaction(
            id=uuid.uuid4(),
            idempotency_key=f"tx_pend_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
            wallet_id=wallet.id,
            merchant_name="Spotify",
            category="subscriptions",
            amount=1200.0,
            currency="INR",
            status="PAYMENT_PENDING",
        )
        # 4. Add ₹3,000 REJECTED
        tx_rejected = Transaction(
            id=uuid.uuid4(),
            idempotency_key=f"tx_rej_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
            wallet_id=wallet.id,
            merchant_name="Crypto Exchange",
            category="crypto",
            amount=3000.0,
            currency="INR",
            status="REJECTED",
        )

        db_session.add_all([tx_success, tx_failed, tx_pending, tx_rejected])
        db_session.commit()

        # Spent must only equal the ₹1,000 from SUCCESS transaction
        total_spent = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert total_spent == 1000.0

    def test_4_spending_recalculated_immediately_after_successful_payment(self, db_session, test_seed_data):
        """
        Scenario 4:
        - Confirm that after a payment succeeds and is committed as SUCCESS,
          subsequent database calculations immediately include the new amount.
        """
        wallet: Wallet = test_seed_data["wallet"]
        agent: Agent = test_seed_data["agent"]

        # Initial spent = 0.0
        initial_spent = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert initial_spent == 0.0

        # Execute successful payment of ₹1,240
        provider = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service = PaymentService(provider=provider)

        res = service.process_payment(
            db_session,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            agent_id=agent.id,
        )
        assert res["success"] is True
        assert res["status"] == "SUCCESS"

        # Recalculate directly from PostgreSQL
        updated_spent = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert updated_spent == 1240.0

        # Execute another successful payment of ₹699
        res2 = service.process_payment(
            db_session,
            merchant_name="Spotify",
            amount=699.0,
            category="subscriptions",
            agent_id=agent.id,
        )
        assert res2["success"] is True

        # Total spent now = ₹1,240 + ₹699 = ₹1,939
        final_spent = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert final_spent == 1939.0

    def test_5_spending_ignores_transactions_from_previous_days(self, db_session, test_seed_data):
        """
        Scenario 5:
        - Transactions from yesterday or past days must NOT count toward today's daily limit.
        """
        wallet: Wallet = test_seed_data["wallet"]
        agent: Agent = test_seed_data["agent"]

        yesterday = datetime.now(timezone.utc) - timedelta(days=1)

        # Yesterday's ₹4,000 SUCCESS transaction
        tx_yesterday = Transaction(
            id=uuid.uuid4(),
            idempotency_key=f"tx_yest_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
            wallet_id=wallet.id,
            merchant_name="MakeMyTrip",
            category="travel",
            amount=4000.0,
            currency="INR",
            status="SUCCESS",
            created_at=yesterday,
        )
        # Today's ₹500 SUCCESS transaction
        tx_today = Transaction(
            id=uuid.uuid4(),
            idempotency_key=f"tx_tod_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
            wallet_id=wallet.id,
            merchant_name="Netflix",
            category="subscriptions",
            amount=500.0,
            currency="INR",
            status="SUCCESS",
            created_at=datetime.now(timezone.utc),
        )

        db_session.add_all([tx_yesterday, tx_today])
        db_session.commit()

        # Only today's ₹500 should be counted
        today_spent = WalletService.get_current_daily_spent(db_session, wallet.id)
        assert today_spent == 500.0
