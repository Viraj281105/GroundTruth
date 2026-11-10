# Backend Architecture

**Platform Core**: `packages/groundtruth/src/groundtruth/platform/` & `apps/api/`  
**Runtime**: Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0, PostgreSQL 16 / SQLite, optional Redis (`rate_limiting` / `arq`).

The backend platform is the operational foundation of GroundTruth 2.0. It manages authentication, multi-tenant isolation, role-based access control, cryptographic audit logging, asynchronous compute scheduling, tiered blob persistence, and immutable evidence storage.

```mermaid
graph TD
    subgraph ClientRequests["HTTP / WebSocket Request Ingestion"]
        Req["Client HTTP Request<br/>(Header / Cookie Session)"]
    end

    subgraph MiddlewarePipeline["FastAPI Middleware Pipeline"]
        CORS["CORS Policy Validation<br/>(Allowed Origins Only)"]
        CSRF["CSRF Protection<br/>(SameSite + Lax / Strict Origin)"]
        RateLimit["Rate Limiting Middleware<br/>(In-Memory / Redis Token Bucket)"]
        AuthDep["Authentication Dependency<br/>(Session / Bearer Token)"]
        RBACGate{"RBAC Enforcement Gate<br/>(Organization / Project Scope)"}
    end

    subgraph ServiceLayer["Platform Service Layer"]
        TenancySvc["Tenancy Service<br/>(Orgs, Projects, Grants)"]
        AuditSvc["Audit Logging Service<br/>(Append-Only, SHA-256)"]
        JobSvc["Job Orchestrator Service<br/>(Leasing / Redis Dispatcher)"]
        CompareSvc["Run Comparison Service<br/>(Evidence Delta Evaluator)"]
        ReportSvc["Reporting Service<br/>(Deterministic / Grounded GenAI)"]
    end

    subgraph StorageLayer["Data & Persistence Layer"]
        DB[("PostgreSQL Database<br/>• Users & Sessions<br/>• Orgs, Projects, Grants<br/>• Analysis Runs<br/>• Immutable Evidence Bundles<br/>• Append-Only Audit Entries")]
        BlobStore["Tiered Blob Storage<br/>(LocalStorage / S3Storage)<br/>• RAW_SOURCE<br/>• INTERMEDIATE<br/>• FINAL_EVIDENCE<br/>• APPLICATION_METADATA"]
    end

    Req --> CORS --> CSRF --> RateLimit --> AuthDep --> RBACGate
    RBACGate -->|Authorized Scope| TenancySvc
    RBACGate -->|Authorized Scope| JobSvc
    RBACGate -->|Authorized Scope| CompareSvc
    RBACGate -->|Authorized Scope| ReportSvc
    TenancySvc --> AuditSvc
    JobSvc --> AuditSvc
    AuditSvc --> DB
    TenancySvc --> DB
    JobSvc --> DB
    JobSvc --> BlobStore
```

![Auditor Dashboard](../product/screens/auditor-dashboard.png)

---

## 1. Platform Modules & Responsibilities

| Module | Location | Primary Responsibility | GroundTruth 2.0 Status |
| :--- | :--- | :--- | :--- |
| `api/` | `platform/api/` | FastAPI routers, OpenAPI schemas, error mapping, cursor pagination | Implemented & Snapshot Tested |
| `tenancy/` | `platform/tenancy/` | Organizations, Projects, User Memberships, Grant Scoping | Implemented |
| `auth/` | `platform/auth/` | Session management, password hashing (Scrypt), CSRF guards, RBAC | Implemented |
| `audit/` | `platform/audit/` | Append-only audit logging with cryptographic SHA-256 Merkle chain verification | Implemented |
| `jobs/` | `platform/jobs/` | Job lifecycle: SQL row-lease queue, optional Redis/arq adapter, worker runner | Implemented |
| `store/` | `platform/store/` | Immutable SQL evidence store, run versioning, trigger protection | Implemented |
| `storage/`| `platform/storage/`| Tiered blob storage abstraction (`LocalStorageBackend`, `S3Storage`) | Implemented |
| `cases/` | `platform/cases/` | Case registry, YAML parsing, translation to `AnalysisRequest` | Implemented |
| `datasets/`| `platform/datasets/`| STAC observation access, CHIRPS/POWER climate access, pinning | Implemented |
| `compare/`| `platform/compare/`| Evidence diffing, non-comparability guards, parameter shift detection | Implemented |
| `reports/`| `platform/reports/`| Deterministic markdown renderer, GenAI narrator, grounding check | Implemented |
| `config.py`| `platform/config.py`| Environment-driven Pydantic `Settings`, secret masking | Implemented |

### 1.1 Case management rules (#36)

Cases are YAML under `cases/`; `POST /cases` writes one. Three rules hold on every path:

- **A created case makes a valid request.** Everything is checked *before* a file is written: the
  boundary, the analysis window (including the estimator's 5 pre-period minimum), the indicator,
  standard and dates. A rejected case answers a structured `422` (`invalid_case`, with the field
  named and a hint) and leaves nothing on disk. Case ids must be lowercase kebab-case, because the
  id becomes a file name.
- **`status: analysed` cannot be set.** The guard is in `CaseDefinition.__post_init__`, so the YAML
  loader, `create_and_register_case`, the database upsert and project seeding all go through it.
  It refuses `analysed` with `case_status_requires_review`: that status needs a run reviewed by both
  owners (coordination point C7, issue #4), and there is no review mechanism or real run yet. An
  unknown status (a typo such as `analyzed`) is refused too. `POST /cases` accepts a `status` field
  only to refuse it explicitly.
- **A case's `min_donors` is its pre-registered refusal floor.** A request that omits it uses the
  case's own value (Kariba: 30). It may ask for a *higher* value; a *lower* one is refused with
  `min_donors_below_case_floor`, because lowering the floor is how a refusal gets forced into a number.
  This applies to `POST /jobs`, `POST /cases/{id}/verify` and the CLI.

### 1.2 Report export (#38)

PDF and CSV exports go through `platform/reports/export_pipeline.py`: the report is verified against
its own bundle, a failed narration refuses the export instead of being substituted, provenance and the
simulated-data warning are guaranteed, and the generator is labelled. See
[`genai.md`](genai.md), section 4. The inline `report_markdown` keeps its deterministic fallback.

### 1.3 One error envelope for every router (#39)

Routes raise errors in several ways (`api_error`, a bare `HTTPException`, FastAPI's validation error,
the auth module's `auth_error`, the CSRF guard, an unexpected exception). Rather than touch each,
`ErrorEnvelopeMiddleware` (`platform/api/error_envelope.py`) normalises the response of any status
400 or above whose body is JSON. It sits inside CORS, so even a 500 carries CORS headers.

| Every error response has | |
| --- | --- |
| `request_id` | Also the `X-Request-ID` header, which every response carries. A valid id from the caller is kept. |
| `is_refusal` | At the top level always, and inside `detail` when `detail` is a dict. `true` only for a scientific refusal. |
| `detail` | **Unchanged in shape**: a dict `{code, message, hint, ...}`, a string, or FastAPI's validation list. |

Added to the validation list and string forms: `code` (`validation_error`, or `http_<status>`), `message`,
and for validation errors `fields`, the dotted name of each offending field (`body.area_ha`). The list
keeps `loc`, `msg` and `type` per entry; **the submitted `input` is dropped**, because a rejected
password field would otherwise be echoed back.

The scrub rewrites only absolute file paths (the file name stays), tracebacks, SQL and its
parameters, credentials in connection strings, and configured secrets. It never removes a key, and
`code`, `stage`, `remediation` and `hint` pass through untouched. Stored engine error text served in
200 responses (`error.message`, `failure_reason`) is scrubbed the same way.

An exception no route handled returns a JSON 500 (`internal_error`) with a generic message and the
request id. The traceback is logged on the server, with configured secrets removed first.

---

## 2. Multi-Tenant RBAC Enforcement & Data Isolation

GroundTruth 2.0 enforces strict multi-tenancy at the API gateway:

```mermaid
flowchart TD
    Start(["Incoming Request: /projects/{id}/*"]) --> Authenticate{"Valid Session Cookie?"}
    Authenticate -- No --> Ret401["Return 401 Unauthorized"]
    Authenticate -- Yes --> IdentifyUser["Identify Actor & Organization"]
    
    IdentifyUser --> QueryGrant{"User holds Grant for Project?"}
    QueryGrant -- No Grant --> Ret403["Return 403 Forbidden<br/>(Cross-Organization Access Denied)"]
    
    QueryGrant -- Grant Exists --> CheckRole{"Evaluate Required Action Scope"}
    CheckRole -- "Read / Export" --> CheckView["Grant in ('view', 'audit', 'contribute')?"]
    CheckRole -- "Execute Audit / Placebo" --> CheckAudit["Grant in ('audit', 'contribute')?"]
    CheckRole -- "Upload Boundary / Data" --> CheckContrib["Grant == 'contribute'?"]
    
    CheckView -- Yes --> RecordAudit["Write Append-Only Audit Entry"]
    CheckAudit -- Yes --> RecordAudit
    CheckContrib -- Yes --> RecordAudit
    
    CheckView -- No --> Ret403Scope["Return 403 Forbidden (Insufficient Scope)"]
    CheckAudit -- No --> Ret403Scope
    CheckContrib -- No --> Ret403Scope
    
    RecordAudit --> ExecuteService["Dispatch Request to Domain Service"]
```

![Cross-Organization Access Denied](../product/screens/cross-org-denied.png)

### 2.1 The Three Grant Scopes
1. **`view`**: Read-only privileges for funders and executive observers. Allows browsing projects, inspecting verified evidence bundles, and viewing generated reports.
2. **`audit`**: Full analytical verification privileges. Allows triggering sensitivity runs, inspecting raw satellite observation tiles, analyzing donor candidate exclusions, and viewing the complete provenance chain.
3. **`contribute`**: Administrative and developer privileges. Allows uploading intervention boundaries, registering new project baselines, submitting field ground-truth observations, and executing production analysis jobs.

---

## 3. Strict Boundary Invariant: Platform Consuming Engine

The platform interacts with the analytical engine through four strictly typed symbols defined in `groundtruth.contracts`:

```python
from groundtruth.contracts import (
    AnalysisRequest,
    AnalysisResult,
    EngineStatus,
    ErrorCode,
)
from groundtruth.engine import (
    run_analysis,
    describe_engine,
    engine_ref,
    ENGINE_VERSION,
)
```

No platform module may import from internal engine subpackages (`causal`, `observation`, `matching`, `uncertainty`, `assessment`). This invariant is enforced by `tests/test_contract_boundary.py`.

---

## 4. Asynchronous Job Lifecycle & Queue Options

Analytical verification tasks require high-dimensional matrix optimization, permutation tests across dozens of donor regions, and multi-temporal satellite raster processing. GroundTruth 2.0 defaults to the SQL leasing queue and provides optional queue adapters:

1. **SQL Leasing Queue (`platform.jobs.queue`)**: Default zero-dependency queue using database table row leases with atomic heartbeating.
2. **Optional Redis + Arq Adapter (`platform.jobs.redis_queue`)**: Distributed queue adapter with per-stage hashes (requires `[queue]` extras and explicit wiring; `REDIS_URL` also enables shared Redis API rate limiting).

```mermaid
sequenceDiagram
    autonumber
    actor Client as Web Client / CLI
    participant API as FastAPI Platform
    participant Q as Job Queue (SQL / Redis)
    participant W as Worker Process
    participant ES as SQL Evidence Store
    participant BS as Tiered Blob Store

    Client->>API: POST /jobs (AnalysisRequest)
    API->>Q: Submit Job (run_id, spec_hash, lease_duration=300s)
    API-->>Client: 202 Accepted (run_id, status_url)
    
    W->>Q: Claim Next Job (Worker ID, atomic row lock)
    Q-->>W: Job Claimed (run_id)
    
    loop Heartbeat Task
        W->>Q: Heartbeat (every lease_duration / 3)
    end
    
    W->>BS: Read Observation Inputs & Zarr Grids
    W->>W: Execute run_analysis(request, access)
    
    alt Analysis Succeeded
        W->>BS: Save Artifacts to FINAL_EVIDENCE Tier
        W->>ES: Save AnalysisRun & EvidenceBundle (Atomic Commit)
        W->>Q: Complete Job (status="succeeded", result_state="measured")
    else Analysis Refused by Gate Chain
        W->>ES: Save AnalysisRun with Structured AnalysisError
        W->>Q: Complete Job (status="succeeded", result_state="refused")
    else Process Unhandled Crash
        W--xW: Process Dies
        Note over Q: Lease expires after 300s<br/>Job returned to queue for retry
    end

    Client->>API: GET /jobs/{run_id}
    API->>Q: Query Status & Live Stage Log
    API-->>Client: 200 OK (terminal: true, result_state: "measured")
```

---

## 5. Persistence & Immutable Evidence Store

The persistence layer is managed via SQLAlchemy 2.0 with Alembic migrations:

```mermaid
erDiagram
    CASES ||--o{ ANALYSIS_RUNS : executes
    ANALYSIS_RUNS ||--o| EVIDENCE_BUNDLES : records
    ANALYSIS_RUNS ||--o{ JOBS : tracks

    CASES {
        string case_id PK
        string name
        string country
        string biome
        jsonb metadata
        timestamp created_at
    }

    ANALYSIS_RUNS {
        string run_id PK
        string case_id FK
        string spec_hash
        string engine_version
        string engine_contract_version
        string status "queued | running | succeeded | failed"
        string result_state "measured | refused | failed | cancelled"
        string data_mode "observed | simulated"
        boolean is_simulated
        jsonb error_payload
        timestamp created_at
        timestamp finished_at
    }

    EVIDENCE_BUNDLES {
        string run_id PK, FK
        string case_id
        string schema_version
        jsonb bundle_json
        string canonical_sha256
        timestamp stored_at
    }

    JOBS {
        string run_id PK, FK
        string worker_id
        int attempt
        timestamp lease_expires_at
        timestamp heartbeat_at
        boolean cancelled
        string stage
        jsonb stage_log
    }
```

### 5.1 Storage Immutability Invariant
Evidence bundles are **strictly immutable**. Re-executing an analysis generates a fresh `run_id`. A PostgreSQL database trigger unconditionally aborts any `UPDATE` command executed against the `evidence_bundles` table:

```sql
CREATE OR REPLACE FUNCTION reject_bundle_update()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Evidence bundles are immutable and cannot be updated. Run ID: %', OLD.run_id;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_immutable_evidence_bundles
BEFORE UPDATE ON evidence_bundles
FOR EACH ROW EXECUTE FUNCTION reject_bundle_update();
```

---

## 6. Tiered Storage Abstraction (`blob_store.py`)

GroundTruth 2.0 partitions binary assets into four distinct storage tiers:

| Tier | Enum Member | Contents | Retention & Access |
| :--- | :--- | :--- | :--- |
| **Tier 1** | `RAW_SOURCE` | Raw Cloud-Optimized GeoTIFFs, Sentinel-2 tiles, CHIRPS NetCDFs | Read-only cache / cold archive |
| **Tier 2** | `INTERMEDIATE_ARTIFACT` | Intermediate raster chips, cloud masks, SVD matrices | Internal compute only, TTL auto-purge |
| **Tier 3** | `FINAL_EVIDENCE` | Final serialized `EvidenceBundle`, zonal reduction tables | Public verification, immutable |
| **Tier 4** | `APPLICATION_METADATA` | SHA-256 sidecar checksums (`.meta.json`), provenance manifests | Permanent audit trail |

Atomic writes are enforced on POSIX filesystems using unique temporary files and `os.replace` to prevent corrupted reads during power or process interruption.

---

## 7. API Schema as Frontend Contract & Snapshot Testing

The backend OpenAPI schema (`platform/api/openapi_schema.py`) is the source of truth for all frontend TypeScript types:
- API changes are committed alongside an updated snapshot: `apps/web/src/lib/generated/openapi.json`.
- TypeScript definitions are compiled directly via `make api-types` (`npm run generate:api-types`).
- CI runs `tests/test_openapi_snapshot.py` and `npm run check:api-types` on every pull request, failing if frontend definitions drift from backend Pydantic models.
