from __future__ import annotations

from fastapi.testclient import TestClient

from groundtruth.platform.api.app import app

ORIGIN = "http://localhost:3000"
PASSWORD = "correct horse battery"


def register(client: TestClient, email: str, password: str = PASSWORD, **kw):
    return client.post(
        "/auth/register",
        json={"email": email, "password": password},
        headers={"Origin": ORIGIN},
        **kw,
    )


def login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post(
        "/auth/login", json={"email": email, "password": password}, headers={"Origin": ORIGIN}
    )


def new_client(client: TestClient) -> TestClient:
    """A second browser: same app, its own cookie jar."""
    return TestClient(app, base_url=ORIGIN)
