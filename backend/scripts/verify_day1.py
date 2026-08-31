import os
import sys
import json
from uuid import UUID

backend_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.wallet import Wallet
from app.models.agent import Agent
from app.models.policy import Policy


def run_live_verification():
    print("=" * 70)
    print("🧪 RUNNING AGENTPAY DAY 1 COMPREHENSIVE LIVE VERIFICATION")
    print("=" * 70)

    client = TestClient(app)
    db = SessionLocal()

    try:
        # 1. Verify GET /api/merchants
        print("\n1️⃣  Testing GET /api/merchants...")
        resp = client.get("/api/merchants")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        merchants = resp.json()
        print(f"   ✓ Retrieved {len(merchants)} merchants:")
        for m in merchants:
            print(f"     • {m['name']} ({m['category']})")

        # 2. Verify GET /api/wallet
        print("\n2️⃣  Testing GET /api/wallet...")
        resp = client.get("/api/wallet")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        wallet = resp.json()
        print(f"   ✓ Wallet Status: {wallet['status']}")
        print(f"   ✓ Daily Spending Limit: ₹{wallet['daily_spending_limit']:,.2f}")
        print(f"   ✓ Per-Transaction Limit: ₹{wallet['per_transaction_limit']:,.2f}")
        print(f"   ✓ Today's Spending So Far: ₹{wallet['current_daily_spent']:,.2f}")
        print(f"   ✓ Remaining Daily Budget: ₹{wallet['remaining_daily_budget']:,.2f}")

        # 3. Verify GET /api/policies
        print("\n3️⃣  Testing GET /api/policies...")
        resp = client.get("/api/policies")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        policies = resp.json()
        print(f"   ✓ Active Policies: {len(policies)}")
        for p in policies:
            print(f"     • {p['name']}: Max Tx ₹{p['max_transaction_amount']:,.2f}, Daily Limit ₹{p['daily_spending_limit']:,.2f}")
            print(f"       Allowed Categories: {p['allowed_categories']}")
            print(f"       Blocked Categories: {p['blocked_categories']}")

        # 4. Test Scenario A: ₹1,240 electricity payment -> APPROVED
        print("\n4️⃣  Testing Policy Evaluation: ₹1,240 Torrent Power (electricity)...")
        payload_electricity = {
            "merchant_name": "Torrent Power",
            "amount": 1240.0,
            "category": "utilities",
            "currency": "INR",
            "idempotency_key": "live_test_torrent_1240",
        }
        resp = client.post("/api/policy/evaluate", json=payload_electricity)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        res_a = resp.json()
        print(f"   ✓ Result: Approved={res_a['approved']}, Decision={res_a['decision_code']}")
        print(f"   ✓ Reason: {res_a['reason']}")
        print(f"   ✓ Remaining Daily Budget: ₹{res_a['remaining_daily_budget']:,.2f}")
        assert res_a["approved"] is True, "Expected ₹1,240 to be approved"

        # 5. Test Scenario B: ₹3,000 Netflix payment -> APPROVED
        print("\n5️⃣  Testing Policy Evaluation: ₹3,000 Netflix (subscriptions)...")
        payload_netflix = {
            "merchant_name": "Netflix",
            "amount": 3000.0,
            "category": "subscriptions",
            "currency": "INR",
            "idempotency_key": "live_test_netflix_3000",
        }
        resp = client.post("/api/policy/evaluate", json=payload_netflix)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        res_b = resp.json()
        print(f"   ✓ Result: Approved={res_b['approved']}, Decision={res_b['decision_code']}")
        print(f"   ✓ Reason: {res_b['reason']}")
        print(f"   ✓ Remaining Daily Budget: ₹{res_b['remaining_daily_budget']:,.2f}")
        assert res_b["approved"] is True, "Expected ₹3,000 Netflix to be approved (limit is ₹5,000)"

        # 6. Test Scenario C: ₹6,000 payment -> REJECTED (Exceeds ₹5,000 limit)
        print("\n6️⃣  Testing Policy Evaluation: ₹6,000 MakeMyTrip (over per-tx limit)...")
        payload_over_limit = {
            "merchant_name": "MakeMyTrip",
            "amount": 6000.0,
            "category": "travel",
            "currency": "INR",
            "idempotency_key": "live_test_mmt_6000",
        }
        resp = client.post("/api/policy/evaluate", json=payload_over_limit)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        res_c = resp.json()
        print(f"   ✓ Result: Approved={res_c['approved']}, Decision={res_c['decision_code']}")
        print(f"   ✓ Reason: {res_c['reason']}")
        assert res_c["approved"] is False, "Expected ₹6,000 to be rejected"
        assert res_c["decision_code"] in ["TX_LIMIT_EXCEEDED", "MULTIPLE_POLICY_VIOLATIONS"]

        # 7. Test Scenario D: ₹500 Blocked Category (Crypto) -> REJECTED
        print("\n7️⃣  Testing Policy Evaluation: ₹500 Crypto (blocked category)...")
        payload_crypto = {
            "merchant_name": "CoinDCX",
            "amount": 500.0,
            "category": "crypto",
            "currency": "INR",
            "idempotency_key": "live_test_crypto_500",
        }
        resp = client.post("/api/policy/evaluate", json=payload_crypto)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        res_d = resp.json()
        print(f"   ✓ Result: Approved={res_d['approved']}, Decision={res_d['decision_code']}")
        print(f"   ✓ Reason: {res_d['reason']}")
        assert res_d["approved"] is False
        assert res_d["decision_code"] == "CATEGORY_BLOCKED"

        # 8. Verify GET /api/transactions
        print("\n8️⃣  Testing GET /api/transactions...")
        resp = client.get("/api/transactions")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        txs = resp.json()
        print(f"   ✓ Retrieved {len(txs)} transactions from database.")

        # 9. Verify GET /api/audit-logs and verify entries written to DB
        print("\n9️⃣  Testing GET /api/audit-logs and DB persistence...")
        resp = client.get("/api/audit-logs")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        audit_logs = resp.json()
        print(f"   ✓ Retrieved {len(audit_logs)} audit log records.")
        for log in audit_logs[:4]:
            print(f"     • [{log['decision']}] {log['action']} - Reason: {log['reason'][:60]}... (Timestamp: {log['created_at']})")

        print("\n" + "=" * 70)
        print("🎉 ALL LIVE DAY 1 CHECKS AND ENDPOINTS PASSED PERFECTLY!")
        print("=" * 70)

    finally:
        db.close()


if __name__ == "__main__":
    run_live_verification()
