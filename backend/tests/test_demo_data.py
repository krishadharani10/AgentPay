import uuid
import pytest
from sqlalchemy import select, func
from app.agents.tools import get_bill
from app.agents.orchestrator import AgentOrchestrator
from app.agents.llm_provider import MockLLMProvider
from app.services.payment_adapter import MockPaymentAdapter
from app.models.merchant import Merchant
from app.models.transaction import Transaction
from app.models.audit_log import AuditLog
from scripts.seed import seed_database, DEMO_MERCHANTS_DATA, DEMO_BILLS_DATA


class TestDemoDataAndSeeding:
    def test_1_torrent_power_bill_returns_1240(self, db_session, test_seed_data):
        """Requirement 1: Torrent Power returns INR 1,240."""
        bill = get_bill(db_session, merchant_name="Torrent Power")
        assert bill is not None
        assert bill["merchant_name"] == "Torrent Power"
        assert bill["amount"] == 1240.0
        assert bill["currency"] == "INR"
        assert bill["category"] == "utilities"
        assert "electricity" in bill["description"].lower() or "power" in bill["description"].lower()
        assert bill["status"] == "PAYMENT_PENDING"

    def test_2_netflix_bill_returns_3000(self, db_session, test_seed_data):
        """Requirement 2: Netflix returns INR 3,000."""
        bill = get_bill(db_session, merchant_name="Netflix")
        assert bill is not None
        assert bill["merchant_name"] == "Netflix"
        assert bill["amount"] == 3000.0
        assert bill["currency"] == "INR"
        assert bill["category"] == "subscriptions"
        assert "netflix" in bill["description"].lower()
        assert bill["status"] == "PAYMENT_PENDING"

    def test_3_spotify_bill_returns_699(self, db_session, test_seed_data):
        """Requirement 3: Spotify returns INR 699."""
        bill = get_bill(db_session, merchant_name="Spotify")
        assert bill is not None
        assert bill["merchant_name"] == "Spotify"
        assert bill["amount"] == 699.0
        assert bill["currency"] == "INR"
        assert bill["category"] == "subscriptions"
        assert "spotify" in bill["description"].lower()
        assert bill["status"] == "PAYMENT_PENDING"

    def test_4_makemytrip_and_amazon_bills_exist(self, db_session, test_seed_data):
        """Verify MakeMyTrip and Amazon demo bills exist with appropriate metadata."""
        mmt_bill = get_bill(db_session, merchant_name="MakeMyTrip")
        assert mmt_bill is not None
        assert mmt_bill["merchant_name"] == "MakeMyTrip"
        assert mmt_bill["amount"] == 4500.0
        assert mmt_bill["category"] == "travel"
        assert mmt_bill["status"] == "PAYMENT_PENDING"

        amazon_bill = get_bill(db_session, merchant_name="Amazon")
        assert amazon_bill is not None
        assert amazon_bill["merchant_name"] == "Amazon"
        assert amazon_bill["amount"] == 899.0
        assert amazon_bill["category"] == "shopping"
        assert amazon_bill["status"] == "PAYMENT_PENDING"

    def test_5_bills_retrieved_via_get_bill_by_id_and_query(self, db_session, test_seed_data):
        """Requirement 4: Bills can be retrieved through get_bill by ID, name, or query string."""
        # 1. Lookup by bill_id
        torrent_bill = get_bill(db_session, merchant_name="Torrent Power")
        bill_by_id = get_bill(db_session, bill_id=uuid.UUID(torrent_bill["bill_id"]))
        assert bill_by_id is not None
        assert bill_by_id["bill_id"] == torrent_bill["bill_id"]
        assert bill_by_id["amount"] == 1240.0

        # 2. Lookup by query string
        bill_by_query = get_bill(db_session, query="electricity")
        assert bill_by_query is not None
        assert bill_by_query["merchant_name"] == "Torrent Power"
        assert bill_by_query["amount"] == 1240.0

        bill_by_music = get_bill(db_session, query="Spotify")
        assert bill_by_music is not None
        assert bill_by_music["amount"] == 699.0

    def test_6_agent_retrieves_bill_amount_dynamically_without_hardcoding(self, db_session, test_seed_data):
        """Verify the agent orchestrator retrieves bill amounts from DB without prompt specifying amount."""
        orchestrator = AgentOrchestrator(
            adapter=MockPaymentAdapter(default_failure=False),
            llm_provider=MockLLMProvider(),
        )

        # User does NOT specify amount in the prompt
        res = orchestrator.process_with_llm(
            db_session,
            message="Pay my Torrent Power electricity bill",
        )
        assert res.success is True
        assert res.amount == 1240.0
        assert res.merchant_name == "Torrent Power"
        assert "1,240" in res.message

        # User pays Spotify without specifying amount
        res_spotify = orchestrator.process_with_llm(
            db_session,
            message="Pay my Spotify subscription",
        )
        assert res_spotify.success is True
        assert res_spotify.amount == 699.0
        assert res_spotify.merchant_name == "Spotify"

    def test_7_seed_database_idempotency_prevents_duplicates(self, db_session):
        """Requirement 5: Running the seed process repeatedly does not create duplicate demo records."""
        # Run seed process 3 consecutive times
        seed_database(db_session)
        seed_database(db_session)
        seed_database(db_session)

        # Count merchants: must be exactly 5
        merchant_count = db_session.execute(select(func.count(Merchant.id))).scalar()
        assert merchant_count == 5

        # Count seeded pending transactions: must be exactly 5
        tx_count = db_session.execute(select(func.count(Transaction.id))).scalar()
        assert tx_count == 5

        # Verify distinct merchants
        merchants = db_session.execute(select(Merchant)).scalars().all()
        names = {m.name for m in merchants}
        expected_names = {"Torrent Power", "Netflix", "Spotify", "MakeMyTrip", "Amazon"}
        assert names == expected_names

        # Verify distinct bills
        bills = db_session.execute(select(Transaction)).scalars().all()
        bill_merchants = {b.merchant_name: b.amount for b in bills}
        assert bill_merchants["Torrent Power"] == 1240.0
        assert bill_merchants["Netflix"] == 3000.0
        assert bill_merchants["Spotify"] == 699.0
        assert bill_merchants["MakeMyTrip"] == 4500.0
        assert bill_merchants["Amazon"] == 899.0

        # Count seed audit logs: must be exactly 5 (one per bill, not multiplied by seed runs)
        seed_audit_count = db_session.execute(
            select(func.count(AuditLog.id)).where(AuditLog.event_type == "DEMO_SEED_TRANSACTION")
        ).scalar()
        assert seed_audit_count == 5

    def test_8_all_merchants_active(self, db_session, test_seed_data):
        """Verify all demo merchants are created and marked active."""
        merchants = db_session.execute(select(Merchant)).scalars().all()
        assert len(merchants) == 5
        for m in merchants:
            assert m.is_active is True
            assert m.category in ["utilities", "subscriptions", "travel", "shopping"]
