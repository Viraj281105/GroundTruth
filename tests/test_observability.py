"""Telemetry must be a safe no-op without configuration."""

from __future__ import annotations

import pytest

from groundtruth.observability import (
    instrument_fastapi,
    setup_telemetry,
    stage_span,
    telemetry_enabled,
)


def test_noop_without_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert setup_telemetry(object()) is False
    assert telemetry_enabled() is False
    assert instrument_fastapi(object()) is False


def test_stage_span_passthrough() -> None:
    ran = False
    with stage_span("estimate", case_id="c1"):
        ran = True
    assert ran
