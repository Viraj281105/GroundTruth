# Observability

Telemetry is optional OpenTelemetry (traces + metrics over OTLP). It is a no-op
unless the `opentelemetry-*` packages are installed **and**
`OTEL_EXPORTER_OTLP_ENDPOINT` is set (e.g. `http://otel-collector:4318`).

Packages: `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`,
`opentelemetry-instrumentation-fastapi`.

## Wiring (platform/api/app.py)

After the `app` is created, add these two lines:

```python
from groundtruth.observability import setup_telemetry
setup_telemetry(app)
```

Analysis stages: `with stage_span("estimate", case_id=cid): ...`
(`from groundtruth.observability import stage_span`).

## Local stack

```
docker compose -f docker-compose.yml -f infrastructure/observability/docker-compose.observability.yml up
```

Grafana http://localhost:3001 (anonymous viewer), Prometheus :9090, Tempo :3200.
Set `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318` on api and worker.
The dashboard's job-duration panel expects a `groundtruth_job_duration_milliseconds`
histogram, which the worker must record separately.
