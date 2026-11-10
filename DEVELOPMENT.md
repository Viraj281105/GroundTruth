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
| `genai` | `httpx>=0.27` | Downstream LLM REST narrative generation (Gemini, OpenAI, Anthropic, NuGen, Groq — strictly grounding-verified). |
| `db` | `sqlalchemy>=2.0`, `alembic>=1.13` | Relational persistence, multi-tenancy tables, and Alembic migrations (`0001`–`0012`). |
| `ingest` | `pystac-client`, `planetary-computer`, `rasterio` | Planetary Computer STAC scene discovery and windowed COG ingestion. |
| `geo` | `geopandas`, `shapely`, `rasterio`, `xarray`, `rioxarray` | Zonal statistics, polygon intersection, and coordinate projections. |
| `queue` | `redis>=5.0`, `arq>=0.26`, `temporalio>=1.5` | Optional Redis/arq and Temporal queue adapters, plus Redis rate limiting. |
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

### C. Background Worker (SQL Row-Lease Queue)
```bash
# Execute background analysis jobs with heartbeat, lease management, and observation ingestion polling
python -m apps.worker.main --migrate
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
        Pytest["Backend Suite (Pytest)<br/>2,130+ offline tests<br/>Contract boundaries · SCM · DiD · Auth · Gateways"]
        Vitest["Frontend Suite (Vitest)<br/>746 passing tests across 75 files<br/>Personas · 8 Dimensions · State Gating · Types"]
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
The web application features **746 passing automated tests across 75 test files**:

```bash
cd apps/web
npm test -- --run
```
Output:
```
 Test Files  75 passed (75)
      Tests  746 passed (746)
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

## 6. Responsive Mobile Web Support

Field auditors and project managers inspect dashboards on mobile viewports (`375 px`) through the responsive Next.js web application (`apps/web`). There is no separate native Android application in this repository; visual parity specs under `apps/web/e2e/visual.spec.ts` cover desktop and mobile browser viewports.

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
