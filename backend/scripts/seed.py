import os
import sys
import uuid
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

# Add backend directory to sys.path
backend_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from sqlalchemy import select
from app.database import SessionLocal
from app.models.user import User
from app.models.agent import Agent
from app.models.wallet import Wallet
from app.models.payment_method import PaymentMethod
from app.models.policy import Policy
from app.models.merchant import Merchant
from app.models.transaction import Transaction
from app.models.audit_log import AuditLog

# Stable deterministic UUIDs for core demo entities
USER_KRISHA_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
AGENT_ASSISTANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
WALLET_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")
PM_PRIMARY_ID = uuid.UUID("00000000-0000-0000-0000-000000000004")
PM_FALLBACK_ID = uuid.UUID("00000000-0000-0000-0000-000000000005")
POLICY_ID = uuid.UUID("00000000-0000-0000-0000-000000000006")

DEMO_MERCHANTS_DATA = [
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000011"),
        "name": "Torrent Power",
        "category": "utilities",
        "description": "Electricity and Power Utility",
        "website": "https://torrentpower.com",
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000012"),
        "name": "Netflix",
        "category": "subscriptions",
        "description": "Digital streaming subscription",
        "website": "https://netflix.com",
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000013"),
        "name": "Spotify",
        "category": "subscriptions",
        "description": "Music and podcast streaming subscription",
        "website": "https://spotify.com",
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000014"),
        "name": "MakeMyTrip",
        "category": "travel",
        "description": "Flight and hotel bookings",
        "website": "https://makemytrip.com",
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000015"),
        "name": "Amazon",
        "category": "shopping",
        "description": "E-commerce and marketplace",
        "website": "https://amazon.in",
    },
]

DEMO_BILLS_DATA = [
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000021"),
        "idempotency_key": "seed_bill_torrent_power_001",
        "merchant_name": "Torrent Power",
        "amount": 1240.0,
        "category": "utilities",
        "status": "PENDING",
        "decision_reason": "Electricity bill",
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000022"),
        "idempotency_key": "seed_bill_netflix_001",
        "merchant_name": "Netflix",
        "amount": 3000.0,
        "category": "subscriptions",
        "status": "PENDING",
        "decision_reason": "Netflix subscription",
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000023"),
        "idempotency_key": "seed_bill_spotify_001",
        "merchant_name": "Spotify",
        "amount": 699.0,
        "category": "subscriptions",
        "status": "PENDING",
        "decision_reason": "Spotify subscription",
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000024"),
        "idempotency_key": "seed_bill_makemytrip_001",
        "merchant_name": "MakeMyTrip",
        "amount": 4500.0,
        "category": "travel",
        "status": "PENDING",
        "decision_reason": "Flight booking to Mumbai",
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000025"),
        "idempotency_key": "seed_bill_amazon_001",
        "merchant_name": "Amazon",
        "amount": 899.0,
        "category": "shopping",
        "status": "PENDING",
        "decision_reason": "Office supplies and essentials",
    },
]


def seed_database(db: Optional[Session] = None):
    """
    Seeds the database with deterministic demo data.
    Guaranteed idempotent: Safe to execute repeatedly without duplicate records.
    """
    is_external_session = db is not None
    if not is_external_session:
        db = SessionLocal()

    try:
        print("🌱 Seeding AgentPay Deterministic Demo Data...")

        # 1. Seed User: Krisha
        user = db.execute(select(User).where(User.email == "krisha@agentpay.local")).scalar_one_or_none()
        if not user:
            user = User(
                id=USER_KRISHA_ID,
                email="krisha@agentpay.local",
                name="Krisha",
                is_active=True,
            )
            db.add(user)
            db.flush()
            print(f"  ✓ Created User: {user.name} ({user.email})")
        else:
            user.name = "Krisha"
            user.is_active = True
            db.flush()
            print(f"  • User exists: {user.name}")

        # 2. Seed Agent: Personal Assistant
        agent = db.execute(
            select(Agent).where(Agent.user_id == user.id, Agent.name == "Personal Assistant")
        ).scalar_one_or_none()
        if not agent:
            agent = Agent(
                id=AGENT_ASSISTANT_ID,
                user_id=user.id,
                name="Personal Assistant",
                description="Autonomous AI Assistant for household payments and subscriptions",
                is_active=True,
            )
            db.add(agent)
            db.flush()
            print(f"  ✓ Created Agent: {agent.name}")
        else:
            agent.is_active = True
            db.flush()
            print(f"  • Agent exists: {agent.name}")

        # 3. Seed Wallet
        wallet = db.execute(select(Wallet).where(Wallet.agent_id == agent.id)).scalar_one_or_none()
        if not wallet:
            wallet = Wallet(
                id=WALLET_ID,
                agent_id=agent.id,
                status="ACTIVE",
                daily_spending_limit=10000.0,
                per_transaction_limit=5000.0,
                currency="INR",
            )
            db.add(wallet)
            db.flush()
            print(f"  ✓ Created Wallet: ₹{wallet.daily_spending_limit:,.2f} daily / ₹{wallet.per_transaction_limit:,.2f} per-tx")
        else:
            wallet.status = "ACTIVE"
            wallet.daily_spending_limit = 10000.0
            wallet.per_transaction_limit = 5000.0
            db.flush()
            print(f"  • Wallet exists: ₹{wallet.daily_spending_limit:,.2f} daily / ₹{wallet.per_transaction_limit:,.2f} per-tx")

        # 4. Seed Payment Methods (Primary UPI & Fallback Card)
        primary_pm = db.execute(
            select(PaymentMethod).where(PaymentMethod.wallet_id == wallet.id, PaymentMethod.is_primary == True)
        ).scalar_one_or_none()
        if not primary_pm:
            primary_pm = PaymentMethod(
                id=PM_PRIMARY_ID,
                wallet_id=wallet.id,
                type="UPI_VPA",
                provider="mock",
                token_or_alias="krisha.agent@icici",
                is_primary=True,
                is_active=True,
                priority=1,
            )
            db.add(primary_pm)
            db.flush()

        fallback_pm = db.execute(
            select(PaymentMethod).where(PaymentMethod.wallet_id == wallet.id, PaymentMethod.is_primary == False)
        ).scalar_one_or_none()
        if not fallback_pm:
            fallback_pm = PaymentMethod(
                id=PM_FALLBACK_ID,
                wallet_id=wallet.id,
                type="CARD_TOKEN",
                provider="mock",
                token_or_alias="tok_hdfc_corp_ending_4082",
                is_primary=False,
                is_active=True,
                priority=2,
            )
            db.add(fallback_pm)
            db.flush()
            print("  ✓ Created Primary and Fallback Payment Methods")
        else:
            print("  • Payment Methods exist")

        # 5. Seed Policy
        policy = db.execute(
            select(Policy).where(Policy.agent_id == agent.id, Policy.name == "Autonomous Utility & Subscriptions Policy")
        ).scalar_one_or_none()
        if not policy:
            policy = Policy(
                id=POLICY_ID,
                agent_id=agent.id,
                name="Autonomous Utility & Subscriptions Policy",
                description="Allowed for routine household utilities, subscriptions, travel, and shopping with hard caps.",
                max_transaction_amount=5000.0,
                daily_spending_limit=10000.0,
                allowed_categories=["utilities", "subscriptions", "travel", "shopping"],
                blocked_categories=["gambling", "crypto"],
                allowed_merchants=[],
                blocked_merchants=[],
                wallet_enabled=True,
                is_active=True,
            )
            db.add(policy)
            db.flush()
            print(f"  ✓ Created Policy: {policy.name}")
        else:
            policy.max_transaction_amount = 5000.0
            policy.daily_spending_limit = 10000.0
            policy.allowed_categories = ["utilities", "subscriptions", "travel", "shopping"]
            policy.blocked_categories = ["gambling", "crypto"]
            policy.wallet_enabled = True
            policy.is_active = True
            db.flush()
            print(f"  • Policy updated: {policy.name}")

        # 6. Seed Demo Merchants (Torrent Power, Netflix, Spotify, MakeMyTrip, Amazon)
        merchant_map = {}
        for m_data in DEMO_MERCHANTS_DATA:
            merchant = db.execute(
                select(Merchant).where(Merchant.name == m_data["name"])
            ).scalar_one_or_none()
            if not merchant:
                merchant = Merchant(
                    id=m_data["id"],
                    name=m_data["name"],
                    category=m_data["category"],
                    description=m_data["description"],
                    website=m_data["website"],
                    is_active=True,
                )
                db.add(merchant)
                db.flush()
                print(f"  ✓ Created Merchant: {merchant.name} ({merchant.category})")
            else:
                merchant.category = m_data["category"]
                merchant.description = m_data["description"]
                merchant.website = m_data["website"]
                merchant.is_active = True
                db.flush()
                print(f"  • Merchant updated: {merchant.name} ({merchant.category})")
            merchant_map[merchant.name] = merchant

        # 7. Seed Demo Bills / Pending Payment Requests
        for bill in DEMO_BILLS_DATA:
            tx = db.execute(
                select(Transaction).where(Transaction.idempotency_key == bill["idempotency_key"])
            ).scalar_one_or_none()
            merchant = merchant_map.get(bill["merchant_name"])

            if not tx:
                tx = Transaction(
                    id=bill["id"],
                    idempotency_key=bill["idempotency_key"],
                    agent_id=agent.id,
                    wallet_id=wallet.id,
                    merchant_id=merchant.id if merchant else None,
                    merchant_name=bill["merchant_name"],
                    category=bill["category"],
                    amount=bill["amount"],
                    currency="INR",
                    status=bill["status"],
                    decision_reason=bill["decision_reason"],
                    payment_method_id=primary_pm.id if primary_pm else None,
                    payment_provider="mock",
                    provider_payment_id=f"pay_mock_{bill['idempotency_key']}",
                )
                db.add(tx)
                db.flush()
                print(f"  ✓ Seeded demo bill: {bill['merchant_name']} → ₹{bill['amount']:,.2f} ({bill['category']})")
            else:
                tx.amount = bill["amount"]
                tx.category = bill["category"]
                tx.merchant_name = bill["merchant_name"]
                tx.decision_reason = bill["decision_reason"]
                tx.status = bill["status"]
                if merchant:
                    tx.merchant_id = merchant.id
                db.flush()
                print(f"  • Seeded demo bill updated: {bill['merchant_name']} → ₹{bill['amount']:,.2f} ({bill['category']})")

            # Seed / Upsert corresponding AuditLog entry idempotently
            audit = db.execute(
                select(AuditLog).where(
                    AuditLog.transaction_id == tx.id,
                    AuditLog.event_type == "DEMO_SEED_TRANSACTION",
                ).limit(1)
            ).scalar_one_or_none()
            if not audit:
                audit = AuditLog(
                    id=uuid.uuid5(uuid.NAMESPACE_DNS, f"audit_{bill['idempotency_key']}"),
                    agent_id=agent.id,
                    transaction_id=tx.id,
                    event_type="DEMO_SEED_TRANSACTION",
                    action="SEED_BILL",
                    decision="APPROVED",
                    reason=bill["decision_reason"],
                    rules_checked=[
                        {"rule": "WALLET_STATUS", "passed": True, "details": "Wallet is ACTIVE"},
                        {"rule": "TRANSACTION_LIMIT", "passed": True, "details": f"Amount ₹{bill['amount']:,.2f} within limit ₹5,000"},
                        {"rule": "CATEGORY_CHECK", "passed": True, "details": f"Category '{bill['category']}' allowed"},
                    ],
                    metadata_payload={"idempotency_key": bill["idempotency_key"], "amount": bill["amount"]},
                )
                db.add(audit)
                db.flush()

        db.commit()
        print("✅ Database seeding completed successfully!\n")
    except Exception as e:
        db.rollback()
        print(f"❌ Error during database seeding: {e}")
        raise
    finally:
        if not is_external_session:
            db.close()


if __name__ == "__main__":
    seed_database()
