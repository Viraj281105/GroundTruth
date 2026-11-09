from __future__ import annotations

import pathlib
import sys

import pytest
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from groundtruth.platform.store import migrate
from groundtruth.platform.store.database import create_db_engine, create_session_factory
from pgdb import new_database


@pytest.fixture
def tenancy_db_url(tmp_path: pathlib.Path):
    db = new_database(tmp_path, "tenancy.db")
    yield db.url
    db.drop()


@pytest.fixture
def tenancy_sessions(tenancy_db_url: str) -> sessionmaker[Session]:
    """A session factory over a temporary SQLite database migrated to head."""
    migrate.upgrade(tenancy_db_url)
    return create_session_factory(create_db_engine(tenancy_db_url))


# --- HTTP fixtures for the org API tests (mirror tests/auth/conftest.py) ---------------
@pytest.fixture
def _fast_scrypt(monkeypatch):
    from groundtruth.platform.auth import passwords

    monkeypatch.setattr(passwords, "SCRYPT_N", 2**10)


@pytest.fixture
def settings(monkeypatch):
    from groundtruth.platform.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "auth_required", True)
    monkeypatch.setattr(s, "auth_allow_registration", True)
    monkeypatch.setattr(s, "auth_cookie_secure", False)
    monkeypatch.setattr(s, "cors_allowed_origins", "http://localhost:3000")
    return s


@pytest.fixture
def sessions(tenancy_sessions):
    return tenancy_sessions


@pytest.fixture
def client(settings, sessions):
    from fastapi.testclient import TestClient

    from groundtruth.platform.api.app import app
    from groundtruth.platform.api.dependencies import get_store, reset_store
    from groundtruth.platform.auth.ratelimit import login_limiter
    from groundtruth.platform.store.sql import SqlEvidenceStore

    reset_store()
    login_limiter.clear()
    app.dependency_overrides[get_store] = lambda: SqlEvidenceStore(sessions)
    with TestClient(app, base_url="http://localhost:3000") as c:
        yield c
    app.dependency_overrides.clear()
    reset_store()
    login_limiter.clear()
