import os
import sys
import uuid
from datetime import datetime, timezone

backend_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from sqlalchemy import select
from app.database import SessionLocal, engine
from app.models.base import Base
from app.models.user import User
from app.models.agent import Agent
from app.models.wallet import Wallet
from app.models.policy import Policy
from app.models.merchant import Merchant
from app.models.payment_method import PaymentMethod
from app.models.transaction import (
    Transaction,
    TransactionStatus,
    InvalidPaymentStateError,
    MaxRetriesExceededError,
)
from app.models.payment_attempt import PaymentAttempt
from app.models.audit_log import AuditLog
from app.services.payment_adapter import (
    MockPaymentProvider,
    MockPaymentMode,
)
from app.services.payment_service import (
    PaymentService,
    PolicyViolationError,
    MAX_RETRIES,
)
from app.services.wallet_service import WalletService


def run_day3_live_verification():
    print("=" * 80)
    print("🚀 RUNNING AGENTPAY DAY 3 PHASE 2 LIVE COMPREHENSIVE END-TO-END VERIFICATION")
    print("=" * 80)

    Base.metadata.create_all(bind=engine)
    from scripts.seed import seed_database
    db = SessionLocal()
    seed_database(db)

    try:
        user = db.execute(select(User).where(User.email == "krisha@agentpay.local")).scalar_one()
        agent = db.execute(select(Agent).where(Agent.user_id == user.id)).scalar_one()
        wallet = db.execute(select(Wallet).where(Wallet.agent_id == agent.id)).scalar_one()
        policy = db.execute(select(Policy).where(Policy.agent_id == agent.id)).scalar_one()

        primary_pm = db.execute(
            select(PaymentMethod).where(PaymentMethod.wallet_id == wallet.id, PaymentMethod.is_primary == True)
        ).scalar_one()
        fallback_pm = db.execute(
            select(PaymentMethod).where(PaymentMethod.wallet_id == wallet.id, PaymentMethod.is_primary == False)
        ).scalar_one()

        # =========================================================================
        # SCENARIO A: FALLBACK SUCCESS
        # =========================================================================
        print("\n" + "─" * 80)
        print("📌 SCENARIO A: DETERMINISTIC PRIMARY UPI FAILURE → FALLBACK CARD SUCCESS")
        print("─" * 80)
        provider_a = MockPaymentProvider(
            mode_sequence=[MockPaymentMode.DECLINED, MockPaymentMode.SUCCESS]
        )
        service_a = PaymentService(provider=provider_a)

        key_a = f"verif_scen_a_{uuid.uuid4().hex[:8]}"
        res_a1 = service_a.process_payment(
            db,
            merchant_name="Torrent Power",
            amount=1240.0,
            category="utilities",
            idempotency_key=key_a,
            agent_id=agent.id,
        )
        assert res_a1["success"] is False
        assert res_a1["status"] == "FAILED"
        payment_id_a = uuid.UUID(res_a1["payment_id"])
        print(f"   ✓ Primary UPI Attempt #1: FAILED (DECLINED)")

        res_a2 = service_a.execute_fallback_payment(
            db,
            payment_id=payment_id_a,
            fallback_method_id=fallback_pm.id,
        )
        assert res_a2["success"] is True
        assert res_a2["status"] == "SUCCESS"
        assert res_a2["attempt_number"] == 2
        assert provider_a.call_count == 2
        print(f"   ✓ Fallback Card Attempt #2: SUCCESS (CARD_TOKEN)")

        tx_a = db.get(Transaction, payment_id_a)
        assert tx_a.status == "SUCCESS"
        assert tx_a.payment_method_id == fallback_pm.id

        attempts_a = db.execute(
            select(PaymentAttempt)
            .where(PaymentAttempt.transaction_id == payment_id_a)
            .order_by(PaymentAttempt.attempt_number.asc())
        ).scalars().all()
        assert len(attempts_a) == 2
        assert attempts_a[0].status == "FAILED" and attempts_a[0].error_code == "DECLINED"
        assert attempts_a[1].status == "SUCCESS" and attempts_a[1].error_code is None
        print(f"   ✓ Exactly 1 Transaction ({tx_a.status}), exactly 2 PaymentAttempts persisted in DB")
        print(f"   ✓ Provider call count = {provider_a.call_count}")

        # =========================================================================
        # SCENARIO B: FALLBACK POLICY REJECTED
        # =========================================================================
        print("\n" + "─" * 80)
        print("📌 SCENARIO B: FALLBACK CANDIDATE REJECTED BY POLICY ENGINE")
        print("─" * 80)
        provider_b = MockPaymentProvider(mode=MockPaymentMode.NETWORK_ERROR)
        service_b = PaymentService(provider=provider_b)

        key_b = f"verif_scen_b_{uuid.uuid4().hex[:8]}"
        res_b1 = service_b.process_payment(
            db,
            merchant_name="Amazon",
            amount=899.0,
            category="shopping",
            idempotency_key=key_b,
            agent_id=agent.id,
        )
        payment_id_b = uuid.UUID(res_b1["payment_id"])
        print(f"   ✓ Primary UPI Attempt #1: FAILED (NETWORK_ERROR)")

        # Temporarily restrict policy
        orig_daily_limit = policy.daily_spending_limit
        policy.daily_spending_limit = 200.0  # Limit ₹200 < Tx ₹899
        db.commit()

        try:
            service_b.execute_fallback_payment(db, payment_id=payment_id_b, fallback_method_id=fallback_pm.id)
            assert False, "Expected PolicyViolationError"
        except PolicyViolationError as pve:
            print(f"   ✓ Fallback Policy Engine Rejection: {pve.reason}")
        finally:
            policy.daily_spending_limit = orig_daily_limit
            db.commit()

        assert provider_b.call_count == 1
        tx_b = db.get(Transaction, payment_id_b)
        assert tx_b.status == "FAILED"
        attempts_b = db.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == payment_id_b)
        ).scalars().all()
        assert len(attempts_b) == 1
        print(f"   ✓ Zero fallback provider executions; PaymentAttempts in DB = 1; Final status = FAILED")

        # =========================================================================
        # SCENARIO C: RETRY LIMIT (MAX_RETRIES = 1)
        # =========================================================================
        print("\n" + "─" * 80)
        print("📌 SCENARIO C: AUTHORITATIVE RETRY LIMIT (MAX_RETRIES = 1)")
        print("─" * 80)
        provider_c = MockPaymentProvider(
            mode_sequence=[MockPaymentMode.TIMEOUT, MockPaymentMode.DECLINED]
        )
        service_c = PaymentService(provider=provider_c)

        key_c = f"verif_scen_c_{uuid.uuid4().hex[:8]}"
        res_c1 = service_c.process_payment(
            db,
            merchant_name="Spotify",
            amount=699.0,
            category="subscriptions",
            idempotency_key=key_c,
            agent_id=agent.id,
        )
        payment_id_c = uuid.UUID(res_c1["payment_id"])

        res_c2 = service_c.retry_payment(db, payment_id=payment_id_c)
        assert res_c2["status"] == "FAILED"
        assert provider_c.call_count == 2
        print(f"   ✓ Attempt #1 (TIMEOUT) and Attempt #2 (DECLINED) executed")

        # Attempt #3 is rejected
        try:
            service_c.retry_payment(db, payment_id=payment_id_c)
            assert False, "Expected MaxRetriesExceededError"
        except MaxRetriesExceededError as mre:
            print(f"   ✓ Attempt #3 strictly blocked: {mre}")

        assert provider_c.call_count == 2
        attempts_c = db.execute(
            select(PaymentAttempt).where(PaymentAttempt.transaction_id == payment_id_c)
        ).scalars().all()
        assert len(attempts_c) == 2
        print(f"   ✓ MAX_RETRIES = {MAX_RETRIES} enforced; 3rd attempt impossible")

        # =========================================================================
        # SCENARIO D: IDEMPOTENCY HARDENING
        # =========================================================================
        print("\n" + "─" * 80)
        print("📌 SCENARIO D: IDEMPOTENCY ACROSS PRE-EXECUTION, SUCCESS, AND FALLBACK")
        print("─" * 80)
        provider_d = MockPaymentProvider(mode=MockPaymentMode.SUCCESS)
        service_d = PaymentService(provider=provider_d)

        key_d = f"verif_scen_d_{uuid.uuid4().hex[:8]}"
        res_d1 = service_d.process_payment(
            db,
            merchant_name="MakeMyTrip",
            amount=500.0,
            category="travel",
            idempotency_key=key_d,
            agent_id=agent.id,
        )
        assert res_d1["success"] is True
        calls_before_replay = provider_d.call_count

        # Replay duplicate request
        res_d2 = service_d.process_payment(
            db,
            merchant_name="MakeMyTrip",
            amount=500.0,
            category="travel",
            idempotency_key=key_d,
            agent_id=agent.id,
        )
        assert res_d2["success"] is True
        assert res_d2["payment_id"] == res_d1["payment_id"]
        assert provider_d.call_count == calls_before_replay

        tx_count_d = db.execute(
            select(Transaction).where(Transaction.idempotency_key == key_d)
        ).scalars().all()
        assert len(tx_count_d) == 1
        print(f"   ✓ Duplicate request returned existing SUCCESS transaction without re-execution")
        print(f"   ✓ Exactly 1 Transaction row; Provider calls on replay = 0")

        # =========================================================================
        # SCENARIO E: WALLET DAILY SPENDING DATABASE CALCULATION
        # =========================================================================
        print("\n" + "─" * 80)
        print("📌 SCENARIO E: WALLET DAILY SPENDING CALCULATED FROM PERSISTED DB")
        print("─" * 80)
        current_spent = WalletService.get_current_daily_spent(db, wallet.id)
        print(f"   ✓ Persisted UTC Daily Spent calculated from DB: ₹{current_spent:,.2f}")
        eval_test = WalletService.evaluate_and_audit(
            db,
            merchant_name="Netflix",
            amount=499.0,
            category="subscriptions",
            agent_id=agent.id,
        )
        print(f"   ✓ Evaluation projected spend checked against limit ₹{wallet.daily_spending_limit:,.2f}")
        print(f"   ✓ Remaining Daily Budget: ₹{eval_test['remaining_daily_budget']:,.2f}")

        # =========================================================================
        # SCENARIO F: SECURITY BOUNDARIES
        # =========================================================================
        print("\n" + "─" * 80)
        print("📌 SCENARIO F: SECURITY BOUNDARIES & ILLEGAL TRANSITIONS")
        print("─" * 80)
        # 1. State machine direct illegal transition
        tx_test = Transaction(
            id=uuid.uuid4(),
            idempotency_key=f"test_state_{uuid.uuid4().hex[:8]}",
            agent_id=agent.id,
            wallet_id=wallet.id,
            merchant_name="Test",
            category="utilities",
            amount=100.0,
            status=TransactionStatus.SUCCESS.value,
        )
        try:
            tx_test.transition_to(TransactionStatus.PAYMENT_PENDING)
            assert False, "Expected InvalidPaymentStateError"
        except InvalidPaymentStateError:
            print(f"   ✓ Arbitrary state mutation from terminal SUCCESS blocked")

        print("\n" + "=" * 80)
        print("🎉 ALL DAY 3 PHASE 2 VERIFICATION SCENARIOS PASSED PERFECTLY!")
        print("=" * 80 + "\n")

    finally:
        db.close()


if __name__ == "__main__":
    run_day3_live_verification()
