"""
Shared fixtures for the Task Tracker test suite.

Test isolation strategy
-----------------------
Each test gets a fresh, isolated SQLite database via aiosqlite (file-based in
a per-test tmp_path). This is fast (no Postgres required in CI) and fully
isolated between tests.

We override the `get_db` FastAPI dependency so every request made through
TestClient uses the same test session.

Authentication
--------------
Phase 4 made all task endpoints require a Bearer token. To keep existing
task tests working unchanged, the default `client` fixture is pre-authenticated
as a test user (its Authorization header is set automatically).

Fixtures provided:
  - db_session         : the isolated AsyncSession
  - anon_client        : TestClient with NO auth header (for auth/negative tests)
  - client             : TestClient pre-authenticated as user A
  - second_user_token  : a Bearer token for a distinct user B (ownership tests)
"""

import os

# ---------------------------------------------------------------------------
# Set the test DATABASE_URL *before* any app module is imported.
# ---------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_default.db")

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base, get_db

# ---------------------------------------------------------------------------
# Per-test async engine + session (file-based SQLite for isolation)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def db_session(tmp_path):
    """Yield an AsyncSession backed by a fresh, isolated SQLite DB."""
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test_tasks.db"
    engine = create_async_engine(db_url, echo=False)

    # Import ORM models so their tables are registered on Base.metadata
    import app.models.orm  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


# ---------------------------------------------------------------------------
# Base (unauthenticated) client — overrides get_db with the test session
# ---------------------------------------------------------------------------

@pytest.fixture()
def anon_client(db_session):
    """A TestClient with the DB override but NO Authorization header."""
    from fastapi.testclient import TestClient

    from app.main import app

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _register_and_login(client, email: str, password: str = "password123") -> str:
    """Register a user (ignore duplicate) and return their Bearer token."""
    client.post("/auth/register", json={"email": email, "password": password})
    resp = client.post(
        "/auth/login",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture()
def client(anon_client):
    """
    A TestClient pre-authenticated as user A (userA@example.com).

    Its Authorization header is set on the underlying httpx client so every
    request from existing task tests carries the Bearer token automatically.
    """
    token = _register_and_login(anon_client, "userA@example.com")
    anon_client.headers.update({"Authorization": f"Bearer {token}"})
    return anon_client


@pytest.fixture()
def second_user_token(anon_client):
    """A Bearer token for a distinct user B (userB@example.com)."""
    return _register_and_login(anon_client, "userB@example.com")
