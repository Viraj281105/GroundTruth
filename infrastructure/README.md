# GroundTruth Infrastructure & Deployment (`infrastructure`)

This directory maintains the containerization, orchestration, telemetry, and Kubernetes deployment specifications for GroundTruth 2.0.

The infrastructure is designed around a multi-tier, zero-trust architecture separating public web interfaces, secure RESTful API services, isolated compute workers, relational geospatial persistence, and comprehensive observability pipelines.

---

## Multi-Container Architecture (Docker Compose)

The standard runtime topology is orchestrated via the root `docker-compose.yml`, deploying five coordinated services with strict health checks and startup ordering:

```mermaid
flowchart TD
    Client([Client / Web Browser]) -->|HTTP :3000| Web[web: Next.js 14 App Router]
    Client -->|REST :8000| API[api: FastAPI HTTP Gateway]

    subgraph CorePlatform["GroundTruth Core Platform"]
        Web -->|Internal SSR :8000| API
        API -->|Read / Write| PG[(postgres: PostgreSQL 16 / PostGIS)]
        MigrateJob[migrate: One-Shot Alembic Job] -.->|Run First| PG
        Worker[worker: Asynchronous Compute Engine] -->|Claim Lease & Update| PG
    end

    subgraph Observability["Observability Stack (:3001)"]
        API -.->|OTLP Spans| OTel[otel-collector :4318]
        Worker -.->|OTLP Spans| OTel
        OTel --> Tempo[Tempo :3200 Tracing]
        OTel --> Prom[Prometheus :9090 Metrics]
        Prom --> Grafana[Grafana :3001 Dashboards]
        Tempo --> Grafana
    end

    PG -.->|Healthy Condition| MigrateJob
    MigrateJob -.->|Completed Successfully| API
    MigrateJob -.->|Completed Successfully| Worker
    API -.->|Healthy Condition| Web
```

### Services Breakdown

| Service | Image / Build Context | Ports | Healthcheck & Dependencies | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| `postgres` | `postgres:16-alpine` (or `postgis/postgis:16-3.4-alpine`) | Internal | `pg_isready -U groundtruth` (interval 5s, 10 retries) | Primary relational and geospatial store. |
| `migrate` | `infrastructure/docker/backend.Dockerfile` | None | Runs `python -m apps.worker.main --migrate --exit-when-idle` | One-shot migration container. Applies Alembic migrations before API/worker boot. |
| `api` | `infrastructure/docker/backend.Dockerfile` | `8000:8000` | Depends on `postgres` healthy and `migrate` completed. | FastAPI HTTP service serving verification endpoints, claims extraction, and tiles. |
| `worker` | `infrastructure/docker/backend.Dockerfile` | None | Depends on `postgres` healthy and `migrate` completed. | Long-running compute daemon claiming queued satellite and causal jobs. |
| `web` | `infrastructure/docker/web.Dockerfile` | `3000:3000` | Depends on `api` healthy. | Next.js 14 frontend serving multi-tenant dashboards and MapLibre maps. |

---

## PostGIS Spatial Extension Override

To enable dynamic Mapbox Vector Tile (MVT) generation for MapLibre GL boundary inspection (`/tiles/{z}/{x}/{y}.mvt`), switch the database image to PostGIS:

```bash
docker compose -f docker-compose.yml -f infrastructure/docker/postgis.override.yml up --build
```

`infrastructure/docker/postgis.override.yml` substitutes `postgis/postgis:16-3.4-alpine` for the standard PostgreSQL Alpine image, providing native geodesic spatial indexing (`ST_Intersects`, `ST_Area`, `ST_AsMVT`).

---

## Kubernetes & Helm Orchestration (`infrastructure/helm/groundtruth`)

GroundTruth provides production-grade Helm charts for Kubernetes deployments:

```mermaid
flowchart TD
    Ingress[Ingress Controller<br/>groundtruth.example.com] --> WebSvc[Web Service :3000]
    Ingress --> APISvc[API Service :8000]

    subgraph K8sCluster["Kubernetes Cluster (Namespace: groundtruth)"]
        WebSvc --> WebPods[Web Pods Deployment]
        APISvc --> APIPods[API Pods Deployment]
        WorkerPods[Worker Pods Deployment]
        
        Secret[Existing Secret:<br/>groundtruth-secrets] --> APIPods
        Secret --> WorkerPods
        ConfigMap[ConfigMap:<br/>groundtruth-config] --> APIPods
        ConfigMap --> WorkerPods
        ConfigMap --> WebPods
        
        MigrateJob[Migrate Job<br/>(helm.sh/hook: pre-install, pre-upgrade)]
    end

    subgraph ManagedDB["Cloud Managed Infrastructure"]
        CloudSQL[(AWS RDS / Cloud SQL PostgreSQL)]
    end

    APIPods --> CloudSQL
    WorkerPods --> CloudSQL
    MigrateJob --> CloudSQL
```

### Helm Chart Components (`infrastructure/helm/groundtruth/templates/`)
* `_helpers.tpl`: Common template labels, selector tags, and chart name definitions.
* `Chart.yaml`: Helm chart metadata (Version 2.0.0, API version v2).
* `values.yaml`: Default resource limits, image tags, replica counts, and config values.
* `api.yaml`: Deployment and ClusterIP service for the FastAPI backend.
* `worker.yaml`: Headless deployment for asynchronous compute workers.
* `web.yaml`: Deployment and ClusterIP service for the Next.js web application.
* `ingress.yaml`: TLS-enabled ingress routing rules for host domain routing.
* `configmap.yaml`: Non-sensitive environment variables (`AUTH_REQUIRED=true`, `OTEL_SERVICE_NAME=groundtruth`).
* `migrate-job.yaml`: Kubernetes pre-install and pre-upgrade hook executing Alembic migrations.

### Deploying with Helm
```bash
# 1. Create Kubernetes secret for sensitive credentials (DATABASE_URL, JWT secret)
kubectl create secret generic groundtruth-secrets \
  --from-literal=DATABASE_URL="postgresql+psycopg://user:pass@postgres-host/groundtruth"

# 2. Deploy Helm chart
helm upgrade --install groundtruth infrastructure/helm/groundtruth \
  --namespace groundtruth --create-namespace \
  --values infrastructure/helm/groundtruth/values.yaml
```

---

## Observability Stack (`infrastructure/observability`)

GroundTruth features an integrated observability stack deployed via `docker-compose.observability.yml`:

```mermaid
flowchart LR
    App[FastAPI / Worker Apps] -->|OTLP gRPC/HTTP :4318| OTel[OpenTelemetry Collector]
    OTel -->|Traces| Tempo[Grafana Tempo :3200]
    OTel -->|Metrics| Prom[Prometheus :9090]
    Tempo --> Grafana[Grafana Dashboards :3001]
    Prom --> Grafana
```

1. **OpenTelemetry Collector (`otel-collector.yaml`)**: Central intake on port `4318`. Receives distributed spans and metrics from FastAPI request handlers and Celery worker tasks.
2. **Grafana Tempo (`tempo.yaml`)**: High-scale distributed tracing backend. Stores end-to-end request traces across HTTP routes and background analysis execution.
3. **Prometheus (`prometheus.yml`)**: Scrapes worker queue latency, satellite processing throughput (megapixels/second), and database query timings.
4. **Grafana (`grafana/`)**: Pre-provisioned dashboards (`groundtruth.json`) displaying:
   * Verification job queue latency and stage durations (`claim` $\to$ `data` $\to$ `engine` $\to$ `record`).
   * Peak process memory vs the 22–24 GB hardware ceiling.
   * Synthetic control solver convergence times.
   * HTTP error rates categorized by contract error code.

### Metrics and alerts (#50)

The API (`api:9464`) and each worker (`worker:9465`) serve Prometheus metrics on internal
ports that are never published to the host. `prometheus.yml` scrapes both and loads
`alerts.yml`; `alerts.test.yml` unit-tests the rules (`promtool test rules`, run in CI). What
each metric and alert means: `docs/operations/README.md`, section 2.

### Launching Observability

Start the main stack first: Prometheus joins its `groundtruth` network to reach the metrics
ports.
```bash
docker compose -f infrastructure/observability/docker-compose.observability.yml up -d
```
Grafana is immediately available at `http://localhost:3001` (anonymous viewer enabled).

---

## CI/CD Pipeline & Automated Quality Gates

Every commit and pull request is audited through GitHub Actions workflows enforcing five automated gates:

```mermaid
flowchart LR
    Commit[Git Commit / PR] --> G1[1. Python Linter & Types<br/>Ruff + Mypy]
    Commit --> G2[2. Unit & Contract Tests<br/>Pytest + Coverage]
    Commit --> G3[3. Schema Freeze Gate<br/>test_openapi_snapshot]
    Commit --> G4[4. Web Unit & Component<br/>Vitest 542 Tests]
    Commit --> G5[5. End-to-End Suite<br/>Playwright Persona & A11y]

    G1 & G2 & G3 & G4 & G5 --> Merge[Approved for Merge]
```

1. **Python Linter & Static Types**: `ruff check` and `mypy` verify zero type regressions in `packages/groundtruth`.
2. **Python Unit & Contract Tests**: Comprehensive pytest suite asserting econometric estimators, units guards (`assert_not_index_to_carbon`), and failure status codes.
3. **OpenAPI Schema Freeze**: Asserts that `apps/web/src/lib/generated/openapi.json` matches the backend API specification. If routes or Pydantic models change without regenerating types, CI fails.
4. **Web Unit & Component Suite**: Vitest executes 57 test files (542 tests) validating design system components, state reducers, and chart formatters.
5. **Playwright End-to-End Suite**: Boots an isolated stack to test all 4 persona journeys, mobile viewports, cross-organization 403 barriers, and WCAG AA accessibility.

---

## Production Security & Secret Management

* **Zero Hardcoded Secrets**: Secrets never reside in source control or Helm charts. They are injected at runtime via environment variables or Kubernetes `existingSecret`.
* **Fail-Closed Authentication**: In all deployed configurations, `AUTH_REQUIRED=true` is enforced. Unauthenticated requests are rejected.
* **Cookie Protection**: In production (`AUTH_COOKIE_SECURE=true`), session tokens are transmitted strictly via `HttpOnly`, `SameSite=Lax`, `Secure` cookies.
* **CORS & CSRF Origin Gate**: `CsrfOriginMiddleware` strictly verifies the HTTP `Origin` header against `CORS_ALLOWED_ORIGINS` before allowing state-changing `POST`, `PATCH`, or `DELETE` requests.
