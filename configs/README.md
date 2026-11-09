# Configuration Management (`configs`)

This directory maintains non-sensitive environment configuration schemas, configuration matrices, and deployment profiles for GroundTruth 2.0.

GroundTruth enforces a strict **zero-secrets-in-repo** policy. Sensitive credentials (database passwords, satellite provider API keys, JWT secret keys) are never committed to version control. They are supplied exclusively via runtime environment variables or external secret managers.

---

## Configuration Architecture & Precedence

All configuration across the API, background worker, CLI, and analytical engine is validated through **Pydantic Settings** (`groundtruth.platform.config.Settings`):

```mermaid
flowchart TD
    subgraph EnvSources["Environment Variable Sources (In Order of Precedence)"]
        CLIEnv["1. Process Environment Variables<br/>(export VAR=value / Kubernetes env)"]
        EnvLocal["2. Local Override File<br/>(.env.local / apps/web/.env.local)"]
        EnvFile["3. Root Dotenv File<br/>(.env)"]
        Defaults["4. Pydantic Model Defaults<br/>(groundtruth.platform.config.Settings)"]
    end

    subgraph ConfigValidation["Type-Safe Validation Gate"]
        SettingsModel["Pydantic Settings Validator<br/>- Wildcard CORS rejection<br/>- Absolute path resolution<br/>- SecretStr masking<br/>- Literal environment enums"]
    end

    subgraph Subsystems["Configured Runtime Subsystems"]
        APISub["FastAPI Gateway (apps/api)"]
        WorkerSub["Background Worker (apps/worker)"]
        WebSub["Next.js Web Frontend (apps/web)"]
        EngineSub["Analytical Engine (packages/groundtruth)"]
    end

    CLIEnv --> SettingsModel
    EnvLocal --> SettingsModel
    EnvFile --> SettingsModel
    Defaults --> SettingsModel

    SettingsModel --> APISub
    SettingsModel --> WorkerSub
    SettingsModel --> WebSub
    SettingsModel --> EngineSub
```

---

## Configuration Matrix

The complete set of runtime configuration parameters is detailed below:

### 1. Platform & Network Services

| Variable | Type / Constraints | Default | Description & Security Invariant |
| :--- | :--- | :--- | :--- |
| `APP_ENV` | `development` \| `test` \| `production` | `development` | Operating profile. |
| `LOG_LEVEL` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` | `INFO` | Logging verbosity (JSON output in production). |
| `DATABASE_URL` | String (`postgresql+psycopg://...` or `sqlite:///...`) | `None` | Database connection string. Unset fails closed. |
| `API_HOST` | IPv4 / String | `0.0.0.0` | Binding host interface for FastAPI. |
| `API_PORT` | Integer (1–65535) | `8000` | Binding port for FastAPI. |
| `FRONTEND_URL` | Valid URL string | `http://localhost:3000` | Trusted frontend web origin for CORS and CSRF validation. |
| `CORS_ALLOWED_ORIGINS`| Comma-separated URL list | `None` (uses `FRONTEND_URL`) | Whitelisted browser origins. **Wildcards (`*`) are explicitly rejected fail-closed.** |
| `REDIS_URL` | Redis URL (`redis://...`) | `None` | Optional Redis broker for distributed Arq worker queues. |

### 2. Multi-Tenant Authentication & Session Security

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `AUTH_REQUIRED` | Boolean | `false` (dev) / `true` (prod) | Enforces authentication on all tenant projects and runs. **Must be `true` in production.** |
| `AUTH_ALLOW_REGISTRATION` | Boolean | `true` | Enables public tenant signup via `POST /auth/register`. |
| `AUTH_COOKIE_SECURE` | Boolean | `false` | Sets the `Secure` flag on session cookies. **Must be `true` behind HTTPS reverse proxies.** |
| `AUTH_SESSION_DAYS` | Integer (1–90) | `7` | Session token validity duration in days. |

### 3. Earth Observation & Satellite Data Providers

| Variable | Type | Default | Purpose |
| :--- | :--- | :--- | :--- |
| `PLANETARY_COMPUTER_API_KEY` | SecretStr | `None` | Microsoft Planetary Computer STAC authentication for high-rate Landsat/Sentinel retrieval. |
| `SENTINEL_HUB_CLIENT_ID` | String | `None` | Copernicus Sentinel Hub client ID. |
| `SENTINEL_HUB_CLIENT_SECRET` | SecretStr | `None` | Copernicus Sentinel Hub secret key. |
| `GEE_SERVICE_ACCOUNT_JSON` | String (JSON filepath) | `None` | Google Earth Engine service account credentials. |
| `GLOBAL_FOREST_WATCH_API_KEY` | SecretStr | `None` | Global Forest Watch Hansen tree cover API token. |

### 4. GenAI Reporting & Narration Layer

| Variable | Type / Constraints | Default | Purpose |
| :--- | :--- | :--- | :--- |
| `GENAI_PROVIDER` | `none` \| `gemini` \| `openai` \| `anthropic` | `none` | AI narrative generation backend. Default `none` renders deterministic templates. |
| `GEMINI_API_KEY` | String | `None` | Google Gemini API key. |
| `GEMINI_MODEL` | String | `gemini-2.5-flash` | Gemini model identifier. |
| `GENAI_TEMPERATURE` | Float | `0.0` | Sampling temperature. **Fixed at 0.0 for deterministic grounding.** |
| `GENAI_MAX_OUTPUT_TOKENS` | Integer | `1200` | Maximum token ceiling for generated narrative sections. |

### 5. Causal Engine & Statistical Defaults

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `RANDOM_SEED` | Integer | `20260101` | Global deterministic pseudo-random generator seed. |
| `MIN_PRE_PERIODS` | Integer | `5` | Minimum required pre-treatment observations for Synthetic Control fitting. |
| `MIN_DONORS` | Integer | `10` | Minimum admissible reference donors required after leakage belt exclusions. |
| `MAX_PRE_RMSE_RATIO` | Float | `0.30` | Rejection threshold for pre-treatment fit error relative to outcome standard deviation. |

---

## Environment Profiles

GroundTruth defines three standard operational profiles:

### 1. Local Development (`.env`)
```env
APP_ENV=development
DATABASE_URL=sqlite:///data/interim/groundtruth.db
AUTH_REQUIRED=true
AUTH_COOKIE_SECURE=false
FRONTEND_URL=http://localhost:3000
CORS_ALLOWED_ORIGINS=http://localhost:3000
LOG_LEVEL=DEBUG
```

### 2. End-to-End Testing (`apps/web/e2e`)
* Ephemeral dynamic ports (`E2E_API_URL=http://localhost:8100`, `E2E_BASE_URL=http://localhost:3100`).
* Isolated SQLite database in a temporary directory removed upon test teardown.
* Deterministic demo credentials injected via `SEED_DEMO_PASSWORDS_FILE`.

### 3. Production Deployment (Docker Compose / Kubernetes)
```env
APP_ENV=production
DATABASE_URL=postgresql+psycopg://groundtruth:${PG_PASSWORD}@postgres/groundtruth
AUTH_REQUIRED=true
AUTH_COOKIE_SECURE=true
FRONTEND_URL=https://groundtruth.example.com
CORS_ALLOWED_ORIGINS=https://groundtruth.example.com
LOG_LEVEL=INFO
OTEL_SERVICE_NAME=groundtruth
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```
