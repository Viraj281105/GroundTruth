# GroundTruth 2.0 — Changelog

**One platform. Four perspectives. One scientifically consistent source of truth.**  
*All notable changes to the GroundTruth ecosystem are documented here, following [Keep a Changelog](https://keepachangelog.com/) conventions and [Semantic Versioning](https://semver.org/).*

```mermaid
flowchart LR
    v0["v0.1.0 – v0.10.0<br/>Prototype Engine & Scaffolding"] --> v1["v1.0.0<br/>Causal Engine, FISTA & AST Guards"]
    v1 --> v2["v2.0.0 (GroundTruth 2.0)<br/>4 Personas · 8 Dimensions · 542 Vitest Tests · Fail-Closed Gateways"]
```

---

## [2.0.0] — 2026-11-09: GroundTruth 2.0 (Enterprise Multi-Tenant Release)

### Added
- **Four Tailored Personas & Dashboards:**
  - **Restoration NGO / Developer Dashboard:** Boundary parcel registration (GeoJSON), multi-spectral vegetation tracking (NDVI/EVI/NDMI/NBR), ground truth data logging, and climate drought defense.
  - **CSR & Impact Funder Portfolio:** Pre-purchase additionality screening, ESG audit defense, portfolio additionality radar, and non-accusatory accredited review triggers.
  - **Auditor / MRV Dashboard:** Complete STAC scene discovery, sensor continuity audits, cryptographic SHA-256 evidence chain verification, and fail-closed inspection.
  - **Government & Regulator Dashboard:** Regional territorial conservation tracking, administrative district comparisons (geoBoundaries ADM2), 10 km leakage belt monitoring, and SPI-12 emergency tracking.
- **8-Dimension Ecological Assessment Framework:**
  - Evaluates projects across 8 orthogonal dimensions: Trajectory, Spatial, Climate, Risk, Progress, Comparison, Evidence Quality, and Attribution.
- **Graduation Ladder (Levels 0 through 5):**
  - Discrete progression from Level 0 (Unverified Claim) to Level 5 (Accredited Carbon Verification). Kariba REDD+ successfully graduated to **Level 2 (Contextual Intelligence)**.
- **Empirical Climate & Drought Intelligence Layer:**
  - Ingestion of 43 years (1981–2023) of monthly CHIRPS rainfall across 514/516 months with honest missingness flags.
  - NASA POWER temperature integration (T2M, Tmax, Tmin) and 12-month Standardized Precipitation Index (SPI-12) drought analytics across 50 districts.
- **Real Sentinel-2 L2A Earth Observation:**
  - Real 10m surface reflectance indices (NDVI/EVI/NDMI/NBR) for Kariba's 784,987 ha parcel across 2021–2023 with scene-level STAC provenance.
- **Task 5/5B Independent Audit Remediation & Fail-Closed Gateways:**
  - Quarantined all fabricated Landsat caches generated in earlier tasks.
  - Implemented fail-closed gateways: when requested in `REAL_OBSERVATIONS` mode, if pre-treatment satellite rasters are incomplete, the engine raises `DataUnavailableError` and returns `HTTP 501`, refusing to guess or interpolate.
  - Honestly reported Kariba causal attribution as **`INCONCLUSIVE (Not Estimable from Real Data Alone)`** until complete multi-tile historical rasters are harmonized.
- **Android Native Mobile Client (Jetpack Compose):**
  - Full-featured offline-first mobile application in `apps/mobile` built with Kotlin, Jetpack Compose, Material 3, and Room SQLite, with verified Compose Previews.
- **Expanded Test Suites:**
  - **542 passing automated tests** in `apps/web` across 57 Vitest test files.
  - **1,466 collected backend tests** in Pytest covering causal models, AST boundary enforcement, Scrypt auth, and fail-closed gateways.
- **Enterprise Multi-Tenant Security & RBAC:**
  - Organization boundaries, project grants, Scrypt password hashing ($N=32768, r=8, p=1$), timing attack mitigation, and session cookies with HttpOnly, SameSite, and Secure flags.
  - Row-level tenant isolation returning `HTTP 403 Forbidden` on unauthorized cross-tenant queries.

### Added on `bhumi-dev`: resilience and end-to-end runs (#48, #49)
- **Circuit breakers (#48).** One `CircuitBreaker` in the existing resilience module, one per provider per
  process (Earth Engine, Gemini, Anthropic): five failures in a row (each after its retries) open it for
  60 s, then one trial call decides. Bad credentials never open it. An open Earth Engine circuit is
  `data_unavailable`, never a fixture; an open GenAI circuit is a labelled deterministic fallback (inline) or
  `narration_failed` (export). Counted in `gt_circuit_open_total{provider}`.
- **Timeouts on every external call (#48).** Added: Redis 5 s, PostgreSQL connect 10 s, S3 5 s connect /
  30 s read with 3 attempts. Already present: Earth Engine 360 s, GenAI 60 s. The offline STAC ingest
  (PR #87's `data_access/stac.py`) has none yet; flagged.
- **A run from the UI again (#49).** `/app/<org>/projects/<project>/run` renders the run flow, which no 2.0
  page could reach (the legacy page redirected to a missing route). It gains an optional "Minimum comparison
  areas" that can only make the test stricter, and an honest "Lost contact" outcome that keeps the run id
  when the API goes away mid-run, after 30 s of silence instead of on the first failed read.
- **End-to-end runs (#49).** The e2e stack starts a worker; `runs.spec.ts` covers the happy path, a refusal
  shown as a designed outcome, a minimum below the floor, cancelling a running job, and a lost API, all on
  the real stack. `.github/workflows/e2e.yml` runs the suite on every pull request, and by hand against a
  deployed environment. The worker's `--pause-before-engine` (a testing aid) is refused in production.

### Added on `bhumi-dev`: replay harness, simulation pin and performance (#42, #47)
- **Reproducibility replay (#42).** `groundtruth-replay` replays every stored run from its own
  stored request (proven to hash to its `spec_hash`), through `run_analysis` only, and compares
  it item by item with #35's diff (relative `1e-9`; verdict, status and refusal code exact). A
  difference within one engine version fails (exit 1); across versions it is reported as expected
  change; observed-data runs whose data is unavailable are skipped with the reason, never replayed
  on simulated data. Five golden stored runs, made by the real simulated path (completed, refused,
  Viraj's golden spec, an unpinned legacy run, a second case), are replayed on every push and
  daily at 04:30 UTC on Python 3.11 to 3.13 (`.github/workflows/replay.yml`).
- **The simulation is part of the specification.** A simulated run's injected `true_effect` was
  recorded nowhere, so two runs with different effects shared a `spec_hash`: the cache could
  answer one with the other and a replay could not know which effect to use. `POST /jobs` and
  `/verify` now pin it as a synthetic dataset (`groundtruth-synthetic-simulation`), which the
  contract already supports; the worker runs the pinned effect. New simulated runs therefore have
  new `spec_hash`es. Viraj's golden snapshot and the web fixtures are unchanged.
- **Performance (#47).** Two queries degraded with run count and are now indexed (migration
  0008): every tenant-scoped run listing (`analysis_runs.project_id`, unindexed since 0007) and
  the lease reaper every claim runs first (`jobs.lease_expires_at`, a full scan of every job ever
  run). A test checks the query plan of every listing, the claim, the reaper and the cache lookup.
  Jobs have a lane: `POST /jobs` is interactive and is always claimed before batch work (the CLI,
  a new case's first run); `WORKER_BATCH_MAX_RUNNING` optionally caps running batch jobs.

### Added on `bhumi-dev`: pre-commit hook and API documentation (#21, #41)
- **Pre-commit hook (#21).** `scripts/hooks/pre-commit` (enable with
  `git config core.hooksPath scripts/hooks`) checks only staged files with CI's own commands:
  `ruff format --check` and `ruff check` on `packages/` and `tests/`, ESLint on web files, and
  gitleaks when installed. Checks run in parallel; measured on Windows about 0.3 s for a Python
  change and 1.3 s with web files. It never runs mypy or tests and never edits a file. ruff is
  pinned (`ruff==0.17.3`) in the dev extra so the hook and CI cannot disagree; a test fails if the
  optional `.pre-commit-config.yaml` drifts from that pin, and mypy moved to its manual stage.
  Setup in `DEVELOPMENT.md`, section 9.
- **API documentation (#41).** A consumer guide, `docs/api/README.md`: sign-in and CSRF, jobs and
  polling, reading and comparing runs, exports, limits, simulated vs observed data, and the
  refusal-vs-error distinction explained, with every error code in one table. Its 15 worked examples
  (a completed run, refusals, a validation error, a 429 among them) are produced by calling the API,
  and a test fails when they go stale. Every operation, parameter, field and schema in the OpenAPI
  schema is now described (a test enforces it), and the CSV and PDF exports are in the schema.

### Added on `bhumi-dev`: production hardening and monitoring (#50, #51)
- **Sign-in on every write (#51).** The API refuses to start with `APP_ENV=production` and
  `AUTH_REQUIRED=false`. `POST /cases` requires sign-in even with auth off, because it writes
  files, and is audited (`case.create`). A sweep proves every non-sign-in write route answers an
  anonymous caller 401.
- **Analysis submission budget (#51).** 20 per user per 10 minutes, shared by `POST /jobs` and
  `/verify` (settings `ANALYSIS_RATE_LIMIT`, `ANALYSIS_RATE_WINDOW_SECONDS`); over it is
  `429 too_many_submissions` with `Retry-After`, audited as a denied `run.start`.
- **Security headers (#51)** on every API response and every web page, with a Content-Security-
  Policy for each. An e2e spec loads every page from a production build and fails on any CSP
  violation.
- **Dependency scans made visible (#51).** Still advisory until after the competition; results go
  to the run summary and annotations, with each npm advisory labelled accepted or NEW.
  `SECURITY.md` section 8 lists every gap as closed or accepted with a reason.
- **Structured logs (#50).** The API now logs JSON like the worker; every line has `run_id`,
  `case_id` and `stage` (null outside an analysis) plus `request_id` on API lines; credentials are
  redacted from every part of every line, and a line that cannot be redacted is withheld.
- **Metrics and alerts (#50).** `prometheus_client` metrics on internal ports 9464 (API) and 9465
  (worker): stage durations, queue depth, run outcomes (for the refusal rate) and cache hits, with
  labels from fixed lists only. Alert rules page on job failure rate and queue backlog; refusal-rate
  shifts and a zero refusal rate are warnings, never pages. Rules are unit-tested with `promtool`
  in CI.

### Added on `bhumi-dev`: report export and structured errors (#38, #39)
- **Report export pipeline (#38).** PDF and CSV exports are verified against their own bundle
  (`verify_grounding`), labelled with their generator (`deterministic` or `genai:<provider>`) in the PDF,
  CSV and an `X-GroundTruth-Report-Generator` header, and guaranteed to carry the provenance section and
  the simulated-data warning. A narrated report that fails verification **refuses the export** with a
  structured error (`narration_not_grounded`, `narration_failed`, `report_not_grounded`); the inline
  `report_markdown` keeps its deterministic fallback. `GET /cases/{id}/export/pdf?narrate=true` is the
  opt-in (`422 narration_not_configured` without a provider). The export policy trusts numbers from
  `verdict.rationale` only, beyond the evidence values: the deterministic report fails the contract's
  check for 7 of 27 cases because the engine's own thresholds are not recognised there (a fix for
  `contracts/grounding`, C1/C6).
- **One error envelope for every router (#39).** Every error response carries `request_id` and a
  top-level `is_refusal`; the existing `detail` shapes are unchanged. Validation errors name their
  fields (`code: validation_error`, `fields`) and no longer echo the submitted input. Absolute paths,
  tracebacks, SQL and secrets are scrubbed from error bodies and from stored error text; an unexpected
  exception returns a JSON 500 with a request id (traceback in the server log only) and carries CORS
  headers. New optional fields on the error models; API types regenerated.

### Fixed on `bhumi-dev`
- **`POST /jobs`, `/verify` and the CLI ignored the case's `min_donors`/`max_donors` (#36).** They
  defaulted to `min_donors=10`, so Kariba ran with a best placebo p-value of 0.091 instead of 0.032.
  They now use the case's own values. A request may raise the floor but not lower it
  (`min_donors_below_case_floor`).
- **Case management (#36).** `status: analysed` is refused on every path (`CaseDefinition` itself;
  it needs a run reviewed by both owners, C7 and #4), unknown statuses are refused, and `POST /cases`
  validates before writing and answers structured 422s instead of a bare 500. A rejected case no longer
  leaves an unloadable YAML behind that broke the whole case list. Case ids must be kebab-case.
  API types regenerated (`min_donors` is optional; `CreateCaseRequest.status`).

### Added on `bhumi-dev` before the 2.0 merge
- **Earth Engine observation service (#22):** `platform/datasets/observation.py`, with
  sign-in, retries, rate limiting and caching shared through `platform/datasets/session.py`.
  Landsat 7 2001-2022 (agreed with Viraj, C3), pinned to a 2026-11-01 snapshot. Tested
  offline; network tests are opt-in (`--run-network`). Never run on real data.
- **Covariate services and ADR-011 unit construction (#23):** `platform/datasets/covariates.py`
  and `platform/units/provider.py`, behind the required settings in
  `cases/run_parameters/kariba-redd.yaml` (decisions V1-V9 agreed with Viraj, C4). No real unit
  set has been generated; the generation script refuses until every setting is decided.
- **Docker fixes (#44):** one shared backend image, a one-shot `migrate` service that api and
  worker wait for, backend image without the web source, and `.dockerignore` rules that keep
  environment files and keys out of every image.

### Visual Preview of 2.0 Dashboards
| Auditor Verification Dashboard | Project Overview & Dimensions |
| :---: | :---: |
| ![Auditor Dashboard](docs/product/screens/auditor-dashboard.png) | ![Kariba Overview](docs/product/screens/kariba-overview.png) |

---

## [1.0.0] — 2026-11-07: Master Causal Verification Engine

### Added
- **Pure NumPy FISTA Synthetic Control Solver:**
  - Hand-written proximal gradient FISTA optimizer solving simplex-constrained SCM without CVXPY or SciPy dependencies.
- **Permutation Placebo Inference:**
  - In-space placebos iterating over donor pools and in-time placebos shifting treatment dates into the pre-period.
  - Phipson-Smyth add-one correction floor ($p = 1 / (J + 1)$).
- **Difference-in-Differences Cross-Check:**
  - Automated pre-trend parallelism diagnostic and standardized mean difference (SMD) covariate balance metrics.
- **AST Contract Boundary Guard:**
  - `tests/test_contract_boundary.py` parsing repository ASTs to ensure zero I/O in the engine and zero methodology in the platform.
- **Gemini Narration & Grounding Verifier:**
  - Downstream narrative generation with regex verification restricting numbers to within $\pm 2\%$ of the `EvidenceBundle` and blocking defamatory legal language.

---

## [0.10.0] — 2026-10-25: Core Platform Foundation

### Added
- Monorepo structure with `packages/groundtruth` (`contracts`, `engine`, `platform`).
- Initial case definitions: `kariba-redd`, `southern-cardamom-redd`, and `mikoko-pamoja`.
- Fast latent factor synthetic benchmark simulator with injected treatment curves.
- FastAPI REST service and OpenAPI schema generation.
- Basic Next.js frontend with dynamic SVG trajectory charts.

---

> GroundTruth 2.0 Changelog · *PCCOE International Grand Challenge 2026*
