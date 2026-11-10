"""Monitoring and structured logging (#50).

* every log line about an analysis carries ``run_id``, ``case_id`` and ``stage``, and every
  JSON line has those keys;
* no credential reaches a log line, whatever part of the record carries it;
* the four metrics move when their events happen, a refusal is never counted as a failure, and
  no metric label can carry a user, an email or a case;
* the alert rules page on failures and backlog, never on refusals, and only name metrics that
  exist; Prometheus scrapes the internal ports, which nothing publishes.

The alert expressions themselves are executed by ``promtool test rules`` in CI
(``infrastructure/observability/alerts.test.yml``).
"""

from __future__ import annotations

import io
import json
import logging
import re
import socket
import urllib.request
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from prometheus_client import generate_latest
from prometheus_client.parser import text_string_to_metric_families
from pydantic import SecretStr

from groundtruth.contracts.errors import DataUnavailableError
from groundtruth.logging import (
    ALWAYS_PRESENT,
    PLAIN_FORMAT,
    REDACTION_FAILED,
    ContextFilter,
    JsonFormatter,
    RedactingFormatter,
    get_logger,
    log_context,
)
from groundtruth.platform import metrics
from groundtruth.platform.api.app import app
from groundtruth.platform.config import REPO_ROOT, get_settings
from groundtruth.platform.jobs.queue import JobQueue
from groundtruth.platform.jobs.worker import Worker, default_resolve_access
from groundtruth.platform.metrics import REGISTRY
from groundtruth.platform.redaction import redact_secrets

SECRET = "sk-observability-secret-0123456789"
DB_PASSWORD = "pa55w0rd-in-the-dsn"
OBSERVABILITY = REPO_ROOT / "infrastructure" / "observability"


def _parse(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def _capture() -> tuple[io.StringIO, logging.Handler]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter(redact_secrets))
    handler.addFilter(ContextFilter())
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    return stream, handler


def _sample(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def _run_one_job(world: Any, **resolve: Any) -> None:
    resolve_access = resolve.get("resolve_access") or default_resolve_access()
    Worker(JobQueue(world.sessions), resolve_access=resolve_access, poll_interval=0.01).run(
        exit_when_idle=True, max_jobs=1
    )


def _queue(world: Any, **body: Any) -> str:
    response = world.client("ref").post(
        "/jobs", json={"case_id": "kariba-redd", "synthetic": True, **body}
    )
    assert response.status_code in (200, 202), response.text
    return str(response.json()["run_id"])


# --- acceptance 1: run_id, case_id and stage on every line --------------------------------


class TestEveryLineCarriesItsAnalysis:
    def test_every_line_of_a_job_names_its_run_case_and_stage(self, tenant_world):
        run_id = _queue(tenant_world)
        stream, handler = _capture()
        try:
            _run_one_job(tenant_world)
        finally:
            logging.getLogger().removeHandler(handler)
        lines = _parse(stream)
        start = next(i for i, e in enumerate(lines) if e["message"] == "job claimed")
        end = max(i for i, e in enumerate(lines) if e["message"].startswith("job finished"))
        job_lines = lines[start : end + 1]
        assert len(job_lines) >= 6
        for entry in job_lines:
            assert (entry["run_id"], entry["case_id"]) == (run_id, "kariba-redd"), entry
            assert entry["stage"], entry
        assert {"claim", "data", "engine", "record", "done"} <= {e["stage"] for e in job_lines}

    def test_every_json_line_has_the_keys_even_outside_an_analysis(self):
        stream, handler = _capture()
        try:
            get_logger("test").info("not about any analysis")
        finally:
            logging.getLogger().removeHandler(handler)
        (entry,) = _parse(stream)
        assert all(key in entry and entry[key] is None for key in ALWAYS_PRESENT)

    def test_a_verify_run_logs_its_run_case_stage_and_request(self, tenant_world):
        stream, handler = _capture()
        try:
            response = tenant_world.client("ref").post("/cases/kariba-redd/verify", json={})
        finally:
            logging.getLogger().removeHandler(handler)
        assert response.status_code == 200
        (finished,) = [e for e in _parse(stream) if e["message"].startswith("verify finished")]
        assert finished["run_id"] == response.json()["run_id"]
        assert (finished["case_id"], finished["stage"]) == ("kariba-redd", "record")
        assert finished["request_id"] == response.headers["x-request-id"]


# --- acceptance 4: no credential in any log line -------------------------------------------


class TestNoCredentialInAnyLine:
    @pytest.fixture(autouse=True)
    def _secrets(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "anthropic_api_key", SecretStr(SECRET))
        monkeypatch.setattr(
            settings, "database_url", f"postgresql+psycopg://groundtruth:{DB_PASSWORD}@db/gt"
        )

    @staticmethod
    def _emit(formatter: logging.Formatter) -> str:
        """Log a credential through every part of a record, as a deployed handler would."""
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(formatter)
        handler.addFilter(ContextFilter())
        log = logging.getLogger("groundtruth.test.redaction")
        log.addHandler(handler)
        log.propagate = False
        try:
            log.warning("key in the message %s", SECRET)
            log.warning("dsn %s", f"postgresql://u:{DB_PASSWORD}@db/gt")
            log.warning("header Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345")
            log.warning("pem -----BEGIN PRIVATE KEY-----\nMIIEvQ\n-----END PRIVATE KEY-----")
            with log_context(case_id=f"case-{SECRET}"):
                log.warning("context field")
            try:
                raise RuntimeError(f"provider said no to {SECRET}")
            except RuntimeError:
                log.exception("with a traceback")
        finally:
            log.removeHandler(handler)
            log.propagate = True
        return stream.getvalue()

    @pytest.mark.parametrize(
        "formatter",
        [
            JsonFormatter(redact_secrets),
            RedactingFormatter(PLAIN_FORMAT, redact_secrets),
        ],
        ids=["json", "plain"],
    )
    def test_secrets_tokens_keys_and_passwords_never_reach_the_output(self, formatter):
        out = self._emit(formatter)
        for leak in (SECRET, DB_PASSWORD, "abcdefghijklmnopqrstuvwxyz012345", "MIIEvQ"):
            assert leak not in out
        assert "[redacted]" in out
        assert "provider said no to" in out  # the rest of the line survives

    def test_a_redactor_that_fails_withholds_the_line(self):
        def broken(text: str) -> str:
            raise ValueError("cannot redact")

        record = logging.LogRecord("x", logging.INFO, __file__, 1, f"has {SECRET}", None, None)
        assert json.loads(JsonFormatter(broken).format(record))["message"] == REDACTION_FAILED
        assert RedactingFormatter("%(message)s", broken).format(record) == REDACTION_FAILED

    def test_both_processes_configure_logging_with_redaction(self):
        api = (REPO_ROOT / "apps/api/main.py").read_text(encoding="utf-8")
        worker = (
            REPO_ROOT / "packages/groundtruth/src/groundtruth/platform/jobs/entrypoint.py"
        ).read_text(encoding="utf-8")
        for source in (api, worker):
            assert re.search(
                r"configure_logging\([^)]*json_output=True[^)]*redact=redact_secrets", source, re.S
            )


# --- acceptance 2: the four metrics -----------------------------------------------------------


class TestMetricsMove:
    def test_a_job_records_each_stage_duration_and_its_outcome(self, tenant_world):
        _queue(tenant_world)
        stages = {s: _sample("gt_stage_duration_seconds_count", stage=s) for s in metrics.STAGES}
        answered = sum(
            _sample("gt_runs_finished_total", outcome=o, path="job")
            for o in ("completed", "refused")
        )
        _run_one_job(tenant_world)
        for stage, before in stages.items():
            assert _sample("gt_stage_duration_seconds_count", stage=stage) == before + 1, stage
        after = sum(
            _sample("gt_runs_finished_total", outcome=o, path="job")
            for o in ("completed", "refused")
        )
        assert after == answered + 1

    def test_a_refusal_counts_as_refused_never_as_a_failure(self, tenant_world):
        _queue(tenant_world, min_donors=500)
        before = {
            o: _sample("gt_runs_finished_total", outcome=o, path="job") for o in metrics.OUTCOMES
        }
        _run_one_job(tenant_world)
        changed = {
            o: _sample("gt_runs_finished_total", outcome=o, path="job") - v
            for o, v in before.items()
            if _sample("gt_runs_finished_total", outcome=o, path="job") != v
        }
        assert changed == {"refused": 1}

    def test_data_that_is_unavailable_goes_back_to_the_queue_and_is_counted_so(self, tenant_world):
        _queue(tenant_world)

        def unavailable(request: Any) -> Any:
            raise DataUnavailableError("upstream is down")

        before = _sample("gt_runs_finished_total", outcome="retried", path="job")
        _run_one_job(tenant_world, resolve_access=unavailable)
        assert _sample("gt_runs_finished_total", outcome="retried", path="job") == before + 1

    def test_the_verify_path_is_counted_separately(self, tenant_world):
        before = _sample("gt_runs_finished_total", outcome="refused", path="verify")
        response = tenant_world.client("ref").post(
            "/cases/kariba-redd/verify", json={"min_donors": 500}
        )
        assert response.status_code == 422
        assert _sample("gt_runs_finished_total", outcome="refused", path="verify") == before + 1

    def test_a_stored_result_answering_a_submission_is_a_cache_hit(self, tenant_world):
        hits = _sample("gt_cache_requests_total", cache="result", result="hit")
        misses = _sample("gt_cache_requests_total", cache="result", result="miss")
        _queue(tenant_world)
        _run_one_job(tenant_world)
        again = tenant_world.client("ref").post(
            "/jobs", json={"case_id": "kariba-redd", "synthetic": True}
        )
        assert again.json()["from_cache"] is True
        assert _sample("gt_cache_requests_total", cache="result", result="miss") == misses + 1
        assert _sample("gt_cache_requests_total", cache="result", result="hit") == hits + 1

    def test_the_queue_depth_is_read_from_the_database(self, tenant_world):
        _queue(tenant_world)
        _queue(tenant_world, min_donors=40)
        metrics.register_queue_collector(tenant_world.sessions)
        try:
            assert _sample("gt_queue_metrics_up") == 1
            assert _sample("gt_queue_jobs", state="queued") == 2
            assert _sample("gt_queue_jobs", state="running") == 0
            assert _sample("gt_queue_oldest_queued_seconds") >= 0
        finally:
            metrics.unregister_queue_collector()

    def test_a_failed_queue_read_says_so_instead_of_reporting_zero(self):
        def broken() -> Any:
            raise RuntimeError("database down")

        families = list(metrics.QueueCollector(broken).collect())
        assert [f.name for f in families] == ["gt_queue_metrics_up"]
        assert families[0].samples[0].value == 0


class TestMetricLabelsCarryNoUserData:
    def test_every_label_and_value_comes_from_a_fixed_list(self, tenant_world):
        _queue(tenant_world)
        _run_one_job(tenant_world)
        metrics.register_queue_collector(tenant_world.sessions)
        try:
            text = generate_latest(REGISTRY).decode("utf-8")
        finally:
            metrics.unregister_queue_collector()
        families = [f for f in text_string_to_metric_families(text) if f.name.startswith("gt_")]
        assert {f.name for f in families} >= {
            "gt_stage_duration_seconds",
            "gt_runs_finished",
            "gt_cache_requests",
            "gt_queue_jobs",
            "gt_queue_oldest_queued_seconds",
            "gt_queue_metrics_up",
        }
        for family in families:
            for sample in family.samples:
                for label, value in sample.labels.items():
                    if label == "le":
                        continue
                    assert label in metrics.LABEL_VALUES, (family.name, label)
                    assert value in (*metrics.LABEL_VALUES[label], metrics.OTHER), (label, value)

    def test_the_exposition_has_no_email_case_or_secret(self, tenant_world, monkeypatch):
        monkeypatch.setattr(get_settings(), "anthropic_api_key", SecretStr(SECRET))
        _queue(tenant_world)
        text = generate_latest(REGISTRY).decode("utf-8")
        assert "@" not in text
        assert "kariba" not in text and SECRET not in text
        assert "run_" not in text.replace("gt_runs_", "")

    def test_an_unknown_label_value_is_recorded_as_other(self):
        before = _sample("gt_runs_finished_total", outcome="other", path="job")
        metrics.record_outcome("someone@example.org")
        assert _sample("gt_runs_finished_total", outcome="other", path="job") == before + 1


class TestMetricsServer:
    @staticmethod
    def _free_port() -> int:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])

    def test_metrics_are_served_on_their_own_port(self):
        port = self._free_port()
        assert metrics.start_metrics_server(port, "127.0.0.1") is True
        body = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=5).read()
        assert b"gt_runs_finished_total" in body

    def test_port_zero_turns_them_off_and_a_busy_port_is_not_fatal(self):
        assert metrics.start_metrics_server(0, "127.0.0.1") is False
        with socket.socket() as busy:
            busy.bind(("127.0.0.1", 0))
            busy.listen()
            assert metrics.start_metrics_server(busy.getsockname()[1], "127.0.0.1") is False

    def test_the_public_api_port_does_not_serve_them(self):
        assert TestClient(app).get("/metrics").status_code == 404

    def test_metrics_listen_on_localhost_unless_a_deployment_says_otherwise(self):
        assert type(get_settings())().metrics_bind_address == "127.0.0.1"


# --- acceptance 3: alerts, and where Prometheus looks ----------------------------------------


def _load(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def alert_rules() -> list[dict[str, Any]]:
    groups = _load(OBSERVABILITY / "alerts.yml")["groups"]
    return [rule for group in groups for rule in group["rules"]]


class TestAlertRules:
    def test_failure_rate_and_backlog_page(self, alert_rules):
        alerts = {r["alert"]: r for r in alert_rules if "alert" in r}
        for name in (
            "GroundTruthJobFailureRateHigh",
            "GroundTruthQueueBacklog",
            "GroundTruthQueueStale",
        ):
            assert alerts[name]["labels"]["severity"] == "page", name

    def test_no_refusal_alert_ever_pages(self, alert_rules):
        alerts = {r["alert"]: r for r in alert_rules if "alert" in r}
        refusal = [n for n in alerts if "Refusal" in n]
        assert sorted(refusal) == ["GroundTruthRefusalRateShift", "GroundTruthRefusalRateZero"]
        for name in refusal:
            assert alerts[name]["labels"]["severity"] == "warning"
        recorded = {r["record"]: r["expr"] for r in alert_rules if "record" in r}
        for name, rule in alerts.items():
            if rule["labels"]["severity"] == "page":
                expr = rule["expr"]
                for record, record_expr in recorded.items():
                    if record in expr:
                        expr += record_expr
                assert 'outcome="refused"' not in expr, name

    def test_refusals_are_not_in_the_failure_rate(self, alert_rules):
        recorded = {r["record"]: r["expr"] for r in alert_rules if "record" in r}
        assert "refused" not in recorded["gt:runs_malfunctioned:increase15m"]

    def test_every_alert_has_a_severity_and_a_runbook(self, alert_rules):
        for rule in alert_rules:
            if "alert" in rule:
                assert rule["labels"]["severity"] in ("page", "warning"), rule["alert"]
                assert rule["annotations"]["runbook"].startswith("docs/operations/README.md#")

    def test_every_metric_the_rules_name_exists(self, alert_rules, tenant_world):
        metrics.register_queue_collector(tenant_world.sessions)
        try:
            text = generate_latest(REGISTRY).decode("utf-8")
        finally:
            metrics.unregister_queue_collector()
        exported = {
            sample.name for f in text_string_to_metric_families(text) for sample in f.samples
        }
        named = {m for rule in alert_rules for m in re.findall(r"\bgt_[a-z_]+\b", rule["expr"])}
        assert named, "the rules name no metrics"
        assert named <= exported, named - exported

    def test_the_alert_unit_tests_cover_every_alert(self, alert_rules):
        tested = {
            case["alertname"]
            for test in _load(OBSERVABILITY / "alerts.test.yml")["tests"]
            for case in test.get("alert_rule_test", [])
        }
        assert {r["alert"] for r in alert_rules if "alert" in r} <= tested


class TestScrapeConfiguration:
    def test_prometheus_loads_the_rules_and_scrapes_both_internal_ports(self):
        config = _load(OBSERVABILITY / "prometheus.yml")
        assert config["rule_files"] == ["/etc/prometheus/alerts.yml"]
        jobs = {job["job_name"]: job for job in config["scrape_configs"]}
        assert jobs["groundtruth-api"]["static_configs"][0]["targets"] == ["api:9464"]
        assert jobs["groundtruth-worker"]["dns_sd_configs"][0]["port"] == 9465
        compose = _load(OBSERVABILITY / "docker-compose.observability.yml")
        volumes = compose["services"]["prometheus"]["volumes"]
        assert "./alerts.yml:/etc/prometheus/alerts.yml:ro" in volumes

    def test_the_metrics_ports_are_never_published(self):
        compose = _load(REPO_ROOT / "docker-compose.yml")
        for service, port in (("api", "9464"), ("worker", "9465")):
            spec = compose["services"][service]
            assert port in spec["expose"]
            assert not any(port in str(p) for p in spec.get("ports", [])), service
            assert spec["environment"]["METRICS_BIND_ADDRESS"] == "0.0.0.0"

    def test_helm_declares_the_ports_and_routes_nothing_to_them(self):
        helm = REPO_ROOT / "infrastructure/helm/groundtruth"
        values = _load(helm / "values.yaml")
        settings = type(get_settings())()
        assert values["api"]["metricsPort"] == settings.api_metrics_port == 9464
        assert values["worker"]["metricsPort"] == settings.worker_metrics_port == 9465
        ingress = (helm / "templates/ingress.yaml").read_text(encoding="utf-8")
        assert "metricsPort" not in ingress
        api = (helm / "templates/api.yaml").read_text(encoding="utf-8")
        service = api.split("kind: Service", 1)[1]
        assert "metricsPort" not in service  # no Service routes to the metrics port
