# GroundTruth 2.0 System Architecture

GroundTruth 2.0 is an enterprise-grade platform for independent environmental verification and continuous ecological intelligence. It replaces unverifiable claims with deterministic remote sensing pipelines, causal econometric counterfactuals, multi-tenant role-based governance, and cryptographic provenance.

```mermaid
graph TB
    subgraph ClientTiers["Client Presentation Tier (Next.js 14 App Router)"]
        direction TB
        PublicZone["(public) Route Group<br/>• Marketing Landing<br/>• Public Methodology<br/>• Static Documentation"]
        AppZone["(app) Route Group<br/>• Multi-Tenant Workspaces<br/>• Auditor / Funder / Gov / NGO<br/>• Design System (ds/) Components"]
    end

    subgraph PlatformTier["Platform Services Tier (FastAPI & Python 3.12)"]
        direction TB
        APIGateway["FastAPI HTTP Gateway<br/>• OpenAPI 3.1 / Pydantic v2<br/>• RBAC Scopes (view, audit, contribute)<br/>• Session & CSRF Security"]
        TenancySvc["Multi-Tenant Service<br/>• Organizations & Projects<br/>• User Grants & Role Scopes"]
        AuditLogSvc["Append-Only Audit Log<br/>• Actor, Action, Target, IP<br/>• Cryptographic Hash Chaining"]
        JobSvc["Job Orchestrator<br/>• PostgreSQL Leasing Queue<br/>• Redis / Celery Streamer<br/>• Spec-Hash Idempotency"]
    end

    subgraph WorkerTier["Asynchronous Worker Tier"]
        direction TB
        WorkerNodes["GroundTruth Compute Workers<br/>• Celery / Redis / Postgres Workers<br/>• 8-Core ProcessPool Concurrency<br/>• Atomic Job Heartbeating"]
    end

    subgraph AnalyticalEngineTier["Deterministic Analytical Engine (Pure Python / NumPy)"]
        direction TB
        EOEngine["Earth Observation Engine<br/>• USGS C2 L2 Surface Reflectance<br/>• Sentinel-2 Harmonized SCL<br/>• Roy et al. Sensor Calibration"]
        MatchingEngine["Candidate Matching<br/>• 50 ADM2 Districts (37 Eligible)<br/>• Buffer & Leakage Exclusions"]
        CausalEngine["Causal Econometrics<br/>• Simplex-Constrained FISTA SCM<br/>• Two-Way Fixed Effects DiD"]
        PermutationEngine["Uncertainty & Placebos<br/>• In-Space / In-Time Placebos<br/>• Leave-One-Out Robustness<br/>• Specification Curves"]
        AssessmentEngine["8 Assessment Dimensions<br/>• Trajectory, Spatial, Climate,<br/>• Risk, Restoration, Benchmark,<br/>• Evidence Quality, Attribution"]
    end

    subgraph StorageTier["Tiered Storage & Persistence Tier"]
        direction TB
        SQLStore[("PostgreSQL 16 Database<br/>• Multi-Tenant Data Schema<br/>• Append-Only Audit Entries<br/>• Job Execution State")]
        BlobStore["Tiered Blob Storage Abstraction<br/>• RAW_SOURCE (STAC COGs)<br/>• INTERMEDIATE (Rasters/Chips)<br/>• FINAL_EVIDENCE (Bundles)<br/>• METADATA (.meta.json SHA-256)"]
    end

    subgraph ReportingGenAITier["Verifiable Reporting & GenAI Boundary Tier"]
        direction TB
        EvBundle["Immutable EvidenceBundle (v1.0)<br/>• SHA-256 Canonical Fingerprint<br/>• 5-State Epistemology"]
        GenAILayer["LLM Narration Layer<br/>• Verifiable Synthesis<br/>• No Autonomous Calculation"]
        GroundingGate{"Grounding Verifier Gate<br/>• 2% Numeric Tolerance Check<br/>• Prohibited Accusation Filter<br/>• Mandatory Caveat Enforcer"}
        PublishedAudit["Cryptographically Signed Audit Report"]
        DryFallback["Deterministic Dry Report Renderer"]
    end

    ClientTiers -->|Secure HTTPS / Cookie Session| APIGateway
    APIGateway --> TenancySvc
    APIGateway --> AuditLogSvc
    APIGateway --> JobSvc
    TenancySvc --> SQLStore
    AuditLogSvc --> SQLStore
    JobSvc --> SQLStore
    JobSvc --> WorkerNodes
    WorkerNodes --> EOEngine
    EOEngine --> MatchingEngine
    MatchingEngine --> CausalEngine
    CausalEngine --> PermutationEngine
    PermutationEngine --> AssessmentEngine
    AssessmentEngine --> EvBundle
    WorkerNodes --> BlobStore
    EvBundle --> SQLStore
    EvBundle --> BlobStore
    EvBundle --> GenAILayer
    EvBundle --> DryFallback
    GenAILayer --> GroundingGate
    GroundingGate -->|Pass| PublishedAudit
    GroundingGate -->|Violation| DryFallback
```

![Auditor Dashboard](../product/screens/auditor-dashboard.png)

---

## 1. The Core Architectural Boundary: Determinism vs. Narration

The foundational design invariant of GroundTruth 2.0 is an unbreachable separation between numerical computation and language generation:

```
┌──────────────────────── DETERMINISTIC ENGINE ────────────────────────┐
│                                                                      │
│  ingestion → masking → matching → causal → uncertainty → assessment  │
│                                                                      │
│  Pure NumPy / Python. No LLMs. No Network Sockets. No Credentials.   │
│  Every value carries explicit Provenance and EvidenceState.          │
└───────────────────────────────────┬──────────────────────────────────┘
                                    │
                                    ▼
                         EvidenceBundle (Immutable, SHA-256)
                                    │
┌──────────────────────── REPORTING & GENAI TIER ──────────────────────┐
│                                                                      │
│  Deterministic Renderer  ──or──  LLM Narration → Grounding Check     │
│                                                       │              │
│                                                 fails ┴► Fallback    │
└──────────────────────────────────────────────────────────────────────┘
```

A generative model handed multi-temporal satellite rasters or spreadsheets and asked "did this project over-credit?" produces ungrounded hallucinations. Conversely, an LLM handed an immutable, verified `EvidenceBundle` containing pre-computed statistics and asked "explain these findings in auditor language" operates strictly within its verified capability.

If any generated report hallucinates a figure outside a 2% numeric tolerance, asserts fraud, or drops mandatory scientific caveats, the system fails closed and publishes the deterministic report.

---

## 2. Multi-Tenant Architecture & Data Layer

GroundTruth 2.0 implements a multi-tenant, role-governed data model supporting cross-organizational collaboration with rigorous isolation:

```mermaid
erDiagram
    ORGANIZATION ||--o{ PROJECT : owns
    ORGANIZATION ||--o{ MEMBERSHIP : has
    USER ||--o{ MEMBERSHIP : holds
    USER ||--o{ GRANT : receives
    PROJECT ||--o{ GRANT : scoped_to
    PROJECT ||--o{ ANALYSIS_RUN : executes
    ANALYSIS_RUN ||--|| EVIDENCE_BUNDLE : produces
    PROJECT ||--o{ AUDIT_LOG : tracks
    USER ||--o{ AUDIT_LOG : initiates

    ORGANIZATION {
        uuid id PK
        string name
        string slug
        string org_type "auditor | funder | government | ngo"
        timestamp created_at
    }

    PROJECT {
        uuid id PK
        uuid organization_id FK
        string name
        string case_id
        string standard "VCS | Gold Standard | Sovereign"
        jsonb boundary_geojson
        timestamp created_at
    }

    USER {
        uuid id PK
        string email
        string hashed_password
        string full_name
        boolean is_active
        timestamp created_at
    }

    GRANT {
        uuid id PK
        uuid user_id FK
        uuid project_id FK
        string role "view | audit | contribute"
        timestamp granted_at
    }

    AUDIT_LOG {
        uuid id PK
        uuid organization_id FK
        uuid project_id FK
        uuid actor_id FK
        string action
        string target_resource
        inet ip_address
        string checksum_sha256
        timestamp recorded_at
    }
```

### 2.1 Organizations, Projects, and Scoped Grants
- **Organizations**: Legal entities operating in the system (e.g., Audit Firms, Carbon Funds, Environmental Ministries, Project Developers).
- **Projects**: Registered intervention units carrying geospatial boundaries, baseline crediting periods, and reference data.
- **Grants**: Granular access tokens binding users to projects under three distinct roles:
  - `view`: Read-only access to published evidence bundles, summaries, and executive dashboards.
  - `audit`: Full inspection privileges, access to raw satellite observation chips, donor matching diagnostics, and sensitivity runs.
  - `contribute`: Authority to upload project polygons, boundary amendments, ground truth surveys, and register analysis runs.
- **Append-Only Audit Log**: Every user action, state change, and analysis run is recorded with client IP, timestamp, actor identity, and SHA-256 checksums to ensure tamper-evident governance.

![Cross-Organization Access Denied](../product/screens/cross-org-denied.png)

---

## 3. Package and Repository Topology

GroundTruth 2.0 is organized as a high-discipline monorepo separating presentation applications, platform infrastructure, and pure analytical computation:

```
GroundTruth/
├── apps/
│   ├── api/                   Thin ASGI FastAPI entrypoint (apps.api.main:app)
│   ├── web/                   Next.js 14 App Router application
│   │   └── src/
│   │       ├── app/
│   │       │   ├── (app)/     Multi-tenant authenticated workspaces (Auditor, Funder, etc.)
│   │       │   ├── (public)/  Public marketing, landing, methodology pages
│   │       │   └── (legacy)/  Backward-compatible case views
│   │       ├── components/ds/ GroundTruth Design System components (542 tests)
│   │       └── lib/           Typed API client & generated OpenAPI types
│   └── worker/                Background job consumer entrypoint (apps.worker.main)
├── packages/
│   └── groundtruth/
│       ├── src/groundtruth/
│       │   ├── contracts/     Shared, immutable Pydantic v2 schemas and protocols
│       │   ├── engine/        Pure scientific computation (NumPy only, no I/O)
│       │   │   ├── observation/   Index computation, QA masking, zonal reductions
│       │   │   ├── matching/      Donor candidate pool filtering & balance
│       │   │   ├── causal/        Simplex FISTA SCM & DiD estimators
│       │   │   ├── uncertainty/   In-space/in-time permutation inference
│       │   │   └── assessment/    8 assessment dimensions & rule evaluator
│       │   ├── platform/      FastAPI routes, tenancy, auth, jobs, storage, store
│       │   │   ├── api/       Routers, OpenAPI snapshot generator, middleware
│       │   │   ├── tenancy/   Organization, project, and grant service
│       │   │   ├── auth/      Session, RBAC, CSRF, rate-limiting services
│       │   │   ├── audit/     Append-only cryptographic audit logging
│       │   │   ├── jobs/      PostgreSQL leasing & Redis/Celery queue backends
│       │   │   └── storage/   Tiered blob storage (LocalStorage, S3Storage)
│       │   ├── provenance/    SHA-256 bundle verification and Sigstore cosign signing
│       │   └── observability/ OpenTelemetry spans, metrics, and trace telemetry
└── tests/                     1,120+ backend tests and scientific property suites
```

### 3.1 Unidirectional Dependency Invariant
Dependencies flow strictly inward toward `contracts`:

```mermaid
graph LR
    Apps["apps/ (api, web, worker)"] --> Platform["groundtruth.platform"]
    Platform --> Contracts["groundtruth.contracts"]
    Engine["groundtruth.engine"] --> Contracts
    Platform -.->|Imports 4 Entrypoint Functions Only| Engine
```

The platform imports exactly four entrypoint symbols from the engine: `run_analysis`, `describe_engine`, `engine_ref`, and `ENGINE_VERSION`. The engine is strictly forbidden from importing platform code, database drivers, network sockets, or filesystem routines. This invariant is enforced on every commit by `tests/test_contract_boundary.py`, which parses the Python AST across all modules.

---

## 4. Frontend Workspace Architecture: 4 Personas

The Next.js 14 frontend is restructured under App Router route groups:
- `(public)`: Public documentation, case methodology, and marketing.
- `(app)`: Role-gated workspaces tailored to specific industry personas:

```mermaid
graph TD
    ClientReq["Client Route Request"] --> Layout{"Route Group Matching"}
    Layout -->|"(public)/*"| PubShell["Public Layout<br/>• Marketing Navbar<br/>• Static Documentation<br/>• Public Methodology"]
    Layout -->|"(app)/*"| AuthShell["Authenticated App Layout<br/>• Tenant Organization Switcher<br/>• Scoped Role Navigation<br/>• RBAC Route Guard"]
    
    AuthShell --> AuditorRole["Auditor Workspace<br/>• Statistical diagnostics (RMSPE, LOO)<br/>• Donor pool weights & exclusions<br/>• Cryptographic provenance chains"]
    AuthShell --> FunderRole["Funder Workspace<br/>• Portfolio carbon risk overview<br/>• Claimed vs. observed delta<br/>• Capital exposure benchmarks"]
    AuthShell --> GovRole["Government Workspace<br/>• Sovereign NDC compliance<br/>• Article 6 leakage tracking<br/>• National forest boundaries"]
    AuthShell --> NGORole["NGO Workspace<br/>• Intervention progress monitoring<br/>• Multi-spectral vegetation index trends<br/>• Field survey evidence upload"]
```

![Funder Dashboard](../product/screens/funder-dashboard.png)

---

## 5. Asynchronous Job & Worker Execution

Heavy causal calculations and satellite raster processing are decoupled from HTTP request loops:

```mermaid
sequenceDiagram
    autonumber
    actor User as Auditor / User
    participant Web as Next.js Web App
    participant API as FastAPI Gateway
    participant Queue as PostgreSQL / Redis Queue
    participant Worker as Compute Worker Process
    participant Storage as Tiered Storage Backend
    participant Store as Evidence Store

    User->>Web: Click "Execute Verification"
    Web->>API: POST /jobs (AnalysisRequest, spec_hash)
    API->>Queue: Submit Job (queued, lease=300s)
    API-->>Web: 202 Accepted (run_id, status_url)
    
    loop Worker Polling & Execution
        Worker->>Queue: Claim Job (atomic lease acquisition)
        Queue-->>Worker: Job Granted (run_id)
        
        loop Heartbeat Loop (every 10s)
            Worker->>Queue: Heartbeat Touch (extend lease)
        end
        
        Worker->>Storage: Retrieve Raw/Cached STAC Observation Assets
        Storage-->>Worker: Raster Chips & Covariate Panels
        Worker->>Worker: Run Pure Engine (EO → Match → Causal → Uncertainty)
        Worker->>Storage: Persist Final Evidence Artifacts & Checksums
        Worker->>Store: Atomic Transaction (save AnalysisRun & EvidenceBundle)
        Worker->>Queue: Mark Job Finished (terminal: succeeded / refused)
    end

    loop Frontend Status Polling
        Web->>API: GET /jobs/{run_id}
        API->>Queue: Query Job Status & Live Stages
        API-->>Web: 200 OK (stage: "engine", elapsed_ms: 1420)
    end

    Web->>API: GET /runs/{run_id}
    API->>Store: Query Verified EvidenceBundle
    API-->>Web: 200 OK (Complete Immutable Bundle)
    Web-->>User: Render Interactive Visualizer & Audit Charts
```

---

## 6. Scientific Integrity & The Fail-Closed Data Gateway

### 6.1 Epistemological Evidence States
Every measurement or statistic is tagged with an `EvidenceState`:
- `RAW_OBSERVED`: Uncalibrated, direct sensor measurements.
- `DERIVED`: Cloud-masked, harmonized spectral indices.
- `MODEL_ESTIMATED`: Econometrically fitted counterfactuals and weights.
- `INFERRED`: Confidence intervals, permutation p-values.
- `UNAVAILABLE` / `INSUFFICIENT_EVIDENCE`: Missing observations.

### 6.2 Fail-Closed Principle & Audit Findings
Following independent audits (Task 5/5B), GroundTruth 2.0 enforces a **fail-closed data gateway**:

```mermaid
stateDiagram-v2
    [*] --> CheckDataMode: Incoming Analysis Request
    
    state CheckDataMode {
        [*] --> ModeBranch
        ModeBranch --> SyntheticMode: data_mode == "simulated"
        ModeBranch --> RealMode: data_mode == "observed"
    }

    SyntheticMode --> ExecuteSynthetic: Load Seeded Factor Panel
    ExecuteSynthetic --> LabelSynthetic: Force is_simulated=True
    LabelSynthetic --> RenderResults: Display Persistent Simulated Banner

    RealMode --> AuditReadiness: Inspect STAC & Climate Panels
    
    state AuditReadiness {
        [*] --> VerifyCoverage: Check Spatial Completeness
        VerifyCoverage --> VerifyHarmonization: Check Sensor Calibration
        VerifyHarmonization --> VerifyDonors: Check Uncontaminated Donor Series
    }

    AuditReadiness --> GateDecision: Evaluate Thresholds
    
    GateDecision --> RaiseRefusal: Incomplete Coverage (<95%) OR<br/>Uncalibrated Historical Sensors OR<br/>Missing Donor Vegetation Outcomes
    GateDecision --> ExecuteReal: All Real Evidence Present & Verified
    
    RaiseRefusal --> HTTP501: Raise DataUnavailableError (HTTP 501 / Refusal)
    HTTP501 --> INCONCLUSIVE: Verdict = INCONCLUSIVE (not estimable)
    
    ExecuteReal --> BuildBundle: Assemble Verified EvidenceBundle
```

> [!IMPORTANT]
> **Independent Audit Posture (Kariba REDD+ VCS 902)**:
> In `REAL_OBSERVATIONS` mode, GroundTruth 2.0 refuses to extrapolate or invent historical pre-treatment vegetation series. Real Sentinel-2 post-treatment data (2021–2023), real CHIRPS precipitation (514/516 months), real NASA POWER temperature, and 37 spatially eligible ADM2 donor districts are rigorously integrated. However, because cross-sensor Landsat 5/7/8 surface reflectance harmonization across 2001–2010 requires coincident empirical cross-calibration and whole-AOI multi-tile raster extraction that is pending execution, the system issues a clear, honest verdict:
>
> **ATTRIBUTION VERDICT: INCONCLUSIVE (not estimable from available real data).**
>
> GroundTruth 2.0 never falls back silently to simulation and never serves unverified numbers under a real-data label.

---

## 7. System Architecture Verification Matrix

| Architectural Invariant | Mechanism of Enforcement | Verification Test |
| :--- | :--- | :--- |
| **Engine Isolation** | Engine imports no I/O, DB, network, or platform code | `tests/test_contract_boundary.py` |
| **Spectral Guard** | Refusal to convert NDVI to carbon without allometry | `tests/test_units.py` |
| **GenAI Grounding** | 2% numeric tolerance, caveat check, prohibited words | `tests/test_grounding.py` |
| **Multi-Tenant RBAC** | Strict middleware, organization scopes (`view`, `audit`, `contribute`) | `tests/test_tenancy.py` |
| **Reproducibility** | `spec_hash` and declared PRNG seeds produce identical bits | `tests/test_golden_reproducibility.py` |
| **Immutable Evidence** | Database trigger blocks `UPDATE` on `evidence_bundles` | `tests/test_evidence_store.py` |
| **Fail-Closed Gate** | Real mode raises 501 `DataUnavailableError` on incomplete data | `tests/test_real_observations.py` |
| **OpenAPI Typing** | Generated TypeScript types match FastAPI schemas | `tests/test_openapi_snapshot.py` |
