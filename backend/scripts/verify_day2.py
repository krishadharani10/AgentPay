import os
import sys
import uuid
from typing import Dict, Any

backend_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from fastapi.testclient import TestClient
from sqlalchemy import select, delete
from app.main import app
from app.database import SessionLocal
from app.models.user import User
from app.models.agent import Agent
from app.models.wallet import Wallet
from app.models.payment_method import PaymentMethod
from app.models.policy import Policy
from app.models.transaction import Transaction
from app.models.audit_log import AuditLog
from app.models.merchant import Merchant


def setup_verification_state(db) -> Dict[str, Any]:
    """
    Creates or resets an isolated, dedicated verification state.
    
    IDEMPOTENCY & ISOLATION GUARANTEES:
    1. Uses a dedicated user ('verify_day2@agentpay.local') and agent ('Day 2 Verification Agent').
    2. Only resets/cleans transactions and audit records belonging to this dedicated verification agent.
    3. Leaves all existing development and production data completely untouched.
    4. Configures policy per Day 2 spec: cap of ₹1,500 for single transaction limit so ₹1,240 is ALLOWED
       and ₹3,000 Netflix subscription is DENIED by Policy Engine.
    """
    # 1. Verification User
    user = db.execute(
        select(User).where(User.email == "verify_day2@agentpay.local")
    ).scalar_one_or_none()
    if not user:
        user = User(
            id=uuid.uuid4(),
            email="verify_day2@agentpay.local",
            name="Day 2 Verifier",
            is_active=True,
        )
        db.add(user)
        db.flush()

    # 2. Verification Agent
    agent = db.execute(
        select(Agent).where(Agent.user_id == user.id, Agent.name == "Day 2 Verification Agent")
    ).scalar_one_or_none()
    if not agent:
        agent = Agent(
            id=uuid.uuid4(),
            user_id=user.id,
            name="Day 2 Verification Agent",
            description="Dedicated isolated agent for deterministic Day 2 verification flows",
            is_active=True,
        )
        db.add(agent)
        db.flush()

    # 3. Verification Wallet
    wallet = db.execute(
        select(Wallet).where(Wallet.agent_id == agent.id)
    ).scalar_one_or_none()
    if not wallet:
        wallet = Wallet(
            id=uuid.uuid4(),
            agent_id=agent.id,
            status="ACTIVE",
            daily_spending_limit=20000.0,
            per_transaction_limit=5000.0,
            currency="INR",
        )
        db.add(wallet)
        db.flush()
    else:
        wallet.status = "ACTIVE"
        wallet.daily_spending_limit = 20000.0
        wallet.per_transaction_limit = 5000.0
        db.flush()

    # 4. Payment Method
    pm = db.execute(
        select(PaymentMethod).where(PaymentMethod.wallet_id == wallet.id, PaymentMethod.is_primary == True)
    ).scalar_one_or_none()
    if not pm:
        pm = PaymentMethod(
            id=uuid.uuid4(),
            wallet_id=wallet.id,
            type="UPI_VPA",
            provider="mock",
            token_or_alias="verify.agent@icici",
            is_primary=True,
            is_active=True,
            priority=1,
        )
        db.add(pm)
        db.flush()

    # 5. Policy: Set max_transaction_amount to ₹1,500 per Day 2 Requirement 5
    # (Netflix ₹3,000 will be DENIED, Torrent Power ₹1,240 will be ALLOWED)
    policy = db.execute(
        select(Policy).where(Policy.agent_id == agent.id)
    ).scalar_one_or_none()
    if not policy:
        policy = Policy(
            id=uuid.uuid4(),
            agent_id=agent.id,
            name="Verification Policy (Capped at ₹1,500)",
            description="Policy for Day 2 verification testing",
            max_transaction_amount=1500.0,
            daily_spending_limit=20000.0,
            allowed_categories=["utilities", "subscriptions", "travel"],
            blocked_categories=["gambling", "crypto"],
            allowed_merchants=[],
            blocked_merchants=[],
            wallet_enabled=True,
            is_active=True,
        )
        db.add(policy)
        db.flush()
    else:
        policy.name = "Verification Policy (Capped at ₹1,500)"
        policy.max_transaction_amount = 1500.0
        policy.daily_spending_limit = 20000.0
        policy.allowed_categories = ["utilities", "subscriptions", "travel"]
        policy.blocked_categories = ["gambling", "crypto"]
        policy.wallet_enabled = True
        policy.is_active = True
        db.flush()

    # 6. IDEMPOTENT RESET: Clean up previous verification transactions and audit logs ONLY for this verification agent
    db.execute(delete(AuditLog).where(AuditLog.agent_id == agent.id))
    db.execute(delete(Transaction).where(Transaction.agent_id == agent.id))
    db.commit()

    return {
        "user": user,
        "agent": agent,
        "wallet": wallet,
        "policy": policy,
        "payment_method": pm,
    }


def run_day2_verification():
    print("=" * 75)
    print("🤖 RUNNING AGENTPAY DAY 2 AGENT ORCHESTRATION & MOCK ADAPTER VERIFICATION")
    print("=" * 75)

    client = TestClient(app)
    db = SessionLocal()

    try:
        # Step 0: Setup isolated test fixture
        fixture = setup_verification_state(db)
        agent_id = str(fixture["agent"].id)
        print(f"🔧 Isolated verification state initialized (Agent ID: {agent_id})")

        # 1. DEMO 1: ALLOWED PAYMENT
        print("\n1️⃣  [DEMO 1] ALLOWED PAYMENT FLOW")
        print("   Prompt: 'Pay my Torrent Power electricity bill of ₹1,240'")
        req_allowed = {
            "message": "Pay my Torrent Power electricity bill of 1240",
            "merchant_name": "Torrent Power",
            "amount": 1240.0,
            "category": "utilities",
            "agent_id": agent_id,
        }
        resp = client.post("/api/agent/run", json=req_allowed)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        print(f"   ✓ Decision: {data['decision']}")
        print(f"   ✓ Payment Status: {data['payment_status']}")
        print(f"   ✓ Payment ID: {data['payment_id']}")
        print(f"   ✓ Provider ID: {data['provider_payment_id']}")
        print(f"   ✓ Agent Message: {data['message']}")
        print(f"   ✓ Remaining Daily Budget: ₹{data['remaining_daily_budget']:,.2f}")
        assert data["success"] is True
        assert data["decision"] == "ALLOWED"
        assert data["payment_status"] == "SUCCESS"
        assert data["payment_id"] is not None

        # 2. DEMO 2: DENIED PAYMENT (Exceeds Policy Subscription Limit of ₹1,500)
        print("\n2️⃣  [DEMO 2] DENIED PAYMENT FLOW (Policy Violation)")
        print("   Prompt: 'Pay my Netflix subscription of ₹3,000' (Policy cap is ₹1,500)")
        req_denied = {
            "message": "Pay my Netflix subscription of 3000",
            "merchant_name": "Netflix",
            "amount": 3000.0,
            "category": "subscriptions",
            "agent_id": agent_id,
        }
        resp = client.post("/api/agent/run", json=req_denied)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        print(f"   ✓ Decision: {data['decision']} (Code: {data['decision_code']})")
        print(f"   ✓ Payment Status: {data['payment_status']}")
        print(f"   ✓ Payment ID: {data['payment_id']} (Payment Adapter NEVER called)")
        print(f"   ✓ Agent Message: {data['message']}")
        assert data["success"] is False
        assert data["decision"] == "DENIED"
        assert data["payment_id"] is None
        assert data["payment_status"] == "REJECTED"
        assert "TX_LIMIT_EXCEEDED" in data["decision_code"] or "MULTIPLE" in data["decision_code"]

        # 3. DEMO 3: FAILED PAYMENT (Gateway Error Simulation)
        print("\n3️⃣  [DEMO 3] FAILED PAYMENT FLOW (Gateway Error)")
        print("   Prompt: 'Pay my Netflix subscription of ₹499' (Simulating gateway timeout)")
        req_failed = {
            "message": "Pay my Netflix subscription of 499",
            "merchant_name": "Netflix",
            "amount": 499.0,
            "category": "subscriptions",
            "agent_id": agent_id,
            "force_failure": True,
        }
        resp = client.post("/api/agent/run", json=req_failed)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        print(f"   ✓ Decision: {data['decision']}")
        print(f"   ✓ Payment Status: {data['payment_status']}")
        print(f"   ✓ Payment ID: {data['payment_id']}")
        print(f"   ✓ Agent Message: {data['message']}")
        assert data["success"] is False
        assert data["decision"] == "ALLOWED"  # Allowed by policy
        assert data["payment_status"] == "FAILED"  # Failed at adapter
        failed_payment_id = data["payment_id"]
        assert failed_payment_id is not None

        # 4. DEMO 4: RETRY FLOW
        print("\n4️⃣  [DEMO 4] SAFE RETRY FLOW")
        print(f"   Retrying failed payment {failed_payment_id}...")
        req_retry = {
            "message": "Retry payment for Netflix",
            "bill_id": failed_payment_id,
            "merchant_name": "Netflix",
            "amount": 499.0,
            "category": "subscriptions",
            "agent_id": agent_id,
            "force_failure": False,
            "retry_if_failed": True,
        }
        resp = client.post("/api/agent/run", json=req_retry)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        print(f"   ✓ Decision: {data['decision']}")
        print(f"   ✓ Payment Status: {data['payment_status']}")
        print(f"   ✓ Provider ID: {data['provider_payment_id']}")
        print(f"   ✓ Agent Message: {data['message']}")
        assert data["success"] is True
        assert data["payment_status"] == "SUCCESS"

        # 5. DEMO 5: PREVENT DUPLICATE RETRY ON SUCCESSFUL PAYMENT
        print("\n5️⃣  [DEMO 5] PREVENT RETRY ON ALREADY SUCCESSFUL PAYMENT")
        print(f"   Attempting to retry successful payment {failed_payment_id}...")
        resp = client.post("/api/agent/run", json=req_retry)
        assert resp.status_code == 200
        data = resp.json()
        print(f"   ✓ Response: Payment already marked as SUCCESS (idempotent safe response).")
        assert data["payment_status"] == "SUCCESS"

        # 6. AUDIT TRAIL LOGS
        print("\n6️⃣  VERIFYING AUDIT TRAIL IN POSTGRESQL")
        logs = db.execute(
            select(AuditLog)
            .where(AuditLog.agent_id == fixture["agent"].id)
            .order_by(AuditLog.created_at.asc())
        ).scalars().all()
        
        assert len(logs) > 0, "Audit logs must be recorded for verification agent"
        for l in logs:
            print(f"   • [{l.decision:10}] {l.event_type:18} | Action: {l.action:16} | Reason: {l.reason[:45]}...")

        print("\n" + "=" * 75)
        print("🎉 ALL DAY 2 AGENT ORCHESTRATION VERIFICATION FLOWS COMPLETED PERFECTLY!")
        print("=" * 75)

    finally:
        db.close()


if __name__ == "__main__":
    run_day2_verification()
