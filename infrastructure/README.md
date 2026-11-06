# infrastructure

Deployment and runtime infrastructure. **Owner: Bhumi.**

| Path | Contents | Status |
| --- | --- | --- |
| `observability/` | Compose override: OTel collector, Tempo, Prometheus, Grafana + starter dashboard | Implemented (not run) |
| `helm/groundtruth/` | Helm chart: api, worker, web, ingress, configmap, `existingSecret` reference | Implemented (`helm` not installed; lint/template unverified) |
| `docker/` | Container images for API, worker, web | Planned |

See [`docs/observability.md`](../docs/observability.md) for telemetry wiring and
[`ADR-010`](../docs/decisions/ADR-010-deployment.md) for deployment decisions.
