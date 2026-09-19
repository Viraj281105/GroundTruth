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
| **Real Earth-observation reduction** | **Planned — MVP** |
| **Cross-sensor calibration** | **Planned — MVP** |
| **Covariate engineering from real products** | **Planned — MVP** |
| **Cloud-starved period handling downstream** | **Planned** |
| **Specification curve wired into a run** | **Planned** |
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
| **Earth Engine client service** | **Planned — MVP** |
| **Covariate dataset services** | **Planned — MVP** |
| **Boundary acquisition and storage** | **Planned — MVP** |
| **Database schema and migrations** | **Planned — MVP** |
| **Evidence and provenance persistence** | **Planned — MVP** |
| **Analysis job lifecycle** | **Planned — MVP** |
| **Background worker process** | **Planned — MVP** |
| **Frontend/backend integration** | **Planned — MVP** |
| **Result listing and comparison APIs** | **Planned — Stage 2** |
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
| API contract TypeScript types | Implemented |
| UI rule helpers (banner, verdict tone, formatting) | Implemented |
| **Design system and app shell** | **Planned — MVP** |
| **Counterfactual chart** | **Planned — MVP** |
| **Placebo distribution plot** | **Planned — MVP** |
| **Evidence explorer with provenance drill-down** | **Planned — MVP** |
| **Case browser and project pages** | **Planned — MVP** |
| **Interactive map** | **Planned — MVP** |
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

## Deliberately not building

| | Why |
| --- | --- |
| Credit issuance, retirement or pricing | Different regulatory category |
| Automated de-listing or enforcement | No project should lose status on a screening signal |
| A replacement for field verification | Ground plots measure pools no satellite sees |
| A fraud-detection product | Satellite data cannot establish intent |
| Our own imagery pipeline | Earth Engine and the open archives are better |
| A general-purpose GIS | We are a verification system, not a geospatial platform |
