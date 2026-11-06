"""Optional OpenTelemetry observability (no-op unless configured)."""

from groundtruth.observability.telemetry import (
    instrument_fastapi,
    setup_telemetry,
    stage_span,
    telemetry_enabled,
)

__all__ = ["instrument_fastapi", "setup_telemetry", "stage_span", "telemetry_enabled"]
