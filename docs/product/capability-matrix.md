# Capability matrix

The single source of truth for what exists. Keep it current — if a capability
moves, update this table in the same change.

| | |
| --- | --- |
| **Implemented** | Works, tested, running in CI |
| **Planned** | Designed, has an issue, not built |
| **Future** | An extension point exists; no commitment, no timeline |

> **No analysis of a real project has been run.** Everything the pipeline
> currently produces comes from a deterministic simulated fixture, labelled as
> such in its provenance, warnings, caveats, API response and CLI banner.

---

## Contract and foundations

| Capability | Status | Owner |
| --- | --- | --- |
| `AnalysisRequest` / `AnalysisResult` contract | Implemented | shared |
| Evidence bundle, `Evidence`, qualifiers | Implemented | shared |
| Mandatory provenance with derivation graph | Implemented | shared |
| Unit vocabulary with index→carbon guard | Implemented | shared |
| Typed error codes, refusal vs malfunction | Implemented | shared |
| Contract versioning and compatibility | Implemented | shared |
| `DataAccess` ports | Implemented | shared |
| Boundary enforcement (AST import tests) | Implemented | shared |
| `spec_hash` reproducibility key | Implemented | shared |
| Grounding rules and verifier | Implemented | shared |
| Per-item spatial and temporal scope | Future | shared |
| Evidence signing | Future | Bhumi |

## Analytical engine — Viraj

| Capability | Status |
| --- | --- |
| NDVI, EVI, NBR, SAVI band math | Implemented |
| SCL cloud masking, median compositing, coverage audit | Implemented |
| Zonal statistics, edge-buffer and leakage-belt caveats | Implemented |
| Donor matching with recorded exclusions | Implemented |
| Common-support caliper, leakage-belt exclusion, coverage rule | Implemented |
| Covariate balance (standardised mean differences) | Implemented |
| Synthetic control, simplex-constrained FISTA solver | Implemented |
| Weight identification reporting | Implemented |
| Difference-in-differences with pre-trend diagnostic | Implemented |
| In-space placebo, add-one p-value correction | Implemented |
| In-time placebo | Implemented |
| Leave-one-out sensitivity, sign stability | Implemented |
| Permutation intervals, specification-curve type | Implemented |
| Evidence assembly and verdict gate chain | Implemented |
| Effect recovery validated on synthetic panels | Implemented |
| **Real Earth-observation reduction** | **Engine methodology specified** (`engine/observation/reduction.py`, published via `describe_engine()`). The Earth Engine client that executes it is **Implemented** (#22): tested offline, network test opt-in, no reviewed real series yet |
| **Cross-sensor calibration** | **Planned — MVP** |
| **Covariate engineering from real products** | **Planned — MVP** |
| **Cloud-starved period handling downstream** | **Planned** |
| **Specification curve wired into a run** | **Implemented**: ridge, pre-period length, treatment date and donor cap. Indicator, caliper and covariate weighting stay offline (`experiments/specification_curve`) |
| **Tidal-window filtering (mangrove)** | **Planned** |
| **Biomass / carbon conversion** | **Planned — Stage 2** |
| Cluster-robust DiD inference | Planned |
| Matched controls, event study, causal forests | Future |
| Spillover analysis, sensitivity bounds | Future |
| Multi-method agreement reporting | Future |

## Platform — Bhumi

| Capability | Status |
| --- | --- |
| Case registry, YAML loading and validation | Implemented |
| Case → `AnalysisRequest` translation | Implemented |
| FastAPI: health, case list, case detail, verify | Implemented |
| Honest capability reporting on `/health` | Implemented |
| Error-code to HTTP mapping, total by test | Implemented |
| Environment configuration, secret handling | Implemented |
| Synthetic dataset provider and `DataAccess` bundle | Implemented |
| Deterministic report renderer | Implemented |
| Grounding enforcement with safe fallback | Implemented |
| CLI (`cases`, `show`, `verify`, `doctor`) | Implemented |
| **Earth Engine client service** | **Implemented** (#22) — auth, retries, rate limiting, cache, snapshot pinning; Landsat 7 2001–2022 (agreed, C3). Observed analysis runs still `501` |
| **Covariate dataset services** | **Implemented** (#23), tested offline; network tests opt-in. Never run on real data. Blocked on the settings in `cases/run_parameters/kariba-redd.yaml` |
| **ADR-011 unit construction and manifest** | **Implemented** (#23), tested offline. No real unit set has been generated |
| **Boundary acquisition and storage** | **Planned — MVP** |
| Database schema and migrations (SQLAlchemy 2.0 + Alembic, `db` extra) | Implemented |
| Evidence and provenance persistence (`EvidenceStore`; not yet called by the API) | Implemented |
| Analysis job lifecycle (`JobQueue`) | Implemented |
| Background worker process (`apps/worker`; simulated data only) | Implemented |
| Job submit, status/progress and cancel APIs (`POST /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`; polling, simulated data, **no authentication**) | Implemented |
| Frontend/backend integration: the case page runs through `POST /jobs`, polls observed stages, cancels, resumes from `?run=`, and renders the stored run; `CORS_ALLOWED_ORIGINS`; error code and remediation on every error state (#40; simulated data, **no authentication**) | Implemented |
| Result listing, retrieval and comparison APIs (`GET /runs`, `/runs/{id}`, `/runs/compare`; read-only, simulated data) | Implemented |
| **GenAI narration providers** | **Planned — Stage 2** |
| Report export with provenance | Planned — Stage 2 |
| Authentication, rate limiting, audit log | Planned — Stage 2 |
| Deployment, containers, CI/CD | Planned — Stage 2 |
| Monitoring and structured logging | Planned — Stage 2 |
| `spec_hash` result caching | Planned — Stage 2 |
| Registry ingestion automation | Future — Stage 3 |
| Batch screening and prioritisation | Future — Stage 3 |
| Scheduled re-analysis, alerts | Future |

## Frontend — Viraj

| Capability | Status |
| --- | --- |
| API contract TypeScript types (generated from OpenAPI, checked in CI) and typed client | Implemented |
| UI rule helpers (banner, verdict tone, formatting) | Implemented |
| **Design system and app shell** | **Planned — MVP** |
| **Counterfactual chart** | **Planned — MVP** |
| **Placebo distribution plot** | **Planned — MVP** |
| **Evidence explorer with provenance drill-down** | **Planned — MVP** |
| **Case browser and project pages** | **Planned — MVP** |
| **Interactive map** | **Planned — MVP**, blocked on unit geometry: the engine matches in covariate space and no unit has coordinates yet, so the hand-drawn map was removed rather than shown with invented locations |
| Evidence diagnostics panels (fit gate, convex hull, period coverage, placebo floor and α, in-time placebo, leave-one-out, specification curve, DiD cluster-robust inference) | Implemented; rendered from the bundle, exercised only against the engine-generated simulated fixture |
| Refusal states with engine code, stage and remediation | Implemented; the per-unit alignment table is fixture-only until the API returns `AnalysisError.detail` |
| Donor pool, contributing weights and exclusions grouped by rule | Implemented; the per-candidate exclusion list is fixture-only until the API returns the candidate list |
| Project timeline | Planned — Stage 2 |
| Report view | Planned — Stage 2 |
| Analysis comparison views | Planned — Stage 2 |
| Demo polish | Planned |

## Validation

| Capability | Status |
| --- | --- |
| Estimator recovery on synthetic panels | Implemented |
| Grounding adversarial suite | Implemented |
| Reproducibility assertion (same spec ⇒ same numbers) | Implemented |
| Pre-registered Kariba benchmark plan | Implemented (plan only) |
| Pre-registered GenAI evaluation plan | Implemented (plan only) |
| Pre-registered specification-curve plan | Implemented (plan only) |
| **Kariba benchmark run** | **Not run — MVP** |
| **Control-case behaviour on real data** | **Not run** |
| **Nugen vs baseline grounding evaluation** | **Not run — Stage 2** |

---

## Extensions added in the platform-expansion pass

"Implemented" here means written, unit-tested offline and in CI. Anything that needs
an external service is marked **Not verified live**: no analysis of a real project
has been run, and none of these paths has been exercised against real data.

| Capability | Status | Notes |
| --- | --- | --- |
| STAC scene search and odc-stac loader (`data_access/stac.py`) | Implemented, **not verified live** | Tested against a fake client only; not wired into the engine |
| DuckDB/Parquet store, Zarr I/O (`data_access/`) | Implemented | Needs the `eo` extra; tests skip without it |
| Dagster asset definitions (`data_access/pipelines.py`) | Implemented, **not verified live** | Needs the `pipelines` extra; test skipped without it |
| Augmented synthetic control, conformal intervals, E-value / sensitivity bounds | Implemented, **not wired into the verdict** | Available as library functions; the assembler's gate chain is unchanged. `full_sample` conformal is not jackknife+ |
| pysyncon / DoWhy cross-check adapters | Implemented, **not verified live** | Optional deps not exercised in CI |
| Parallel placebo executor (serial, process pool, Dask, Ray) | Implemented (serial, process); Dask/Ray **not verified live** | Not yet used by the placebo suite |
| Embedding-based donor similarity | Implemented | Needs user-supplied vectors; no embedding model is bundled |
| Redis (arq) job queue, Temporal workflow | Implemented, **not verified live** | Off unless `REDIS_URL` is set; transitions are not atomic |
| SSE job progress, boundary GeoJSON, PostGIS vector tiles | Implemented | Tiles need a `case_boundaries` PostGIS table that no migration creates yet |
| Anthropic narrator provider | Implemented, **not verified live** | Mocked HTTP only; output still passes the grounding verifier (R4) |
| Claim extraction, retrieval and comparison (`claims/`) | Implemented | Heuristic text extraction; served by `POST /claims/analyze` and the `/claims` page. Only project area is compared against a case record today; other claim kinds show no estimate |
| Evidence-bundle manifests, cosign signing, DVC config | Implemented, signing **not verified live** | Needs the cosign binary |
| OpenTelemetry, Grafana/Tempo/Prometheus stack, Helm chart | Implemented, **not verified live** | Compose overlay and chart never started; no job-duration metric yet |
| Docker images and compose stack | Implemented | Built and run locally |

## UI rework (apps/web)

Light/dark design system, multi-page flow and lenses. All numbers still come from the simulated
fixture or the API; nothing is computed in the browser (R6). See `docs/ui-data-gaps.md`.

| Capability | Status | Notes |
| --- | --- | --- |
| Design tokens, light and dark themes (no flash), `system` default | Implemented | Three-tier tokens with a `--gt-*` compatibility layer |
| Story / Explorer / Auditor detail levels, shared glossary | Implemented | Persisted locally; `?lens=` override |
| Routes: home, cases, case overview / evidence / robustness / method / report / run, compare, claims, method, status | Implemented | Results and charts need `NEXT_PUBLIC_DEMO_MODE=true`: the API serves no series, placebo or donor geometry |
| Run Theatre (stepper, live stage progress) | Implemented, **not verified live** | SSE with polling fallback; tested against fakes only |
| Counterfactual Playground | Partly implemented | Scrubs only data the API returns; true re-fitting needs API support |
| Donor map (MapLibre) | Implemented | Boundary only; donor shading needs donor geometry the data does not have |
| Command palette, shortcuts, tour, recently viewed, web manifest | Implemented | Hindi and Marathi cover navigation and core labels only |
| Landing page (problem, how it works, features, AI flow, FAQ) with scroll reveals | Implemented | Illustrative SVGs are labelled; the Verra/Kariba figure is attributed to Verra |
| Chart kit (token-based SVG) and charts on cases, overview, evidence, robustness, compare, status, claims, method, run | Implemented | Only values the API or fixtures return are drawn; Kariba is the only case with fixture series |
| Floating navigation; Method and Status moved into the account menu | Implemented | Status link shown to developers and admins |
| Accounts: email + password, cookie sessions, roles `user` / `dev` / `admin`, admin user management | Implemented | `AUTH_REQUIRED` is on in `docker-compose.yml` and off by default in code. No password reset, no per-user run ownership; see `docs/security/auth.md` |
| Sign-in required to run analyses and use the claims workbench; Status limited to developers | Implemented | The Status gate is client-side only; `/health` and `/runs` stay public API endpoints |
| Offline service worker, Pyodide in-browser reproduction, shareable evidence cards | **Not built** | Cut from the first pass |
| Playwright e2e and visual specs | Written, **not run** | Needs a browser download; baselines are not committed |

---

## Deliberately not building

| | Why |
| --- | --- |
| Credit issuance, retirement or pricing | Different regulatory category |
| Automated de-listing or enforcement | No project should lose status on a screening signal |
| A replacement for field verification | Ground plots measure pools no satellite sees |
| A fraud-detection product | Satellite data cannot establish intent |
| Our own imagery pipeline | Earth Engine and the open archives are better |
| A general-purpose GIS | We are a verification system, not a geospatial platform |
