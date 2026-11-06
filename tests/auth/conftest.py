from __future__ import annotations

import pathlib

import pytest
from authhelpers import ORIGIN
from fastapi.testclient import TestClient

from groundtruth.platform.api.app import app
from groundtruth.platform.api.dependencies import get_store, reset_store
from groundtruth.platform.auth import passwords
from groundtruth.platform.auth.ratelimit import login_limiter
from groundtruth.platform.config import get_settings
from groundtruth.platform.store import migrate
from groundtruth.platform.store.database import create_db_engine, create_session_factory
from groundtruth.platform.store.sql import SqlEvidenceStore


@pytest.fixture
def _fast_scrypt(monkeypatch):
    """Cheap scrypt cost for speed. The default-cost round trip is tested separately."""
    monkeypatch.setattr(passwords, "SCRYPT_N", 2**10)


@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "auth_required", True)
    monkeypatch.setattr(s, "auth_allow_registration", True)
    monkeypatch.setattr(s, "auth_cookie_secure", False)
    monkeypatch.setattr(s, "cors_allowed_origins", ORIGIN)
    return s


@pytest.fixture
def sessions(tmp_path: pathlib.Path):
    url = f"sqlite:///{tmp_path / 'auth.db'}"
    migrate.upgrade(url)
    return create_session_factory(create_db_engine(url))


@pytest.fixture
def client(settings, sessions):
    reset_store()
    login_limiter.clear()
    app.dependency_overrides[get_store] = lambda: SqlEvidenceStore(sessions)
    with TestClient(app, base_url=ORIGIN) as c:
        yield c
    app.dependency_overrides.clear()
    reset_store()
    login_limiter.clear()
