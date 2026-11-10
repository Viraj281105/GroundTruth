"""Infrastructure, security, Alembic migration chain, and container/Helm QA tests."""

from __future__ import annotations

import ast
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

import pytest
import yaml

from groundtruth.platform.auth.csrf import CsrfOriginMiddleware
from groundtruth.platform.auth.passwords import (
    check_policy,
    dummy_verify,
    hash_password,
    needs_rehash,
    verify_password,
)
from groundtruth.platform.auth.sessions import COOKIE_NAME
from groundtruth.platform.config import REPO_ROOT, Settings

# ---------------------------------------------------------------------------
# 1. Settings & Honest Capability / Security Posture Inspection
# ---------------------------------------------------------------------------


def test_settings_honest_capability_properties(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("SENTINEL_HUB_CLIENT_ID", raising=False)
    monkeypatch.delenv("GLOBAL_FOREST_WATCH_API_KEY", raising=False)

    s_default = Settings(
        gee_service_account_json=None,
        sentinel_hub_client_id=None,
        global_forest_watch_api_key=None,
    )
    assert s_default.real_eo_ingestion_implemented is False
    assert s_default.deployment_tenancy_mode == "single-tenant"
    assert s_default.earth_observation_configured is False

    s_with_eo = Settings(
        gee_service_account_json='{"type": "service_account"}',
    )
    assert s_with_eo.earth_observation_configured is True
    # Even when EO credentials are supplied, live ingestion remains honestly reported as False
    assert s_with_eo.real_eo_ingestion_implemented is False


def test_settings_validate_security_posture_flags_production_risks() -> None:
    prod_insecure = Settings(
        app_env="production",
        auth_required=False,
        auth_cookie_secure=False,
        gee_service_account_json=None,
        sentinel_hub_client_id=None,
        global_forest_watch_api_key=None,
    )
    warnings = prod_insecure.validate_security_posture()
    assert any("AUTH_REQUIRED is false in production" in w for w in warnings)
    assert any("AUTH_COOKIE_SECURE is false in production" in w for w in warnings)
    assert any("Earth Observation credentials are not configured" in w for w in warnings)

    prod_hardened = Settings(
        app_env="production",
        auth_required=True,
        auth_cookie_secure=True,
        sentinel_hub_client_id="sh-client-123",
    )
    assert prod_hardened.validate_security_posture() == []


def test_settings_cors_rejects_wildcard() -> None:
    with pytest.raises(ValueError, match="never '\\*'"):
        Settings(cors_allowed_origins="http://localhost:3000, *")


# ---------------------------------------------------------------------------
# 2. Password Hashing, Policy & Constant-Time Dummy Verification
# ---------------------------------------------------------------------------


def test_password_hashing_and_dummy_verification() -> None:
    secret = "CorrectHorseBatteryStaple!99"
    digest = hash_password(secret)
    assert digest.startswith("scrypt$")
    assert verify_password(secret, digest) is True
    assert verify_password("WrongHorseBatteryStaple!99", digest) is False
    assert verify_password(secret, "malformed$hash") is False
    assert needs_rehash(digest) is False
    assert needs_rehash("scrypt$1024$8$1$YWJj$ZGVm") is True

    # Constant-time dummy verification for non-existent accounts must not raise
    dummy_verify("any-attempted-password-12345")


def test_password_policy_enforcement() -> None:
    assert check_policy("short", "user@example.org") is not None
    assert check_policy("password123", "user@example.org") is not None
    assert check_policy("user@example.org", "user@example.org") is not None
    assert check_policy("A_Strong_Unique_Passphrase_2026!", "user@example.org") is None


# ---------------------------------------------------------------------------
# 3. CSRF Origin Middleware Protection on Mutating Requests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_csrf_middleware_blocks_untrusted_origin_on_cookie_post() -> None:
    called = False

    async def dummy_app(scope: Any, receive: Any, send: Any) -> None:
        nonlocal called
        called = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = CsrfOriginMiddleware(dummy_app, allowed_origins=lambda: ["http://localhost:3000"])

    sent_events: list[MutableMapping[str, Any]] = []

    async def send(event: MutableMapping[str, Any]) -> None:
        sent_events.append(event)

    async def receive() -> MutableMapping[str, Any]:
        return {"type": "http.request", "body": b""}

    # 1. Unsafe POST with session cookie and malicious origin -> 403
    bad_scope: MutableMapping[str, Any] = {
        "type": "http",
        "method": "POST",
        "headers": [
            (b"cookie", f"{COOKIE_NAME}=tok123".encode()),
            (b"origin", b"https://evil.example.com"),
        ],
    }
    await middleware(bad_scope, receive, send)
    assert called is False
    assert sent_events[0]["status"] == 403
    assert b"csrf_origin_rejected" in sent_events[1]["body"]

    # 2. Unsafe POST with session cookie and allowed origin -> passes through
    sent_events.clear()
    good_scope: MutableMapping[str, Any] = {
        "type": "http",
        "method": "POST",
        "headers": [
            (b"cookie", f"{COOKIE_NAME}=tok123".encode()),
            (b"origin", b"http://localhost:3000"),
        ],
    }
    await middleware(good_scope, receive, send)
    assert called is True
    assert sent_events[0]["status"] == 200


# ---------------------------------------------------------------------------
# 4. Alembic Migration Chain Integrity (0001 -> 0007)
# ---------------------------------------------------------------------------


def _extract_migration_metadata(path: Path) -> tuple[str | None, str | None]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    revision: str | None = None
    down_revision: str | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "revision":
                    revision = ast.literal_eval(node.value)
                elif isinstance(target, ast.Name) and target.id == "down_revision":
                    down_revision = ast.literal_eval(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "revision" and node.value is not None:
                revision = ast.literal_eval(node.value)
            elif node.target.id == "down_revision" and node.value is not None:
                down_revision = ast.literal_eval(node.value)
    return revision, down_revision


def test_alembic_migration_chain_integrity() -> None:
    versions_dir = (
        REPO_ROOT
        / "packages"
        / "groundtruth"
        / "src"
        / "groundtruth"
        / "platform"
        / "store"
        / "migrations"
        / "versions"
    )
    expected_files = [
        "0001_initial_schema.py",
        "0002_add_engine_contract_version.py",
        "0003_job_request_and_lease.py",
        "0004_run_listing_indexes.py",
        "0005_job_stage.py",
        "0006_auth_users_and_sessions.py",
        "0007_tenancy.py",
    ]
    for fname in expected_files:
        assert (versions_dir / fname).is_file(), f"Missing migration file: {fname}"

    chain: list[tuple[str | None, str | None]] = [
        _extract_migration_metadata(versions_dir / fname) for fname in expected_files
    ]
    assert chain[0][1] is None, "First migration 0001 must have down_revision = None"
    for idx in range(1, len(chain)):
        prev_rev = chain[idx - 1][0]
        curr_rev, curr_down = chain[idx]
        assert curr_rev is not None
        assert curr_down == prev_rev, (
            f"Broken Alembic chain at {expected_files[idx]}: "
            f"down_revision={curr_down!r} != previous revision={prev_rev!r}"
        )

    head_file_stem = Path(expected_files[-1]).stem
    head_revision = chain[-1][0]
    assert head_file_stem == "0007_tenancy"
    assert head_revision in {"0007", "0007_tenancy"}


# ---------------------------------------------------------------------------
# 5. Docker Compose & Helm Chart Structural Validation
# ---------------------------------------------------------------------------


def test_docker_compose_and_helm_chart_structure() -> None:
    compose_path = REPO_ROOT / "docker-compose.yml"
    compose_data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = compose_data.get("services", {})
    assert {"postgres", "migrate", "api", "worker", "web"}.issubset(services.keys())
    # Migrations run once, in a one-shot service, before anything serves or claims jobs.
    assert "--migrate" in services["migrate"]["command"]
    assert "--migrate" not in services["worker"].get("command", [])
    for waiting in ("api", "worker"):
        assert services[waiting]["depends_on"]["migrate"] == {
            "condition": "service_completed_successfully"
        }

    helm_root = REPO_ROOT / "infrastructure" / "helm" / "groundtruth"
    chart_data = yaml.safe_load((helm_root / "Chart.yaml").read_text(encoding="utf-8"))
    assert chart_data["name"] == "groundtruth"
    assert chart_data["apiVersion"] == "v2"

    values_data = yaml.safe_load((helm_root / "values.yaml").read_text(encoding="utf-8"))
    assert {"api", "worker", "web", "existingSecret"}.issubset(values_data.keys())

    migrate_job_template = (helm_root / "templates" / "migrate-job.yaml").read_text(
        encoding="utf-8"
    )
    assert "kind: Job" in migrate_job_template
    assert "pre-install,pre-upgrade" in migrate_job_template
    assert '"--migrate"' in migrate_job_template
    assert "runAsNonRoot: true" in migrate_job_template
