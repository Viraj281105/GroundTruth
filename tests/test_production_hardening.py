"""Production hardening (#51): sign-in on writes, a submission budget, security headers, and an
audit trail of who asked for which analysis.

Each acceptance item is checked against the running application, not its configuration alone:
every write route is called anonymously, the budget is spent through both analysis routes, and
the audit rows are read back from the database.
"""

from __future__ import annotations

import importlib
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from sqlalchemy import select

from groundtruth.contracts.errors import ConfigurationError
from groundtruth.platform.api.app import app, refuse_unsafe_production
from groundtruth.platform.api.errors import API_ERROR_STATUS, ApiErrorCode
from groundtruth.platform.api.rate_limits import submission_limiter
from groundtruth.platform.api.security_headers import (
    API_CSP,
    DOCS_CSP,
    HSTS,
    SecurityHeadersMiddleware,
)
from groundtruth.platform.cases import creator
from groundtruth.platform.config import REPO_ROOT, get_settings
from groundtruth.platform.metrics import REGISTRY
from groundtruth.platform.store.models import AuditEventRow

ORIGIN = {"Origin": "http://testserver"}
NEW_CASE = {
    "name": "Hardening Probe",
    "country": "Zimbabwe",
    "registry_id": "VCS 9998",
    "area_ha": 5000,
}


def _write_routes() -> list[tuple[str, str]]:
    def walk(routes: Any) -> Any:
        for route in routes:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                yield from walk(inner.routes)
            elif hasattr(route, "methods"):
                yield route

    return sorted(
        {
            (method, route.path)
            for route in walk(app.routes)
            for method in route.methods
            if method in {"POST", "PUT", "PATCH", "DELETE"}
        }
    )


def _fill(path: str) -> str:
    values = {"run_id": "run_0000000000000000", "case_id": "kariba-redd"}
    return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), "nope"), path)


@pytest.fixture
def cases_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway copy of ``cases/``: creating a case must never touch the real folder."""
    target = tmp_path / "cases"
    shutil.copytree(REPO_ROOT / "cases", target)
    monkeypatch.setattr(get_settings(), "cases_dir", target)
    monkeypatch.setattr(creator, "_queue_initial_run", lambda case: None)
    return target


def _audit(world: Any, action: str) -> list[AuditEventRow]:
    with world.sessions() as db:
        rows = list(
            db.execute(select(AuditEventRow).where(AuditEventRow.action == action)).scalars()
        )
        for row in rows:
            db.expunge(row)
        return rows


# --- acceptance 1: sign-in on every write -------------------------------------------------


class TestWritesRequireSignIn:
    def test_the_sweep_finds_the_app(self):
        assert len(_write_routes()) >= 15

    def test_every_write_route_refuses_an_anonymous_caller(self, tenant_world):
        """With AUTH_REQUIRED on (every deployed profile), no write answers anyone signed out.
        The sign-in routes themselves are the only exception, by design."""
        anonymous = TestClient(app, raise_server_exceptions=False)
        let_through = []
        for method, path in _write_routes():
            if path.startswith("/auth/"):
                continue
            response = anonymous.request(method, _fill(path), json={}, headers=ORIGIN)
            if response.status_code not in (401, 403):
                let_through.append(f"{method} {path} -> {response.status_code}")
        assert let_through == []

    def test_creating_a_case_needs_sign_in_even_with_auth_off(self, cases_dir):
        """POST /cases writes files, so it is never open, even in development (#51)."""
        assert get_settings().auth_required is False
        response = TestClient(app, raise_server_exceptions=False).post(
            "/cases", json=NEW_CASE, headers=ORIGIN
        )
        assert response.status_code in (401, 503)  # 503: no account store to sign in against
        assert not (cases_dir / "hardening-probe.yaml").exists()
        assert not list(cases_dir.glob("*hardening*"))

    def test_the_claims_workbench_is_open_only_with_auth_off(self, tenant_world, monkeypatch):
        """ACCEPTED in SECURITY.md: the claims routes write nothing and stay open in
        development. Pinned so a change to either side is noticed."""
        anonymous = TestClient(app, raise_server_exceptions=False)
        assert anonymous.post("/claims/analyze", json={}, headers=ORIGIN).status_code == 401
        monkeypatch.setattr(get_settings(), "auth_required", False)
        assert anonymous.post("/claims/analyze", json={}, headers=ORIGIN).status_code == 422


class TestProductionFailsClosed:
    def test_production_with_auth_off_refuses_to_start(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "production")
        monkeypatch.setattr(settings, "auth_required", False)
        with pytest.raises(ConfigurationError, match="AUTH_REQUIRED"), TestClient(app):
            pass

    def test_production_with_auth_on_starts(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "production")
        monkeypatch.setattr(settings, "auth_required", True)
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200

    @pytest.mark.parametrize("env", ["development", "test"])
    def test_auth_off_is_allowed_outside_production(self, env):
        class Settings:
            app_env = env
            auth_required = False

        refuse_unsafe_production(Settings())

    def test_no_shipped_configuration_combines_production_with_auth_off(self):
        """docker-compose, Helm, .env.example and the run scripts (D1)."""
        compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
        assert compose["services"]["api"]["environment"]["AUTH_REQUIRED"] == "true"
        values = yaml.safe_load(
            (REPO_ROOT / "infrastructure/helm/groundtruth/values.yaml").read_text(encoding="utf-8")
        )
        assert values["config"]["AUTH_REQUIRED"] == "true"
        env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        assert re.search(r"^AUTH_REQUIRED=true$", env_example, re.M)
        for script in ("run.sh", "run.ps1"):
            text = (REPO_ROOT / script).read_text(encoding="utf-8")
            assert "APP_ENV" not in text and "AUTH_REQUIRED" not in text, script


# --- acceptance 2: a submission budget ----------------------------------------------------


@pytest.fixture
def budget_of(monkeypatch):
    def set_budget(n: int) -> None:
        monkeypatch.setattr(get_settings(), "analysis_rate_limit", n)

    return set_budget


def _submit(client: TestClient, **extra: Any) -> Any:
    return client.post("/jobs", json={"case_id": "kariba-redd", "synthetic": True, **extra})


class TestSubmissionBudget:
    def test_the_default_is_20_in_10_minutes(self):
        settings = type(get_settings())()
        assert (settings.analysis_rate_limit, settings.analysis_rate_window_seconds) == (20, 600)
        assert API_ERROR_STATUS[ApiErrorCode.TOO_MANY_SUBMISSIONS] == 429

    def test_over_the_budget_is_a_429_with_retry_after(self, tenant_world, budget_of):
        budget_of(2)
        client = tenant_world.client("ref")
        before = REGISTRY.get_sample_value("gt_submissions_rate_limited_total", {"path": "job"})
        # The second is answered by the first's run (deduplicated): it still counts.
        assert _submit(client).status_code == 202
        assert _submit(client).status_code in (200, 202)
        refused = _submit(client)
        assert refused.status_code == 429
        body = refused.json()
        assert body["detail"]["code"] == "too_many_submissions"
        assert body["is_refusal"] is False  # a budget, not a scientific refusal
        assert int(refused.headers["retry-after"]) > 0
        after = REGISTRY.get_sample_value("gt_submissions_rate_limited_total", {"path": "job"})
        assert after == (before or 0) + 1

    def test_jobs_and_verify_share_one_budget(self, tenant_world, budget_of):
        budget_of(1)
        client = tenant_world.client("ref")
        assert _submit(client).status_code == 202
        response = client.post("/cases/kariba-redd/verify", json={})
        assert response.status_code == 429
        assert response.json()["detail"]["code"] == "too_many_submissions"

    def test_a_rejected_submission_does_not_spend_the_budget(self, tenant_world, budget_of):
        budget_of(1)
        client = tenant_world.client("ref")
        assert _submit(client, synthetic=False).status_code == 501  # refused before the budget
        assert _submit(client).status_code == 202

    def test_the_budget_is_per_user(self, budget_of):
        budget_of(1)
        limiter = submission_limiter()
        limiter.record_failure(("user-a", "analysis-submission"))
        assert limiter.retry_after(("user-a", "analysis-submission")) is not None
        assert limiter.retry_after(("user-b", "analysis-submission")) is None

    def test_a_refused_submission_is_audited_as_denied(self, tenant_world, budget_of):
        budget_of(1)
        client = tenant_world.client("ref")
        assert _submit(client).status_code == 202
        assert _submit(client).status_code == 429
        denied = [row for row in _audit(tenant_world, "run.start") if row.outcome == "denied"]
        assert len(denied) == 1
        assert denied[0].actor_user_id == tenant_world.user_ids["ref"]
        assert denied[0].resource_id == "kariba-redd"
        assert denied[0].details["reason"] == "rate_limited"


# --- acceptance 5: who requested which analysis -------------------------------------------


class TestAuditTrail:
    def test_a_queued_analysis_records_who_and_which_case(self, tenant_world):
        response = _submit(tenant_world.client("ref"))
        assert response.status_code == 202
        (row,) = [r for r in _audit(tenant_world, "run.start") if r.outcome == "success"]
        assert row.actor_user_id == tenant_world.user_ids["ref"]
        assert row.resource_id == response.json()["run_id"]
        assert row.details["case_id"] == "kariba-redd"

    def test_a_verify_run_records_who_and_which_case_even_when_refused(self, tenant_world):
        response = tenant_world.client("ref").post(
            "/cases/kariba-redd/verify", json={"min_donors": 500}
        )
        assert response.status_code == 422 and response.json()["is_refusal"] is True
        (row,) = _audit(tenant_world, "run.start")
        assert row.actor_user_id == tenant_world.user_ids["ref"]
        assert (row.details["case_id"], row.details["path"]) == ("kariba-redd", "verify")

    def test_creating_a_case_records_who_created_it(self, tenant_world, cases_dir):
        response = tenant_world.client("ref").post("/cases", json=NEW_CASE)
        assert response.status_code == 200, response.text
        (row,) = _audit(tenant_world, "case.create")
        assert row.actor_user_id == tenant_world.user_ids["ref"]
        assert row.resource_id == response.json()["case_id"]
        assert row.outcome == "success"


# --- acceptance 3: security headers on the API ----------------------------------------------


BASE = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
}


class TestApiSecurityHeaders:
    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app, raise_server_exceptions=False)

    def test_a_json_response_gets_the_strict_policy(self, client):
        response = client.get("/health")
        for name, value in BASE.items():
            assert response.headers[name] == value
        assert response.headers["content-security-policy"] == API_CSP
        assert "strict-transport-security" not in response.headers  # development speaks HTTP

    def test_errors_and_preflights_get_them_too(self, client):
        assert client.get("/no/such/route").headers["x-content-type-options"] == "nosniff"
        preflight = client.options(
            "/jobs",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
        )
        assert preflight.headers["x-frame-options"] == "DENY"

    def test_an_unexpected_500_gets_them_too(self, monkeypatch):
        module = importlib.import_module("groundtruth.platform.api.app")

        def boom() -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(module, "describe_engine", boom)
        response = TestClient(app, raise_server_exceptions=False).get("/health")
        assert response.status_code == 500
        assert response.headers["content-security-policy"] == API_CSP

    def test_the_interactive_docs_may_load_their_cdn_and_nothing_else(self, client):
        response = client.get("/docs")
        assert response.status_code == 200
        assert response.headers["content-security-policy"] == DOCS_CSP
        assert "https://cdn.jsdelivr.net" in DOCS_CSP and "frame-ancestors 'none'" in DOCS_CSP

    def test_hsts_is_sent_in_production_only(self, client, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "production")
        monkeypatch.setattr(settings, "auth_required", True)
        assert client.get("/health").headers["strict-transport-security"] == HSTS

    def test_a_header_the_route_set_is_kept(self):
        mini = FastAPI()

        @mini.get("/framed")
        def framed(response: Response) -> dict[str, bool]:
            response.headers["X-Frame-Options"] = "SAMEORIGIN"
            return {"ok": True}

        mini.add_middleware(SecurityHeadersMiddleware, production=lambda: False)
        response = TestClient(mini).get("/framed")
        assert response.headers["x-frame-options"] == "SAMEORIGIN"
        assert response.headers["x-content-type-options"] == "nosniff"
