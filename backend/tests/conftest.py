import uuid
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
    return Settings(
        APP_NAME="AgentPay",
        APP_ENV="test",
        DEBUG=True,
        DATABASE_URL=SQLALCHEMY_TEST_DATABASE_URL,
    )


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
