import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("APP_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_placeholder")
os.environ.setdefault("STRIPE_PRO_PRICE_ID", "price_test_pro")

from app.config import get_settings

get_settings.cache_clear()

import app.db
from app.db import Base


@pytest.fixture(scope="function")
def db_engine():
    """Create a fresh engine for each test function."""
    from sqlalchemy.pool import StaticPool

    test_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    # Override the app.db engine and session factory for this test
    app.db.engine = test_engine
    app.db.SessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    yield test_engine
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()
    app.db.engine = None
    app.db.SessionLocal = None


@pytest.fixture(scope="function")
def db(db_engine):
    """Create a session using the test engine."""
    session = app.db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db):
    """Create a test client with database dependency override."""
    from app.main import create_app
    from app.db import get_db
    
    app = create_app()

    def _override():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
