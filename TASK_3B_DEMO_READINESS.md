# TASK 3B: GroundTruth End-to-End Demo Readiness Inventory

**Evaluation Date:** November 8, 2026  
**Target Completion / Submission Date:** November 10, 2026  
**Auditor:** Independent Technical Verification (Pair Programming Agent)  
**Assessment Mode:** READ-ONLY Codebase & Architecture Audit  

---

## Executive Summary & Overall Readiness Verdict

### Overall Readiness: **PARTIAL**

| Category | Status | Summary |
| :--- | :---: | :--- |
| **Pre-Configured Offline Kariba Demo** | **READY** | Evaluators can immediately inspect the Kariba REDD+ investigation using offline synthetic benchmark fixtures (`data/synthetic_fixtures/kariba_synthetic_benchmark.json`) and precomputed UI state. The frontend UI renders counterfactual charts, placebo permutations, donor weightings, specification curves, and provenance drawers. |
| **Interactive Analysis Pipeline (Synthetic)** | **READY** | Real-time analysis execution works end-to-end via CLI (`groundtruth verify kariba-redd --synthetic` or `--synthetic-fixture`) and through the background worker / jobs API (`POST /jobs` + SSE/polling). Engine execution takes 2.3–3.8 seconds. |
| **Real Earth-Observation Ingestion** | **NOT READY** | Live satellite ingestion (Sentinel-2 / Landsat via Google Earth Engine) is explicitly un-implemented (`earth_engine_access` raises `DataUnavailableError` / HTTP 501; `earth_observation_implemented: false`). |
| **Real STAC & Climate Cache Integration** | **PARTIAL** | Real Sentinel-2 STAC L2A cache exists (`data/processed/stac_cache/`), but only covers 3 post-treatment years (2021–2023) for Kariba with **0 donors**. Real CHIRPS/NASA POWER climate data exists (`data/processed/climate_cache/`, 1981–2023), and climate confounding diagnostics are implemented in `engine/causal/climate_confounding.py`, but are **not yet hooked into the primary verification pipeline or API**. |
| **Report Generation & Export** | **PARTIAL** | Deterministic narrative reports and raw HTTP endpoints for institutional CSV and `%PDF-1.4` exports exist on the backend (`GET /cases/{case_id}/export/csv`, `GET /cases/{case_id}/export/pdf`), but the frontend `ReportView.tsx` has **no download buttons** wired to these endpoints (evaluators are prompted to use browser Ctrl+P). |
| **RBAC / Authentication Flow** | **PARTIAL / RISK** | The local database (`data/interim/groundtruth.db`) has **zero registered users**. While `AUTH_ALLOW_REGISTRATION=true` is enabled, `NewCaseForm.tsx` omits `credentials: 'include'`, breaking case creation behind auth. |

---

## 1. Application Startup & Infrastructure Inventory

### 1.1 Startup Commands

#### Option A: Native Local Development (Recommended for Offline Evaluation)

The project provides an automated PowerShell runner (`run.ps1`) and shell script (`run.sh`):

```powershell
# 1. Setup virtual environment, dependencies, and Next.js frontend
.\run.ps1 setup

# 2. Start both FastAPI Backend (:8000) and Next.js Frontend (:3000)
.\run.ps1 local
```

**Under the hood, these run:**
- **Backend API (Uvicorn):**
  ```powershell
  .venv\Scripts\python.exe -m uvicorn apps.api.main:app --port 8000 --host 0.0.0.0
  ```
  *(Reference: `GroundTruth/run.ps1:22`, `GroundTruth/apps/api/main.py:14`)*
- **Background Worker (Async Job Execution):**
  ```powershell
  .venv\Scripts\python.exe -m apps.worker.main
  ```
  *(Reference: `GroundTruth/apps/worker/main.py:24`, `GroundTruth/apps/worker/README.md`)*
- **Frontend Web UI (Next.js 14):**
  ```powershell
  cd apps\web
  $env:NEXT_PUBLIC_API_URL = "http://localhost:8000"
  npx next dev -p 3000
  ```
  *(Reference: `GroundTruth/run.ps1:25-26`, `GroundTruth/apps/web/package.json`)*

#### Option B: Containerized Deployment (Docker Compose)

```powershell
docker compose up --build
# or: .\run.ps1 docker
```
- **Containers Defined:** (`GroundTruth/docker-compose.yml:3-55`)
  1. `postgres`: `postgres:16-alpine` on internal port 5432 with health check.
  2. `api`: Builds `infrastructure/docker/backend.Dockerfile`, exposes port `8000:8000`.
  3. `worker`: Builds `infrastructure/docker/backend.Dockerfile`, runs `python -m apps.worker.main --migrate`.
  4. `web`: Builds `infrastructure/docker/web.Dockerfile`, exposes port `3000:3000` with build arg `NEXT_PUBLIC_DEMO_MODE=true`.

---

### 1.2 Environment Variables & Configuration

The application is configured via `.env` (`GroundTruth/.env`) and `.env.local` (`GroundTruth/apps/web/.env.local`).

| Variable | Current Active Value | Default / Expected | Impact on Demo |
| :--- | :--- | :--- | :--- |
| `APP_ENV` | `development` | `development` | Enables debug logging and local SQLite path |
| `RANDOM_SEED` | `20260101` | `20260101` | Ensures 100% deterministic, reproducible pseudo-random outputs |
| `DATABASE_URL` | `sqlite:///data/interim/groundtruth.db` | Unset / Postgres | Local SQLite database. Enables persistent stored runs and background jobs |
| `API_HOST` / `PORT` | `0.0.0.0:8000` | `0.0.0.0:8000` | API service binding |
| `FRONTEND_URL` | `http://localhost:3000` | `http://localhost:3000` | Allowed CORS origin |
| `CORS_ALLOWED_ORIGINS`| `http://localhost:3000` | `http://localhost:3000` | Browser origins permitted to call API |
| `AUTH_REQUIRED` | `true` | `false` (code default) | **Enforces authentication for runs and case creation** |
| `AUTH_COOKIE_SECURE` | `false` | `false` | Allows HTTP session cookies on `localhost` |
| `AUTH_ALLOW_REGISTRATION` | `true` | `true` | Allows new evaluators to self-register as admin |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | `http://localhost:8000` | Browser API target |
| `NEXT_PUBLIC_DEMO_MODE` | `true` | `false` | **Critical:** Permits precomputed simulation fixtures in UI when backend un-run |
| `GENAI_PROVIDER` | `none` | `none` | Uses deterministic report renderer (no LLM keys required) |
| `GEE_SERVICE_ACCOUNT_JSON` | *Unset* | Optional | Real Earth Engine ingestion not implemented (safe to leave blank) |

---

### 1.3 Database Initialization & Migrations

- **Migration Tool:** Alembic (`GroundTruth/packages/groundtruth/src/groundtruth/platform/store/migrate.py`)
- **Schema Head Revision:** `0006_auth_users_and_sessions`
- **Current Database Status:** `data/interim/groundtruth.db` is migrated to head (`0006`).
- **Initial Table State:**
  - `cases`: Populated with synced project YAML definitions.
  - `analysis_runs`: 1 pre-existing stored successful run.
  - `evidence_bundles`: 1 pre-existing verified evidence bundle.
  - `users`: **Empty (`0` rows)**. First user to register will automatically receive role `admin` (`GroundTruth/packages/groundtruth/src/groundtruth/platform/auth/service.py:112`).
- **Manual Initialization Command (if resetting database):**
  ```powershell
  .venv\Scripts\python.exe -m apps.worker.main --migrate
  ```

---

### 1.4 External Services, Credentials & Network Dependencies

- **Fully Offline Capable:**
  - Synthetic pipeline (`--synthetic` and `--synthetic-fixture`) runs **100% offline** with zero external network calls.
  - Deterministic report generator requires no OpenAI/Gemini/Anthropic API keys.
  - Map visualization (`MapCanvas.tsx`) renders vector GeoJSON via MapLibre GL without external tile server requirements.
- **Services Requiring Live Credentials (Not needed for offline demo):**
  - Google Earth Engine (`GEE_SERVICE_ACCOUNT_JSON`): Planned for milestone M1. Currently raises `DataUnavailableError`.
  - Microsoft Planetary Computer STAC: Required only if re-running raw satellite downloading scripts.
  - CHIRPS / NASA POWER: Used by data-fetching scripts (`fetch_real_stac.py`, `climate.py`), but output is already cached in `data/processed/`.

---

## 2. Complete Evaluator Journey: Step-by-Step Experience

Below is the verified end-to-end path an evaluator takes when inspecting the Kariba restoration investigation:

```
[1. Application Startup]
       │
       ▼
[2. Home Landing Page]  ──> Hero counterfactual preview & methodology highlights
       │
       ▼
[3. Cases Browser]      ──> Select "Kariba REDD+ Project (VCS 902)"
       │
       ├───> [4A. Overview Tab]   ──> Headline effect (-0.0547 NDVI), Inconclusive verdict, "NDVI is not carbon"
       │
       ├───> [4B. Evidence Tab]   ──> Counterfactual chart, Placebo histogram, Donor ranking, Interactive Playground
       │
       ├───> [4C. Robustness Tab] ──> Specification curve, DiD cross-check, Leave-one-out sensitivity
       │
       ├───> [4D. Method Tab]     ──> 6-stage causal pipeline ladder & parameter gates
       │
       ├───> [4E. Report Tab]     ──> Deterministic narrative report & formal citation
       │
       └───> [4F. Run Tab]        ──> Live execution against synthetic control engine (Auth required)
```

### Step 1: Accessing the Kariba Investigation
- **URL:** `http://localhost:3000/cases/kariba-redd`
- **Backend Route:** `GET /cases/kariba-redd` (`GroundTruth/packages/groundtruth/src/groundtruth/platform/api/app.py:165-187`)
- **Case Configuration:** Loaded from `GroundTruth/cases/kariba-redd.yaml`.
  - Area: 784,987 ha (forested accounting area inside 1,077,930 ha RDC boundary).
  - Pre-intervention baseline window: 2001–2010.
  - Post-intervention evaluation window: 2011–2022.
  - Target Indicator: `ndvi` (Normalized Difference Vegetation Index).
  - Validation reference: Verra 2025 finding of ~57% excess credit issuance (treated as independent validation target, never as model input; lines 105–120).

### Step 2: AOI & Spatial Boundary Inspection
- **Project Boundary Route:** `GET /cases/kariba-redd/boundary.geojson` (`GroundTruth/packages/groundtruth/src/groundtruth/platform/api/tiles.py:45-73`)
- **Boundary Assets:** `GroundTruth/cases/boundaries/kariba-redd.geojson` (101 KB, 4 RDC parcels) and `kariba-donors.geojson` (1.67 MB, 80 candidate ADM2 regions).
- **UI Component:** `DonorMap.tsx` and `MapCanvas.tsx` (`GroundTruth/apps/web/src/features/case/map/DonorMap.tsx`).
- **Visuals:** Renders the project perimeter, bounding box coordinates, and shades admitted donor control districts according to synthetic control weights.

### Step 3: Satellite Observations & Climate Context
- **Observation Discrepancy Note:** The UI clearly notes that the current benchmark uses the synthetic calibration fixture (`data/synthetic_fixtures/kariba_synthetic_benchmark.json`).
- **Real Cached Observations Available on Disk:**
  - Real Sentinel-2 L2A zonal composites for Kariba exist in `data/processed/stac_cache/kariba-redd__ndvi.json` (2021–2023).
  - Real CHIRPS monthly rainfall (5.5km) & NASA POWER MERRA-2 temperatures exist in `data/processed/climate_cache/kariba_chirps_climate.json` (1981–2023).
- **UI Display:** Shows annual NDVI trajectory from 2001 through 2022, capturing pre-treatment parallel trends and post-2011 intervention divergence.

### Step 4: Donor Pool Selection & Causal Diagnostics
- **Admitted vs. Excluded Donors:** 80 candidates evaluated; 50 admitted; 30 excluded (`kariba-redd.yaml:83-97`).
  - Spatial exclusions: 10km leakage belt buffer around Lake Kariba and cross-border Zambezi districts (`zm-luangwa`, `zm-gwembe`, `zm-siavonga`, `zm-chirundu`).
  - Overlap exclusions: Project host RDCs (`zw-hurungwe`, `zw-binga`, `zw-mbire`, `zw-nyaminyami`).
- **Covariate Balance:** Standardized Mean Differences (SMDs) evaluated across rainfall, elevation, slope, road distance, and population density (`assembler.py:186-190`).
- **Convex Hull Check:** Verifies treated unit is inside the donor convex hull (`fit.inside_donor_hull = True`).

### Step 5: Evidence Interpretation & The Verdict
- **Verdict Panel:** Returns **`INCONCLUSIVE`** (`VerdictPanel.tsx`).
- **Scientific Integrity Principle:** The rationale explicitly states:
  > *"INCONCLUSIVE / NOT CALIBRATED: an effect on the observed indicator was estimated, but it cannot be expressed in tCO2e because no validated, site-calibrated biomass model is available... NDVI is not carbon."*
- **Role Lenses:**
  - **Story Lens:** Plain English summary explaining the estimate and uncertainty.
  - **Explorer Lens:** Detailed charts, donuts, donor weights, and the interactive Playground.
  - **Auditor Lens:** Cryptographic SHA-256 provenance fingerprints for every single metric.

### Step 6: Interactive Counterfactual Playground
- **Component:** `GroundTruth/apps/web/src/features/case/playground/Playground.tsx`
- **Evaluator Actions:**
  - Slide intervention year between 2001 and 2022.
  - Toggle individual contributing donor districts (e.g. disable `zm-mumbwa` or `zw-buby`) to observe real-time counterfactual shift and sensitivity.

### Step 7: Report Generation & Institutional Export
- **Screening Report View:** `http://localhost:3000/cases/kariba-redd/report`
- **Exports (Backend endpoints):**
  - CSV Export: `http://localhost:8000/cases/kariba-redd/export/csv`
  - PDF Export: `http://localhost:8000/cases/kariba-redd/export/pdf`

---

## 3. Frontend / Backend Integration & Discrepancy Audit

### 3.1 Connected Screens vs. API Endpoints

| Frontend Route | Primary Component | Backend API Route | Data Source / Status |
| :--- | :--- | :--- | :--- |
| `/` | `features/home/CounterfactualHero.tsx` | N/A | Static marketing & hero chart |
| `/cases` | `features/cases/CasesBrowser.tsx` | `GET /cases` | **Connected** to SQLite / registry |
| `/cases/new` | `features/cases/NewCaseForm.tsx` | `POST /cases` | **Integration Defect:** Missing `credentials: 'include'` |
| `/cases/[id]` | `features/case/overview/OverviewView.tsx` | `GET /cases/{id}` | **Connected** (displays fixture or stored run) |
| `/cases/[id]/evidence` | `features/case/evidence/EvidenceView.tsx` | `GET /cases/{id}` & `GET /runs/{id}` | **Connected** (reads fixture or run bundle) |
| `/cases/[id]/robustness` | `features/case/robustness/RobustnessView.tsx` | `GET /cases/{id}` & `GET /runs/{id}` | **Connected** (parses spec curve & DiD evidence) |
| `/cases/[id]/method` | `features/case/method/MethodView.tsx` | `GET /cases/{id}` | **Connected** |
| `/cases/[id]/report` | `features/case/report/ReportView.tsx` | `GET /cases/{id}` | **Connected** to fixture markdown |
| `/cases/[id]/run` | `features/run/RunFlow.tsx` | `POST /jobs`, `GET /jobs/{id}`, `GET /runs/{id}` | **Connected** to background worker and store |
| `/compare` | `features/compare/ComparePage.tsx` | `GET /cases`, `GET /cases/{id}` | **Connected** |
| `/status` | `features/status/StatusView.tsx` | `GET /health`, `GET /runs` | **Connected** |
| `/claims` | `features/claims/ClaimsWorkbench.tsx` | `POST /claims/analyze`, `POST /claims/extract-pdf` | **Connected** |
| `/login`, `/register` | `features/auth/AuthForms.tsx` | `POST /auth/login`, `POST /auth/register` | **Connected** |

---

### 3.2 Mocked Data, Placeholders & Hardcoded Gaps

1. **`NEXT_PUBLIC_DEMO_MODE` Fixture Precedence:**
   - In `apps/web/src/features/case/evidence/useCaseEvidence.ts:48-52`, `getVisualizationFixture(caseId)` is loaded **before** checking URL query parameter `?run=<id>`.
   - **Consequence:** When `NEXT_PUBLIC_DEMO_MODE=true` is set, visiting `/cases/kariba-redd/evidence` will **always render the static fixture**, even if the evaluator just completed a new run in the `/run` tab.
2. **Missing Time-Series in Backend Result API:**
   - The backend `VerificationResponse` and `RunDetail` schemas (`schemas.py:121, 293`) transmit scalar `EvidenceBundle.items` and summaries, but **do not transmit the full time-series array (`counterfactual_path`)**.
   - As noted in `simulated-data.ts:173` and `generated.ts`, `counterfactual_path`, `placebo_distribution`, and `donor_pool` coordinates are bundled under `not_served_by_api`.
   - **Consequence:** If demo mode is turned off (`NEXT_PUBLIC_DEMO_MODE=false`), a newly executed run displays "Not available: this analysis produced no counterfactual series" for the main chart (`EvidenceView.tsx:67`).
3. **ADR-011 Donor Candidate Summary Placeholder:**
   - In `apps/web/src/lib/api.ts:278-304`, `getDonorCandidateSummary()` explicitly returns `null` for all candidate counts (`resultState: 'not_started'`).
   - The docstring confirms: *"There is currently no HTTP endpoint serving this. EarthEngineUnitConstruction raises DataUnavailableError on every call."*
4. **Disconnected PDF/CSV Export Endpoints:**
   - Backend `exports.py` (`packages/groundtruth/src/groundtruth/platform/api/exports.py:41, 59`) implements high-fidelity binary PDF and CSV downloads:
     - `GET /cases/{case_id}/export/csv`
     - `GET /cases/{case_id}/export/pdf`
   - However, `ReportView.tsx:22, 107` has **no `<a href="...">` or `<button>` downloading these files**, only displaying a notice: *"Use your browser print dialog (Ctrl or Cmd + P) to save this page as a PDF."*
5. **Climate Confounding Engine Integration Gap:**
   - A 1,037-line, rigorous climate confounding module exists in `GroundTruth/packages/groundtruth/src/groundtruth/engine/causal/climate_confounding.py`, with unit tests in `tests/engine/test_climate_integration.py`.
   - However, `run_climate_confounding_analysis()` is **not imported or invoked** in `GroundTruth/packages/groundtruth/src/groundtruth/engine/run.py` or exposed in `GroundTruth/packages/groundtruth/src/groundtruth/platform/api/app.py`.

---

## 4. Real vs. Synthetic Data Inventory

| Asset Name | Location | Declared Origin | Genuine Origin | Usable in Demo? | Notes |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Kariba Benchmark Fixture** | `data/synthetic_fixtures/kariba_synthetic_benchmark.json` | `synthetic` | **Synthetic** | **YES** | 2000–2023 annual series for Kariba + 50 donors. Explicitly watermarked `synthetic: true`. |
| **Synthetic Replay Cache** | `apps/web/src/lib/fixtures/generated/kariba-redd.completed.json` | `synthetic` | **Synthetic** | **YES** | Pre-generated from engine run for instant UI rendering. |
| **Real Sentinel-2 STAC Cache** | `data/processed/stac_cache/kariba-redd__ndvi.json` | `real_stac` | **Genuine Satellite** | **NO (Insufficient)** | Real Sentinel-2 L2A zonal composites from Microsoft Planetary Computer, but **only 3 years (2021–2023) and 0 donors**. Cannot fit pre-2011 baseline. |
| **Real CHIRPS Climate Cache** | `data/processed/climate_cache/kariba_chirps_climate.json` | `observed` | **Genuine Climate** | **PARTIAL** | 514 months (1981–2023) of CHIRPS 5.5km precipitation + NASA POWER temperature. Verified by test suite, but not wired to UI. |
| **Kariba Project Boundary** | `cases/boundaries/kariba-redd.geojson` | `observed` | **Genuine Registry** | **YES** | 4 RDC boundary parcels extracted from Verra VCS 902 KML document. |
| **Kariba Donor Boundaries** | `cases/boundaries/kariba-donors.geojson` | `observed` | **Genuine Registry** | **YES** | geoBoundaries v6.0.0 ADM2 boundaries for Zimbabwe and Zambia. |
| **Raw Project Document** | `data/raw/FI-VL798LB80E6302132020094433.pdf` | `observed` | **Genuine Registry** | **YES** | 4.0 MB VCS verification report for Kariba REDD+. Usable in Claims Workbench. |

---

## 5. Demo-Breaking Risks Ranked by Severity

### Critical Severity (Must be handled during demonstration)

1. **Authentication Gate Blocks Unregistered Evaluators:**
   - **Location:** `GroundTruth/.env:48` (`AUTH_REQUIRED=true`), `GroundTruth/packages/groundtruth/src/groundtruth/platform/api/jobs.py:55`.
   - **Risk:** An evaluator navigating directly to `/cases/kariba-redd/run` will see `<RequireAuth action="run analyses">` or receive HTTP 401. Since the local SQLite database has 0 registered users, they cannot log in without first registering.
   - **Mitigation:** The presenter must either:
     a) Register an account (e.g. `evaluator@groundtruth.org`) via `/register` at the start of the demo, OR
     b) Set `AUTH_REQUIRED=false` in `.env` for the competition session.

2. **New Case Creation Fails Behind Auth:**
   - **Location:** `GroundTruth/apps/web/src/features/cases/NewCaseForm.tsx:166-170`.
   - **Risk:** In `NewCaseForm.tsx`, the `fetch` call to `${getApiBaseUrl()}/cases` does not specify `credentials: 'include'`. Even if logged in, the browser will not send session cookies across ports (`:3000` to `:8000`), resulting in HTTP 401 unauthenticated and displaying *"Could not create project. Ensure you are signed in."*
   - **Mitigation:** Do not attempt live project creation via `NewCaseForm.tsx` during the demo unless fixed, or ensure `AUTH_REQUIRED=false`.

### Moderate Severity

3. **Background Worker Must Be Running For `/run` Tab:**
   - **Location:** `GroundTruth/apps/worker/main.py`.
   - **Risk:** If the evaluator clicks "Start Analysis" on `/cases/kariba-redd/run` while only Uvicorn is running, the job will remain permanently in `queued` status because the background worker is not running to lease the job.
   - **Mitigation:** Ensure `python -m apps.worker.main` is running in a terminal alongside Uvicorn, or run via Docker Compose (`docker compose up`).

4. **Missing Download Buttons for Generated PDF/CSV Reports:**
   - **Location:** `GroundTruth/apps/web/src/features/case/report/ReportView.tsx:107`.
   - **Risk:** Evaluators expect a "Download Audit PDF" button. They will be confused when only browser printing is suggested.
   - **Mitigation:** Directly demonstrate opening the API endpoints `http://localhost:8000/cases/kariba-redd/export/pdf` and `http://localhost:8000/cases/kariba-redd/export/csv` in a browser tab.

5. **`NEXT_PUBLIC_DEMO_MODE=true` Overrides Newly Executed Runs:**
   - **Location:** `GroundTruth/apps/web/src/features/case/evidence/useCaseEvidence.ts:48-52`.
   - **Risk:** If an evaluator runs an analysis on `/cases/kariba-redd/run` and then clicks "View Evidence", the evidence tab reloads the static fixture rather than the newly completed run ID.
   - **Mitigation:** In the `/run` tab, show the live progress theater and completion state, then explain that the Evidence view inspects the verified baseline benchmark.

---

## 6. Recommended Minimum Fixes Before November 10

To make the demonstration 100% robust without redesigning major subsystems:

1. **Add `credentials: 'include'` to `NewCaseForm.tsx`:**
   - *File:* `GroundTruth/apps/web/src/features/cases/NewCaseForm.tsx` (Line 167)
   - *Fix:* Add `credentials: 'include'` to the `fetch` options so session cookies are passed to `POST /cases`.
2. **Add Direct Download Buttons to `ReportView.tsx`:**
   - *File:* `GroundTruth/apps/web/src/features/case/report/ReportView.tsx`
   - *Fix:* Add `<a href={`${API_BASE_URL}/cases/${caseId}/export/pdf`} download>` and CSV download buttons next to "Cite this report".
3. **Pre-seed an Evaluator Account in SQLite:**
   - *File:* `GroundTruth/data/interim/groundtruth.db`
   - *Fix:* Register `admin@groundtruth.org` / `GroundTruth2026!` during initialization so evaluators do not hit an empty login screen.
4. **Wire Climate Confounding Diagnostic to Report Output:**
   - *File:* `GroundTruth/packages/groundtruth/src/groundtruth/platform/reports/narrative.py`
   - *Fix:* Expose the CHIRPS precipitation anomaly and SPI drought indicator metrics in the evidence summary table.

---

## 7. Proposed 5–7 Minute Competition Demonstration Sequence

| Timestamp | Screen / Step | Action & Key Talking Points |
| :---: | :--- | :--- |
| **0:00 – 1:00** | **System Startup & Health**<br>`http://localhost:3000/status`<br>`groundtruth doctor` | • Show `groundtruth doctor` in terminal: honest capability reporting.<br>• Highlight that GroundTruth refuses to pretend un-implemented satellite ingestion is working (`earth_observation_implemented: false`).<br>• Show system status screen verifying local engine version `0.10.0` and contract `1.0.0`. |
| **1:00 – 2:15** | **Kariba REDD+ Overview & Boundaries**<br>`/cases/kariba-redd` | • Open Kariba REDD+ investigation (VCS 902).<br>• Point out the VCS project area (784,987 ha forested portion vs. 1,077,930 ha RDC boundary).<br>• Switch lenses: show **Story Lens** (plain English for policymakers) vs **Auditor Lens** (scientific audit).<br>• View `DonorMap`: show actual geoBoundaries ADM2 polygons and the 10km leakage belt buffer around Lake Kariba. |
| **2:15 – 3:45** | **Evidence & Scientific Integrity**<br>`/cases/kariba-redd/evidence` | • Show counterfactual NDVI chart (2001–2010 pre-period fit, 2011–2022 intervention gap).<br>• **Key Scientific Rule:** Show why the verdict is **`INCONCLUSIVE`**: GroundTruth refuses to convert NDVI directly to carbon credits without validated field calibration ("NDVI is not carbon").<br>• Inspect Placebo Diagnostics: in-space permutation test confirming significance.<br>• Open Provenance Drawer: click on any evidence metric to show the SHA-256 fingerprint, source URL, and exact execution method. |
| **3:45 – 4:45** | **Counterfactual Playground & Robustness**<br>`/cases/kariba-redd/robustness`<br>`/cases/kariba-redd/evidence#playground` | • Open the Interactive Playground: change the intervention year and toggle donor weights in real time.<br>• Switch to Robustness tab: demonstrate the **Specification Curve** (testing the estimate across alternative donor pool sizes and pre-periods) and the **Difference-in-Differences cross-check**. |
| **4:45 – 5:45** | **Live Analysis Execution & Worker**<br>`/cases/kariba-redd/run` | • Navigate to the Run tab.<br>• Click "Start Analysis": show the Theatre progress stepper through stages (`claim`, `data`, `engine`, `assembly`).<br>• Explain the background job leasing architecture (`FOR UPDATE SKIP LOCKED` / SQLite task queue). |
| **5:45 – 6:30** | **Claims Workbench & Document Extraction**<br>`/claims` | • Open Claims Workbench.<br>• Load the Kariba REDD+ sample document (or upload `data/raw/FI-VL798LB80E6302132020094433.pdf`).<br>• Click "Analyze Claims": rule-based parser extracts project area (784,987 ha) and claimed credits (26.8M tCO2e), comparing them directly against registered benchmarks. |
| **6:30 – 7:00** | **Institutional Report & Conclusion**<br>`/cases/kariba-redd/report`<br>`:8000/cases/kariba-redd/export/pdf` | • Show the narrative screening report.<br>• Open `http://localhost:8000/cases/kariba-redd/export/pdf` in a browser tab to demonstrate the institutional `%PDF-1.4` document with embedded provenance and calibration warnings.<br>• Conclude: GroundTruth delivers verifiable, conservative causal screening with complete audit trails. |

