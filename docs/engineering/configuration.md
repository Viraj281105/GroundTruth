# Configuration Specification

**Module**: `groundtruth.platform.config.Settings` (pydantic-settings)  
**Philosophy**: 12-Factor App Environment Configuration with Zero Engine Bleed.

All runtime configuration in GroundTruth 2.0 is driven by environment variables read once through a strongly typed Pydantic v2 `Settings` class. No secrets are baked into container images, and no credentials live in git.

```mermaid
flowchart TD
    Env[".env / System Environment Variables"] --> SettingsClass["Platform Settings (pydantic-settings)"]
    
    subgraph PlatformUsage["Platform Subsystems"]
        SettingsClass --> AuthSvc["Authentication & Sessions<br/>(AUTH_REQUIRED, COOKIE_SECURE)"]
        SettingsClass --> DBSvc["Database Engine<br/>(DATABASE_URL)"]
        SettingsClass --> QueueSvc["Job Queue Dispatcher<br/>(REDIS_URL, WORKER_CONCURRENCY)"]
        SettingsClass --> StorageSvc["Storage Backend<br/>(STORAGE_BACKEND, S3_BUCKET)"]
        SettingsClass --> ExtSvc["External Providers<br/>(PLANETARY_COMPUTER_KEY, OPENAI_API_KEY)"]
    end

    subgraph EngineIsolation["Pure Engine Boundary"]
        PlatformUsage --> RequestBuilder["CaseDefinition.to_request()"]
        RequestBuilder --> PureReq["AnalysisRequest<br/>(Self-Contained Pydantic Object)"]
        PureReq --> Engine["Analytical Engine (NumPy)<br/><i>Engine Reads ZERO Environment Variables</i>"]
    end
```

![Auditor Dashboard](../product/screens/auditor-dashboard.png)

---

## 1. Core Configuration Invariants

1. **The Engine Reads No Configuration**: The analytical engine reads zero environment variables. Every parameter needed for analysis arrives explicitly via `AnalysisRequest`. This guarantees that an analysis can be replayed years later with guaranteed reproducibility.
2. **Secrets are Strongly Typed**: Sensitive values use Pydantic's `SecretStr`. They cannot be printed, serialized to JSON, or dumped in logs. `groundtruth doctor` checks for credential presence without leaking string content.
3. **No Silent Fallback**: If an external provider is explicitly requested (e.g., Earth Engine or Planetary Computer) but credentials are missing, the system raises an explicit configuration error rather than silently substituting simulated data.

---

## 2. Configuration Parameters Matrix

### 2.1 Multi-Tenancy & Authentication

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `AUTH_REQUIRED` | `bool` | `true` | Enforces authentication on all mutating endpoints (`/jobs`, `/cases/{id}/verify`). |
| `AUTH_ALLOW_REGISTRATION` | `bool` | `false` | When `false`, only signed-in administrators can register new tenant accounts. |
| `AUTH_COOKIE_SECURE` | `bool` | `true` | Enforces `Secure` flag on session cookies (must be `true` in production HTTPS). |
| `AUTH_SESSION_DAYS` | `int` | `7` | Active session and cookie lifetime in days. |
| `CORS_ALLOWED_ORIGINS` | `str` | `http://localhost:3000` | Comma-separated list of exact allowed browser origins (scheme, host, port). |

### 2.2 Storage & Persistence

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `DATABASE_URL` | `SecretStr` | — | PostgreSQL connection string (`postgresql+psycopg://user:pass@host/db`). |
| `GROUNDTRUTH_STORAGE_BACKEND` | `str` | `development` | Storage driver selection: `development` (local POSIX) or `production` (S3). |
| `GROUNDTRUTH_DEV_STORAGE_PATH` | `Path` | `./data/storage` | Local directory root for four-tier storage. |
| `AWS_S3_BUCKET` | `str` | `groundtruth-evidence` | Target S3 bucket for cloud storage backend. |

### 2.3 Compute & Workstation Performance

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `GROUNDTRUTH_WORKERS` | `int` | `8` | Number of concurrent worker processes (empirically tuned sweet spot). |
| `GROUNDTRUTH_MAX_MEMORY_GB` | `int` | `24` | Memory allocation budget ceiling in gigabytes. |
| `GROUNDTRUTH_CHUNK_WINDOW_SIZE`| `int` | `512` | Pixel window dimensions for COG raster reduction. |
| `REDIS_URL` | `SecretStr` | — | Redis connection URL for distributed Celery/Arq worker queue. |

---

## 3. The `groundtruth doctor` Diagnostic Tool

Developers and deployment operators verify runtime environment configuration using the CLI:

```bash
groundtruth doctor
```

```
[OK] Python Runtime: 3.12.3 (64-bit)
[OK] Database Connection: postgresql+psycopg://... (PostgreSQL 16.2)
[OK] Storage Backend: LocalStorageBackend (./data/storage)
[OK] Worker Concurrency: 8 processes (Ceiling: 24 GB RAM)
[OK] Authentication: Enabled (AUTH_REQUIRED=true, 7-day sessions)
[OK] STAC Provider: Planetary Computer (API key present)
[OK] GenAI Grounding: Downstream verification gate active
```
