# GroundTruth 2.0 — Developer & Contributor Guide

**One platform. Four perspectives. One scientifically consistent source of truth.**  
*Comprehensive developer guide for setting up, running, testing, and hardening the GroundTruth 2.0 platform.*

---

## 1. Quickstart: One-Command Execution

GroundTruth provides unified startup scripts for Windows, macOS, and Linux:

```powershell
# Windows (PowerShell)
.\run.ps1            # Starts Python venv, FastAPI API (:8000), and Next.js Web (:3000)
.\run.ps1 docker     # Starts full Docker stack: Postgres, Redis, API, Worker, Web
.\run.ps1 test       # Runs full Python pytest suite
```

```bash
# macOS / Linux (Bash)
./run.sh local       # Starts API and Next.js locally
./run.sh docker      # Boots Docker Compose environment
./run.sh test        # Executes all test suites
```

---

## 2. Local Environment Setup

### Prerequisites
- **Python:** 3.11 or higher (Python 3.11, 3.12, 3.13 supported)
- **Node.js:** v18.0.0 or higher (v20+ LTS recommended)
- **Git:** 2.40+
- **Docker & Docker Compose:** (Optional, for containerized multi-service deployment)
- **Android Studio / Android SDK:** (Optional, for `apps/mobile` Jetpack Compose development)

### Step-by-Step Installation

```bash
# 1. Clone repository
git clone https://github.com/Viraj281105/GroundTruth.git
cd GroundTruth

# 2. Configure Python Virtual Environment
python -m venv .venv

# Activate on Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Activate on macOS / Linux:
source .venv/bin/activate

# 3. Install GroundTruth package with development extras
pip install -e "packages/groundtruth[api,genai,dev,geo]"

# 4. Copy Environment Template
cp .env.example .env

# 5. Verify system readiness with doctor
groundtruth doctor
```

`groundtruth doctor` performs an honest audit of installed dependencies, cloud credentials, and real data assets. It explicitly notes which capabilities are active and which are fail-closed.

```mermaid
flowchart TD
    Setup["git clone & python -m venv .venv"] --> Pip["pip install -e packages/groundtruth[api,genai,dev,geo]"]
    Pip --> Env["cp .env.example .env"]
    Env --> Doctor["groundtruth doctor"]
    Doctor --> Choice{"Choose Mode"}
    Choice --> FullLocal["Run Local: Uvicorn (:8000) + Next.js (:3000)"]
    Choice --> DockerStack["Run Docker: docker compose up --build"]
```

---

## 3. Package Structure & Optional Extras

GroundTruth uses a modular dependency architecture. The core causal engine depends only on NumPy, Pandas, and Pydantic—heavy geospatial and cloud dependencies are isolated behind optional extras:

| Extra | Included Dependencies | Purpose |
|---|---|---|
| `core` | `numpy`, `pandas`, `pydantic>=2.0` | Pure deterministic causal engine and FISTA solver. Runs anywhere offline. |
| `api` | `fastapi`, `uvicorn`, `httpx` | REST API, OpenAPI schema generation, and HTTP routing. |
| `genai` | `google-genai` | Downstream Gemini narrative generation (strictly grounding-verified). |
| `geo` | `geopandas`, `shapely`, `rasterio`, `pyproj` | STAC zonal statistics, polygon intersection, and coordinate projections. |
| `dev` | `pytest`, `ruff`, `mypy`, `hypothesis` | Complete testing, linting, and static analysis toolchain. |

---

## 4. Running the Development Services

### A. FastAPI Backend Service
```bash
# Run API with live reloading on port 8000
uvicorn apps.api.main:app --reload --port 8000
# OpenAPI documentation available at: http://localhost:8000/docs
```

### B. Next.js 14 Web Frontend
The frontend features four tailored persona views (NGO, Funder, Auditor, Government) and comprehensive 8-dimension visualizations:

```bash
cd apps/web
npm install
npm run dev
# Web application available at: http://localhost:3000
```

### C. Background Worker (Celery & Database Queue)
```bash
# Execute background analysis jobs with heartbeat and lease management
python -m apps.worker.main
```

### D. Full Docker Compose Stack
Boot the production-grade multi-tenant stack with PostgreSQL and Redis:

```bash
docker compose up --build
```
Services instantiated:
- `postgres`: PostgreSQL 15 database storing tenants, projects, users, sessions, and `EvidenceBundle` records.
- `redis`: Redis 7 instance managing asynchronous job queues.
- `api`: FastAPI ASGI container (Port 8000).
- `worker`: Background analysis worker processing causal inference jobs.
- `web`: Next.js production build (Port 3000).

---

## 5. Comprehensive Test Execution

GroundTruth maintains an exhaustive, multi-layered automated testing regime:

```mermaid
flowchart TD
    subgraph TestSuites["Testing Architecture"]
        Pytest["Backend Suite (Pytest)<br/>1,466 collected tests<br/>Contract boundaries · SCM · DiD · Auth · Gateways"]
        Vitest["Frontend Suite (Vitest)<br/>542 passing tests across 57 files<br/>Personas · 8 Dimensions · State Gating · Types"]
        E2E["Playwright Persona E2E<br/>Auditor · Funder · NGO · Gov flows"]
        AST["AST Static Boundary Guard<br/>tests/test_contract_boundary.py"]
    end

    TestSuites --> CI["GitHub Actions Matrix CI (Python 3.11, 3.12, 3.13)"]
```

### Running Backend Tests (Pytest)
```bash
# Run the entire backend test suite
pytest

# Run specific functional test categories
pytest tests/auth/                        # Auth, Scrypt, session, and RBAC tests
pytest tests/engine/                      # FISTA solver, DiD, allometry, placebos
pytest tests/claims/                      # Adversarial grounding & defamation blocks
pytest tests/test_contract_boundary.py    # AST contract boundary enforcement
```

### Running Frontend Tests (Vitest)
The web application features **542 passing automated tests across 57 test files**:

```bash
cd apps/web
npm test -- --run
```
Output:
```
 Test Files  57 passed (57)
      Tests  542 passed (542)
   Duration  4.00s
```

### Checking Contract Boundaries and API Types
GroundTruth prevents schema drift between the Python backend and TypeScript frontend using automated OpenAPI synchronization:

```bash
# Verify TypeScript API types match the backend schema
cd apps/web
npm run check:api-types

# Regenerate TypeScript types from backend OpenAPI JSON
make api-types
```

---

## 6. Native Mobile Development (Jetpack Compose)

Field auditors and project managers capture evidence and review dashboards on mobile via `apps/mobile`:

```mermaid
flowchart LR
    A["Jetpack Compose UI<br/>(Material 3)"] --> B["ViewModel & StateFlow"]
    B --> C["Room SQLite Offline Cache"]
    C <-->|Retrofit2 Sync| D["FastAPI Backend (:8000)"]
```

### Mobile Views
The native client provides full parity with the web interface for offline inspection:

| Native Auditor Screen | Native NGO Screen |
| :---: | :---: |
| ![Native Auditor](docs/product/screens/compose-auditor-dashboard.png) | ![Native NGO](docs/product/screens/compose-ngo-dashboard.png) |

To run the mobile test suite or previews:
```bash
cd apps/mobile
./gradlew test
./gradlew assembleDebug
```

---

## 7. Daily Development Commands

| Command | Action |
|---|---|
| `ruff check packages tests` | Fast Python linting and code style inspection. |
| `ruff format packages tests` | Automated code formatting adhering to PEP 8 standards. |
| `mypy` | Strict static type checking across engine and platform. |
| `cd apps/web && npm run lint` | ESLint static analysis for Next.js components. |
| `groundtruth verify kariba-redd --synthetic` | Execute complete CLI verification run on Kariba synthetic benchmark. |

---

## 8. Fail-Closed Scientific Testing

A critical component of GroundTruth 2.0 is testing that the platform **fails closed** when empirical rasters are missing, preventing the accidental presentation of synthetic data under a real label:

```python
# tests/test_fail_closed.py
def test_real_observations_mode_raises_when_rasters_missing():
    """Verify that REAL mode refuses to guess when data is incomplete."""
    request = AnalysisRequest(
        case_id="kariba-redd",
        data_mode=DataMode.REAL_OBSERVATIONS,
    )
    with pytest.raises(DataUnavailableError) as exc_info:
        run_analysis(request, data_access=live_data_access)
    
    assert "pre-treatment panel incomplete" in str(exc_info.value)
```

This fail-closed architecture guarantees that no fabricated or synthetic values can ever be silently served to auditors or the public.

---

> GroundTruth 2.0 Development Guide · *PCCOE International Grand Challenge 2026*
