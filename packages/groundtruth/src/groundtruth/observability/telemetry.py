"""OpenTelemetry setup. All opentelemetry imports are lazy and optional."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

_enabled = False


def telemetry_enabled() -> bool:
    """Whether :func:`setup_telemetry` configured exporters in this process."""
    return _enabled


def setup_telemetry(app: Any = None) -> bool:
    """Configure OTLP tracing and metrics; return True if active.

    No-op when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is unset or the opentelemetry
    packages are not installed. Standard ``OTEL_*`` env vars are honoured by the SDK.
    """
    global _enabled
    if _enabled:
        if app is not None:
            instrument_fastapi(app)
        return True
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return False
    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.info("OTEL endpoint set but opentelemetry packages missing; telemetry off")
        return False
    resource = Resource.create({"service.name": os.environ.get("OTEL_SERVICE_NAME", "groundtruth")})
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)
    reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))
    _enabled = True
    if app is not None:
        instrument_fastapi(app)
    return True


def instrument_fastapi(app: Any) -> bool:
    """Instrument a FastAPI app if telemetry is active and the package is installed."""
    if not _enabled:
        return False
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except ImportError:
        return False
    FastAPIInstrumentor.instrument_app(app)
    return True


@contextmanager
def stage_span(stage: str, **attributes: Any) -> Iterator[None]:
    """Span around an analysis stage; a plain pass-through when telemetry is off."""
    if not _enabled:
        yield
        return
    from opentelemetry import trace

    tracer = trace.get_tracer("groundtruth.analysis")
    with tracer.start_as_current_span(f"stage.{stage}") as span:
        for key, value in attributes.items():
            span.set_attribute(key, value)
        yield
