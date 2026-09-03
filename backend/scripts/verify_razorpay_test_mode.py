"""
AgentPay — Razorpay Test Mode Live Verification Script
scripts/verify_razorpay_test_mode.py

Purpose:
  Verify that the Razorpay Test Mode payment provider is fully integrated with
  AgentPay's PaymentService, Policy Engine, audit trail, and database persistence.

Usage:
  # From backend/ directory:
  python scripts/verify_razorpay_test_mode.py

Environment variables required for live test:
  RAZORPAY_KEY_ID=rzp_test_XXXXXXXXXXXXXXXX
  RAZORPAY_KEY_SECRET=XXXXXXXXXXXXXXXXXXXXXXXX
  PAYMENT_PROVIDER=RAZORPAY

If these are not configured, the script reports NOT CONFIGURED and exits cleanly.

IMPORTANT:
  - This script NEVER fakes a PASS if credentials are unavailable.
  - This script NEVER exposes API keys in console output or logs.
  - All payments go through the Policy Engine before provider dispatch.
  - Razorpay Test Mode only — no real money is moved.
"""
import os
import sys
import uuid
import json
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
from app.models.transaction import Transaction, TransactionStatus
from app.models.payment_attempt import PaymentAttempt
from app.models.audit_log import AuditLog
from app.services.payment_adapter import (
    RazorpayPaymentProvider,
    MockPaymentProvider,
    MockPaymentMode,
    get_payment_provider,
)
from app.services.payment_service import PaymentService, PolicyViolationError
from app.services.wallet_service import WalletService
from app.config import get_settings


SEPARATOR = "─" * 60
PASS_MARK = "  ✅ PASS"
FAIL_MARK = "  ❌ FAIL"
SKIP_MARK = "  ⚠️  SKIP"
INFO_MARK = "  ℹ️ "


def mask_key(key: str) -> str:
    """Safely mask a key for display — never show more than 4 chars."""
    if not key:
        return "(empty)"
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


def check_configuration() -> dict:
    """Check environment variables and return configuration status."""
    settings = get_settings()
    key_id = str(getattr(settings, "razorpay_key_id", "") or "").strip()
    key_secret = str(getattr(settings, "razorpay_key_secret", "") or "").strip()
    provider_type = str(getattr(settings, "payment_provider", "MOCK") or "MOCK").upper()

    is_test_key = key_id.startswith("rzp_test_")
    is_live_key = key_id.startswith("rzp_live_")
    configured = bool(key_id and key_secret and provider_type == "RAZORPAY")

    return {
        "key_id": key_id,
        "key_secret": key_secret,
        "provider_type": provider_type,
        "configured": configured,
        "is_test_key": is_test_key,
        "is_live_key": is_live_key,
    }


def run_verification():
    print("\n" + "=" * 60)
    print("  AgentPay — Razorpay Test Mode Verification")
    print("=" * 60)
    print(f"  Run timestamp: {datetime.now(timezone.utc).isoformat()}")
    print()

    results = {}

    # ─── CHECK 1: Configuration ───────────────────────────────────────────────
    print(SEPARATOR)
    print("  [1] Configuration")
    print(SEPARATOR)

    cfg = check_configuration()
    key_id = cfg["key_id"]
    key_secret = cfg["key_secret"]

    print(f"  PAYMENT_PROVIDER : {cfg['provider_type']}")
    print(f"  RAZORPAY_KEY_ID  : {mask_key(key_id)}")
    print(f"  RAZORPAY_KEY_SECRET: {mask_key(key_secret)}")
    print(f"  Is Test Key      : {cfg['is_test_key']}")

    if cfg["is_live_key"]:
        print(f"{FAIL_MARK} — LIVE key detected! This script only supports TEST MODE keys.")
        print("  Set RAZORPAY_KEY_ID to a key starting with 'rzp_test_'.")
        results["configuration"] = "FAIL — LIVE KEY DETECTED"
        _print_summary(results, configured=False)
        sys.exit(1)

    if not cfg["configured"]:
        results["configuration"] = "NOT CONFIGURED"
        print(f"{SKIP_MARK} — Razorpay Test Mode credentials not found.")
        print(f"  Set RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, and PAYMENT_PROVIDER=RAZORPAY")
        _print_summary(results, configured=False)
        return

    results["configuration"] = "PASS"
    print(PASS_MARK)

    # ─── CHECK 2: Provider initialization ────────────────────────────────────
    print()
    print(SEPARATOR)
    print("  [2] Provider Initialization")
    print(SEPARATOR)
    try:
        provider = RazorpayPaymentProvider(key_id=key_id, key_secret=key_secret)
        assert isinstance(provider, RazorpayPaymentProvider)
        results["provider_init"] = "PASS"
        print(PASS_MARK)
    except Exception as e:
        results["provider_init"] = f"FAIL — {e}"
        print(f"{FAIL_MARK} — {e}")
        _print_summary(results, configured=True)
        sys.exit(1)

    # ─── SETUP: Database and demo data ───────────────────────────────────────
    print()
    print(SEPARATOR)
    print("  [3] Database Setup")
    print(SEPARATOR)
    try:
        Base.metadata.create_all(bind=engine)
        from scripts.seed import seed_database
        db = SessionLocal()
        seed_database(db)

        user = db.execute(select(User).where(User.email == "krisha@agentpay.local")).scalar_one()
        agent = db.execute(select(Agent).where(Agent.user_id == user.id)).scalar_one()
        wallet = db.execute(select(Wallet).where(Wallet.agent_id == agent.id)).scalar_one()
        policy = db.execute(select(Policy).where(Policy.agent_id == agent.id)).scalar_one()

        # Ensure daily spending limit has headroom above today's accumulated test runs
        current_spent = WalletService.get_current_daily_spent(db, wallet.id)
        if policy.daily_spending_limit <= current_spent + 1500.0:
            wallet.daily_spending_limit = current_spent + 10000.0
            policy.daily_spending_limit = current_spent + 10000.0
            db.commit()

        results["database_setup"] = "PASS"
        print(PASS_MARK)
    except Exception as e:
        results["database_setup"] = f"FAIL — {e}"
        print(f"{FAIL_MARK} — {e}")
        _print_summary(results, configured=True)
        sys.exit(1)

    try:
        # ─── CHECK 4: AgentPay Policy Check ──────────────────────────────────
        print()
        print(SEPARATOR)
        print("  [4] AgentPay Policy Check (Deterministic)")
        print(SEPARATOR)
        try:
            eval_result = WalletService.evaluate_and_audit(
                db,
                merchant_name="Torrent Power",
                amount=1240.0,
                category="utilities",
                agent_id=agent.id,
                idempotency_key=f"rzp_verify_{uuid.uuid4().hex[:8]}",
            )
            assert eval_result["approved"] is True, f"Policy rejected: {eval_result['reason']}"
            results["policy_check"] = "PASS"
            print(f"{PASS_MARK} — {eval_result['reason'][:80]}")
        except AssertionError as e:
            results["policy_check"] = f"FAIL — {e}"
            print(f"{FAIL_MARK} — {e}")

        # ─── CHECK 5: PaymentService dispatch via Razorpay ───────────────────
        print()
        print(SEPARATOR)
        print("  [5] PaymentService → Razorpay API Dispatch")
        print(SEPARATOR)
        print(f"{INFO_MARK} Sending ₹1,240 payment to Razorpay Test Mode API...")
        print(f"{INFO_MARK} Merchant: Torrent Power | Category: utilities")

        service = PaymentService(provider=provider)
        idempotency_key = f"rzp_live_verify_{uuid.uuid4().hex[:8]}"

        try:
            result = service.process_payment(
                db,
                merchant_name="Torrent Power",
                amount=1240.0,
                category="utilities",
                idempotency_key=idempotency_key,
                agent_id=agent.id,
            )

            if result["success"]:
                results["payment_dispatch"] = "PASS"
                provider_payment_id = result.get("provider_payment_id", "N/A")
                # Mask provider_payment_id if it looks sensitive (it shouldn't, but just in case)
                print(f"{PASS_MARK} — Status: {result['status']}")
                print(f"  Provider Payment ID : {provider_payment_id}")
            else:
                results["payment_dispatch"] = f"FAIL — {result.get('failure_reason')} | {result.get('error_message')}"
                print(f"{FAIL_MARK} — {result.get('failure_reason')}: {result.get('error_message')}")

        except PolicyViolationError as pve:
            results["payment_dispatch"] = f"FAIL — Policy: {pve.reason}"
            print(f"{FAIL_MARK} — Policy rejected: {pve.reason}")
        except Exception as e:
            results["payment_dispatch"] = f"FAIL — {e}"
            print(f"{FAIL_MARK} — {e}")

        # ─── CHECK 6: PaymentAttempt persistence ─────────────────────────────
        print()
        print(SEPARATOR)
        print("  [6] PaymentAttempt Persistence")
        print(SEPARATOR)
        try:
            if "payment_id" in (result if "result" in dir() else {}):
                payment_id = uuid.UUID(result["payment_id"])
                attempts = db.execute(
                    select(PaymentAttempt)
                    .where(PaymentAttempt.transaction_id == payment_id)
                ).scalars().all()
                assert len(attempts) >= 1, "No PaymentAttempt persisted"
                att = attempts[0]
                assert att.attempt_number == 1
                assert att.provider_payment_id is not None
                results["attempt_persistence"] = "PASS"
                print(f"{PASS_MARK} — {len(attempts)} attempt(s) persisted, attempt_number={att.attempt_number}")
            else:
                results["attempt_persistence"] = "SKIP — payment did not complete"
                print(f"{SKIP_MARK} — Payment did not complete, skipping persistence check")
        except Exception as e:
            results["attempt_persistence"] = f"FAIL — {e}"
            print(f"{FAIL_MARK} — {e}")

        # ─── CHECK 7: Audit logging ───────────────────────────────────────────
        print()
        print(SEPARATOR)
        print("  [7] Audit Trail")
        print(SEPARATOR)
        try:
            audit_logs = db.execute(
                select(AuditLog)
                .where(AuditLog.agent_id == agent.id)
                .order_by(AuditLog.created_at.desc())
            ).scalars().all()

            event_types = [log.event_type for log in audit_logs[:20]]
            has_policy_eval = any("POLICY" in e for e in event_types)
            has_payment_result = any("PAYMENT_RESULT" in e for e in event_types)

            if has_policy_eval and has_payment_result:
                results["audit_trail"] = "PASS"
                print(f"{PASS_MARK} — {len(audit_logs)} total audit events. Types: {list(set(event_types[:10]))}")
            else:
                results["audit_trail"] = "PARTIAL — missing event types"
                print(f"{SKIP_MARK} — Events found: {list(set(event_types[:10]))}")

            # Verify secret not in audit log metadata
            for log in audit_logs[:5]:
                meta_str = json.dumps(log.metadata_payload or {}, default=str)
                assert key_secret not in meta_str, "Secret leaked in AuditLog!"
            print(f"  Secret key: NOT in any of {min(5, len(audit_logs))} audit log entries ✓")
        except Exception as e:
            results["audit_trail"] = f"FAIL — {e}"
            print(f"{FAIL_MARK} — {e}")

    finally:
        db.close()

    _print_summary(results, configured=True)


def _print_summary(results: dict, configured: bool):
    print()
    print("=" * 60)
    print("  SUMMARY")
    print("=" * 60)

    for check, status in results.items():
        icon = "✅" if status == "PASS" else ("⚠️ " if "NOT CONFIGURED" in str(status) or "SKIP" in str(status) else "❌")
        print(f"  {icon} {check.replace('_', ' ').title():<28} {status}")

    print()
    if not configured or results.get("configuration") == "NOT CONFIGURED":
        print("  RESULT: ⚠️  NOT VERIFIED — Razorpay Test Mode credentials not configured")
        print()
        print("  To enable live Razorpay Test Mode verification:")
        print("    1. Set RAZORPAY_KEY_ID=rzp_test_XXXX in .env")
        print("    2. Set RAZORPAY_KEY_SECRET=XXXX in .env")
        print("    3. Set PAYMENT_PROVIDER=RAZORPAY in .env")
        print("    4. Re-run this script")
    elif all(v == "PASS" for v in results.values() if v not in ("SKIP", "NOT CONFIGURED")):
        print("  RESULT: ✅ RAZORPAY TEST MODE VERIFIED")
    else:
        print("  RESULT: ❌ RAZORPAY TEST MODE VERIFICATION FAILED")
        failed = [k for k, v in results.items() if "FAIL" in str(v)]
        print(f"  Failed checks: {failed}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    run_verification()
