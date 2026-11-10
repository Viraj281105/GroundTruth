# Deployment Compute Architecture & Storage Hierarchy

**Project**: GroundTruth 2.0 — Enterprise Impact Verification Platform  
**Architecture Spec**: Task 5B Deployment-Aware Architecture  
**Status**: APPROVED & CODIFIED  
**Implementation**: `groundtruth.platform.storage.blob_store`, `groundtruth.platform.jobs`, `apps/api/`, `apps/worker/`

GroundTruth 2.0 is architected for dual-environment deployment:
1. **Local Developer Workstation**: Zero-external-dependency execution using local NVMe storage, multi-process CPU concurrency, and direct SQLite/PostgreSQL storage.
2. **Production Cloud Deployment**: Horizontally scalable container topology (Docker Compose / Kubernetes / Helm), SQL row-lease workers (with optional Redis/arq and Temporal adapters), managed PostgreSQL 16, and cloud object storage (AWS S3, Cloudflare R2, MinIO).

```mermaid
graph TB
    subgraph ClientLayer["Presentation Tier (Next.js 14 App Router)"]
        WebUI["Web Client Workspaces<br/>(Auditor, Funder, Gov, NGO)"]
    end

    subgraph APILayer["API Gateway Tier (FastAPI)"]
        Gateway["FastAPI Gateway<br/>• OpenAPI 3.1 / Pydantic v2<br/>• Strict Multi-Tenant RBAC<br/>• Session & CSRF Security"]
    end

    subgraph AsyncQueue["Distributed Job Scheduling Tier"]
        SQLQueue["PostgreSQL Leasing Queue<br/>(SELECT FOR UPDATE SKIP LOCKED)"]
        RedisQueue["Optional Redis + Arq Queue<br/>(Distributed Adapter)"]
    end

    subgraph ComputeWorkers["Worker Compute Tier (Python 3.12)"]
        Worker1["Compute Worker Process 1<br/>(8 Processes / 512px Chunks)"]
        WorkerN["Compute Worker Process N<br/>(Horizontal Scale-Out)"]
    end

    subgraph TieredStorage["Four-Tier Blob Storage Hierarchy"]
        T1["Tier 1: RAW_SOURCE<br/>(Raw STAC COGs, NetCDFs)"]
        T2["Tier 2: INTERMEDIATE_ARTIFACT<br/>(Chips, Masks, SVD Panels)"]
        T3["Tier 3: FINAL_EVIDENCE<br/>(Immutable Evidence Bundles)"]
        T4["Tier 4: APPLICATION_METADATA<br/>(SHA-256 .meta.json Manifests)"]
    end

    subgraph DatabaseTier["Relational Store"]
        DB[("PostgreSQL 16 Database<br/>• Multi-Tenant Schema<br/>• Append-Only Audit Entries<br/>• Immutable Evidence Trigger")]
    end

    WebUI -->|HTTPS / WSS| Gateway
    Gateway --> SQLQueue
    Gateway --> RedisQueue
    Gateway --> DB
    SQLQueue --> Worker1 & WorkerN
    RedisQueue --> Worker1 & WorkerN
    Worker1 & WorkerN --> TieredStorage
    Worker1 & WorkerN --> DB
```

![Auditor Dashboard](../product/screens/auditor-dashboard.png)

---

## 1. Four-Tier Storage Architecture (`blob_store.py`)

To prevent intermediate mathematical steps from contaminating public evidence packages, GroundTruth 2.0 partitions all data into four strictly isolated storage tiers:

```mermaid
flowchart LR
    T1["1. RAW_SOURCE<br/>• STAC COG Tiles<br/>• CHIRPS NetCDFs<br/>• Cold / Read-Only Cache"] --> T2["2. INTERMEDIATE<br/>• Windowed Chips<br/>• QA Bitmasks<br/>• Auto-Purged TTL"]
    T2 --> T3["3. FINAL_EVIDENCE<br/>• Immutable Bundles<br/>• Public Audit Reports<br/>• SHA-256 Verified"]
    T3 --> T4["4. METADATA<br/>• .meta.json Sidecars<br/>• Sigstore Manifests<br/>• Audit Logs"]
```

### Tier 1: `RAW_SOURCE`
- **Contents**: Unprocessed satellite rasters retrieved directly from upstream cloud STAC providers (e.g., USGS Landsat Collection 2 COGs, Copernicus Sentinel-2 L2A tiles, CHIRPS gridded pentads).
- **Access**: Read-only cache; immutable upon ingestion.

### Tier 2: `INTERMEDIATE_ARTIFACT`
- **Contents**: Intermediate pixel arrays, cloud-masked rasters, unharmonized zonal reductions, and SVD decomposition matrices.
- **Access**: Internal compute workers only. Automatically purged via TTL policies after verification completion.

### Tier 3: `FINAL_EVIDENCE`
- **Contents**: Auditable evidence packages (`EvidenceBundle`, `CausalReadinessAssessment`, `VerificationReport`).
- **Standard**: Every object carries complete `Provenance`, `EvidenceState`, and cryptographic SHA-256 fingerprints.

### Tier 4: `APPLICATION_METADATA`
- **Contents**: Cryptographic sidecars (`.meta.json`), Sigstore Cosign signature bundles, OpenAPI schemas, and append-only audit records.

---

## 2. Storage Backend Driver Abstraction

The factory function `get_storage_backend(profile)` returns the appropriate driver:

### 2.1 `LocalStorageBackend` (Workstation & CI)
- Writes objects to disk hierarchies (`./data/storage/<tier>/...`).
- Implements atomic writes via unique temporary files and POSIX `os.replace` to prevent corrupted reads during process interruption.
- Automatically generates companion `.meta.json` sidecars containing SHA-256 hashes and acquisition timestamps.

### 2.2 `S3StorageBackend` (Production)
- Compatible with AWS S3, MinIO, Cloudflare R2, and Google Cloud Storage (via S3 compatibility API).
- Enforces Server-Side Encryption (SSE-S3), bucket versioning, and pre-signed URL generation for direct client visualization.

---

## 3. Workstation vs. Production Deployment Profile

| Dimension | Workstation Development Profile | Cloud Production Profile |
| :--- | :--- | :--- |
| **Worker Concurrency** | Worker process (`apps/worker`) + `ProcessPoolExecutor` helpers | Scale-out worker replicas against shared DB / optional Redis+Arq |
| **Memory Allocation** | Bounded stream / chunked raster windows | Container memory limits; horizontal worker scaling |
| **Relational DB** | SQLite / Local PostgreSQL 16 container | High-availability managed PostgreSQL 16 (RDS) |
| **Blob Persistence** | `LocalStorageBackend` (`STORAGE_BACKEND=local`) | `S3StorageBackend` (AWS S3 / Cloudflare R2 / MinIO) |
| **Queue Backend** | SQL table row leases (`JobQueue`) | SQL row leases (default) or optional Redis/Arq & Temporal |
| **Telemetry** | Local logging (stdout / stderr) | OpenTelemetry Collector → Prometheus / Grafana |

![Kariba Overview](../product/screens/kariba-overview.png)
