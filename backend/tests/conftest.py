import uuid
import os
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import get_db
from app.models import (
    Base,
    User,
    Agent,
    Wallet,
    Policy,
    Merchant,
    PaymentMethod,
    Transaction,
    PaymentAttempt,
    AuditLog,
)
from app.config import get_settings, Settings


SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def override_get_settings():
    """
    Test settings override.

    Explicitly forces PAYMENT_PROVIDER=MOCK so that no test is affected
    by a developer's real .env having PAYMENT_PROVIDER=RAZORPAY.

    This is wired into FastAPI DI for routes that use Depends(get_settings).
    Direct calls to get_payment_provider() also see MOCK because:
      1. The session-scoped clear_settings_cache fixture clears the lru_cache.
      2. PAYMENT_PROVIDER env var is set to "MOCK" before the first
         get_settings() call in the test process.
    """
    return Settings(
        APP_NAME="AgentPay",
        APP_ENV="test",
        DEBUG=True,
        DATABASE_URL=SQLALCHEMY_TEST_DATABASE_URL,
        # ── CRITICAL: Force MOCK regardless of developer's real .env ──────────
        PAYMENT_PROVIDER="MOCK",
        RAZORPAY_KEY_ID="",
        RAZORPAY_KEY_SECRET="",
    )


@pytest.fixture(autouse=True, scope="session")
def clear_settings_cache():
    """
    Session-scoped autouse fixture that clears the lru_cache on get_settings
    and forces PAYMENT_PROVIDER=MOCK in the process environment.

    ROOT CAUSE OF PROVIDER LEAKAGE:
        get_settings() is decorated with @lru_cache.  When the app module is
        first imported (e.g. `from app.main import app`), get_settings() is
        called and its return value — including PAYMENT_PROVIDER=RAZORPAY from
        the developer's .env — is cached at process level.

        Subsequent calls to get_payment_provider() inside endpoint handlers that
        do NOT go through FastAPI DI (direct function calls like
        `adapter = get_payment_provider()` in tasks.py / agent.py) receive the
        cached real Settings instead of the test override.  This causes them to
        instantiate RazorpayPaymentProvider and attempt real/test-mode network
        calls, making ~15 flight/task tests fail when PAYMENT_PROVIDER=RAZORPAY.

    FIX:
        1. Clear the lru_cache once at session start so the first call after
           clearing returns Settings built from the process environment, which
           we force to PAYMENT_PROVIDER=MOCK via os.environ.
        2. The FastAPI DI override (override_get_settings) remains the
           authoritative source for all Depends(get_settings) paths.
        3. Production/dev behaviour is NOT affected; cache is cleared only
           inside the pytest process.
        4. Tests that explicitly need Razorpay use their own
           app.dependency_overrides[get_settings] override as before.
    """
    # Force MOCK in process env so any direct Settings() call uses MOCK.
    _orig_provider = os.environ.get("PAYMENT_PROVIDER")
    _orig_key_id = os.environ.get("RAZORPAY_KEY_ID")
    _orig_key_secret = os.environ.get("RAZORPAY_KEY_SECRET")

    os.environ["PAYMENT_PROVIDER"] = "MOCK"
    os.environ["RAZORPAY_KEY_ID"] = ""
    os.environ["RAZORPAY_KEY_SECRET"] = ""

    # Clear the stale cached settings (built from real .env before we changed env)
    get_settings.cache_clear()

    yield

    # Restore original values and clear cache again to avoid bleed-through.
    if _orig_provider is not None:
        os.environ["PAYMENT_PROVIDER"] = _orig_provider
    else:
        os.environ.pop("PAYMENT_PROVIDER", None)
    if _orig_key_id is not None:
        os.environ["RAZORPAY_KEY_ID"] = _orig_key_id
    else:
        os.environ.pop("RAZORPAY_KEY_ID", None)
    if _orig_key_secret is not None:
        os.environ["RAZORPAY_KEY_SECRET"] = _orig_key_secret
    else:
        os.environ.pop("RAZORPAY_KEY_SECRET", None)

    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = override_get_settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


from scripts.seed import seed_database
from sqlalchemy import select


@pytest.fixture
def test_seed_data(db_session):
    seed_database(db_session)
    user = db_session.execute(select(User).where(User.email == "krisha@agentpay.local")).scalar_one()
    agent = db_session.execute(select(Agent).where(Agent.user_id == user.id)).scalar_one()
    wallet = db_session.execute(select(Wallet).where(Wallet.agent_id == agent.id)).scalar_one()
    policy = db_session.execute(select(Policy).where(Policy.agent_id == agent.id)).scalar_one()
    merchants = db_session.execute(select(Merchant)).scalars().all()
    bills = db_session.execute(select(Transaction)).scalars().all()

    return {
        "user": user,
        "agent": agent,
        "wallet": wallet,
        "policy": policy,
        "merchants": merchants,
        "bills": bills,
    }
