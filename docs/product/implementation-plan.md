# Implementation plan

Phased task breakdown with owners, dependencies, acceptance criteria and
parallelism. Workload targets ~60% Bhumi / ~40% Viraj by story points.

Points: 1 = hours, 2 = a day, 3 = a few days, 5 = a week, 8 = more than a week.

| Legend | |
| --- | --- |
| **V** | Viraj |
| **B** | Bhumi |
| ‖ | Can run in parallel with its phase peers |
| → | Blocked by the listed dependency |

---

## Phase 1 — Foundation

| # | Task | Owner | Pts | Deliverable | Depends | ‖ | Acceptance |
| --- | --- | :---: | ---: | --- | --- | :---: | --- |
| F1 | Monorepo restructure | shared | 3 | `apps/` + `packages/` + docs tree | — | — | ✅ Done. Tests green after move. |
| F2 | Contract schemas | shared | 5 | Request, result, evidence, provenance, ports, versioning | — | — | ✅ Done. Round-trips JSON; invariants tested. |
| F3 | Boundary enforcement | shared | 2 | AST import tests | F2 | — | ✅ Done. Fails on any cross-boundary import. |
| F4 | Documentation system | shared | 5 | Root docs, ADRs, architecture, science, data, product | — | — | ✅ Done. A new dev can orient without asking. |
| F5 | Database schema + migrations | **B** | 3 | `cases`, `analysis_runs`, `evidence_bundles`, `datasets`, `jobs` | F2 | ‖ | Migrations apply and roll back; bundle round-trips through the store. |
| F6 | Evidence store | **B** | 3 | Persist and retrieve bundles by `run_id` and `spec_hash` | F5 | → | A stored bundle reloads identically, including after a minor contract bump. |
| F7 | UI skeleton + design system | **V** | 5 | Next.js app, routing, tokens, app shell, simulated banner | F2 | ‖ | Renders at phone/tablet/desktop; banner not dismissible. |
| F8 | Generated TS types + API client | **B** | 2 | OpenAPI → TypeScript, typed client | F2 | ‖ | Schema change without regeneration fails the build. |
| F9 | Engine `features/` module | **V** | 2 | Covariate engineering structure and transforms | F2 | ‖ | Unit-tested transforms; no I/O. |
| F10 | Frontend test + lint infra | **V** | 2 | Vitest, ESLint, Prettier, component tests | F7 | → | Runs in CI. |
| F11 | CI extension for frontend | **B** | 2 | Lint, typecheck, test, build job | F10 | → | Green on push and PR. |
| F12 | Pre-commit hooks | **B** | 1 | ruff, mypy, prettier on staged files | — | ‖ | Blocks a commit that CI would reject. |

**Phase 1 points: V 9 · B 11** (plus 15 shared, already complete)

---

## Phase 2 — Core pipeline

The MVP-critical phase. Note how each EO/covariate concern splits into a
methodology task (V) and a service task (B) meeting at a port.

| # | Task | Owner | Pts | Deliverable | Depends | ‖ | Acceptance |
| --- | --- | :---: | ---: | --- | --- | :---: | --- |
| P1 | S2/Landsat reduction methodology | **V** | 5 | Masking, compositing, index math, reducer spec | F2 | ‖ | Reduction validated against known reflectance targets; coverage counts populated. |
| P2 | Earth Engine client service | **B** | 5 | Auth, session, retries, rate limits, caching behind `ObservationAccess` | P1, C2 | → | Real NDVI series for Kariba; raises rather than falling back. |
| P3 | Cross-sensor calibration | **V** | 3 | Transition detection, overlap calibration, transform in provenance | P1 | → | A synthetic injected calibration step is corrected within tolerance. |
| P4 | Covariate methodology | **V** | 3 | Which covariates, derivations, transformations | F9 | ‖ | Documented rationale per covariate; unit-tested transforms. |
| P5 | Covariate dataset services | **B** | 5 | CHIRPS, SRTM, slope, OSM roads, WorldPop behind `CovariateAccess` | P4, C4 | → | Real covariates for a Kariba donor pool; each pinned to a `DatasetRef`. |
| P6 | Boundary acquisition + storage | **B** | 3 | Registry geometry for 3 cases, validated, stored | F5 | ‖ | Area cross-check within 10% of registered hectares, or the discrepancy recorded. |
| P7 | Donor-pool methodology | **V** | 5 | Ecoregion constraint, leakage belt, WDPA exclusion, balance targets | P4 | → | Kariba pool with worst SMD ≤ 0.25; every exclusion has a reason. |
| P8 | Cloud-starved period handling | **V** | 3 | Masking report threaded to the assembler; refuse or down-weight | P1 | → | Sparse periods are evidence; a too-sparse pre-period refuses. |
| P9 | Specification curve in-run | **V** | 3 | Multi-spec execution wired into `RobustnessSpec` | F2 | ‖ | Curve emitted as evidence; sign agreement reported. |
| P10 | Analysis job lifecycle | **B** | 5 | Queue, claim, lease, retry, cancel, status transitions | F5 | → | Jobs survive a restart; a refusal is a SUCCEEDED job. |
| P11 | Worker process | **B** | 3 | `apps/worker` consuming jobs, persisting results | P10, F6 | → | Kariba runs to completion in the worker; cancellation works. |
| P12 | Dataset registry + pinning | **B** | 3 | Version resolution, cache keyed by ref + extent | F5 | ‖ | A re-run uses the same pinned version. |
| P13 | Storage service | **B** | 2 | Artifacts, exports, generated reports | F5 | ‖ | Round-trips a report and a raster export. |

**Phase 2 points: V 22 · B 26**

---

## Phase 3 — Product

| # | Task | Owner | Pts | Deliverable | Depends | ‖ | Acceptance |
| --- | --- | :---: | ---: | --- | --- | :---: | --- |
| R1 | Counterfactual chart | **V** | 5 | Observed vs synthetic, gap shaded, treatment marked | F7, C5 | ‖ | Legible to a non-specialist; interval `kind` shown. |
| R2 | Placebo distribution plot | **V** | 3 | Histogram with the project highlighted | F7 | ‖ | p-value and its floor stated on the chart. |
| R3 | Interactive map | **V** | 5 | Boundary, donor pool, leakage belt, exclusions | F7, P6 | → | Exclusion reason visible per unit. |
| R4 | Evidence explorer | **V** | 5 | Every value with unit, interval, provenance drill-down | F7, F8 | ‖ | Provenance reachable in two clicks. |
| R5 | Case browser + project pages | **V** | 3 | Listing, detail, run history | F8 | ‖ | Nothing reads as `analysed` when it is not. |
| R6 | Project timeline | **V** | 3 | Crediting period, treatment, transitions, fire years | R5 | → | Sensor transitions visible where they affect the series. |
| R7 | Analysis result APIs | **B** | 3 | List, get, filter, paginate, compare | F6 | → | Pagination stable under concurrent writes. |
| R8 | Case management API | **B** | 3 | CRUD replacing YAML-only definition | F5 | ‖ | A case created via API produces a valid request. |
| R9 | Job status API | **B** | 2 | Poll and stream progress | P10 | → | UI can show progress and cancel. |
| R10 | Report pipeline | **B** | 3 | Evidence → report, export with provenance | F6, C6 | → | Exported report passes its own grounding check. |
| R11 | GenAI narration providers | **B** | 5 | Nugen + baseline clients, retries, safe degradation | R10 | → | Hallucinating output falls back; evaluation harness runs. |
| R12 | Backend validation + errors | **B** | 3 | Boundary validation, structured errors everywhere | F8 | ‖ | Every error code mapped; refusals distinguishable. |
| R13 | Frontend/backend integration | **B** | 3 | Wiring, env config, CORS, error surfaces | R1–R6, R7 | → | End-to-end from UI click to rendered evidence. |
| R14 | API documentation | **B** | 2 | OpenAPI descriptions, examples, usage guide | R7 | → | A consumer integrates without asking us. |

**Phase 3 points: V 24 · B 24**

---

## Phase 4 — Validation

| # | Task | Owner | Pts | Deliverable | Depends | ‖ | Acceptance |
| --- | --- | :---: | ---: | --- | --- | :---: | --- |
| V1 | Kariba benchmark run | **V** | 5 | First real result, reviewed | P2, P5, P6, P7 | → | Pre-registered criteria applied; result published whatever it says. |
| V2 | Control cases on real data | **V** | 3 | Cardamom (cloud/saturation), Mikoko (scale) | V1 | → | Mikoko returns INCONCLUSIVE on scale grounds. |
| V3 | Robustness suite on real data | **V** | 3 | Donor sensitivity, spec curve, pre-period length, treatment date | V1 | → | Any sign flip reported as a limitation, not dropped. |
| V4 | Uncertainty validation | **V** | 2 | Interval coverage, placebo calibration | V1 | → | Intervals behave as labelled. |
| V5 | Reproducibility harness | **B** | 3 | Replay stored specs, assert numeric equality | F6, P11 | → | A replay reproduces exactly; a mismatch fails CI. |
| V6 | Grounded-report evaluation | **B** | 3 | Nugen vs baseline on identical bundles | R11 | → | Metrics published both directions, including inconclusive fidelity. |

**Phase 4 points: V 13 · B 6**

---

## Phase 5 — Demo and production

| # | Task | Owner | Pts | Deliverable | Depends | ‖ | Acceptance |
| --- | --- | :---: | ---: | --- | --- | :---: | --- |
| D1 | Containerisation | **B** | 3 | One image, two entrypoints | P11 | → | API and worker run from the same image. |
| D2 | Deployment | **B** | 3 | Hosting, managed database, env config | D1 | → | Deploys from green CI with a documented rollback. |
| D3 | CI/CD pipeline | **B** | 3 | Build, test, deploy on merge | D2 | → | A merge reaches the environment without manual steps. |
| D4 | Performance | **B** | 3 | `spec_hash` caching, query tuning, concurrency | V5 | ‖ | A cached analysis returns without recomputation. |
| D5 | Error handling + resilience | **B** | 3 | Timeouts, circuit breaking, graceful degradation | D2 | → | An upstream outage degrades rather than crashes. |
| D6 | End-to-end tests | **B** | 3 | Full path, including refusal and failure paths | R13 | → | Runs in CI against a deployed environment. |
| D7 | Monitoring + logging | **B** | 3 | Structured logs, metrics, alerts | D2 | → | Run id and stage present on every log line. |
| D8 | Production hardening | **B** | 3 | Auth, rate limits, headers, dependency scanning | D2 | ‖ | `SECURITY.md` gaps closed or explicitly accepted. |
| D9 | Demo workflow + polish | **V** | 5 | Rehearsed flow, visual polish, fallbacks | R13, V1 | → | Runs in 7 minutes; every failure path has a fallback. |
| D10 | Methodology documentation | **V** | 3 | Per-case methodology note generated from evidence | V1 | → | Generated from the bundle, so it cannot drift. |

**Phase 5 points: V 8 · B 24**

---

## Workload totals

| Owner | P1 | P2 | P3 | P4 | P5 | **Total** | **Share** |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Viraj | 9 | 22 | 24 | 13 | 8 | **76** | **40%** |
| Bhumi | 11 | 26 | 24 | 6 | 24 | **91** | **60%** |

Viraj's 76 points split roughly 35 analytical / 41 frontend — the two areas that
decide scientific credibility and whether the demo lands. Bhumi's 91 span
foundation, data services, APIs, reporting, integration and operations: the work
that makes GroundTruth a real deployable application rather than a computational
module.

---

## Coordination points

The only places both owners must be in the room. Everything else proceeds
independently — that is the point of the boundary.

| # | Point | Phase | Why |
| --- | --- | --- | --- |
| C1 | Any `contracts/` change | any | Both sides depend on it; needs a version bump |
| C2 | `DataAccess` port semantics | 2 | Wrong split puts credentials in the engine or methodology in the platform |
| C3 | EO reduction handover | 2 | V owns band math and masking; B owns client and caching |
| C4 | Covariate list and derivation | 2 | V decides which and how; B builds the services |
| C5 | Evidence → UI projection | 3 | The API must return what the UI can render without re-deriving |
| C6 | Report structure | 3 | V specifies content and caveats; B builds the pipeline |
| C7 | Kariba result review | 4 | No case reaches `status: analysed` without both reviewing |
| C8 | Demo rehearsal | 5 | V drives; B must have deployment stable and failure paths understood |

---

## Dependency graph

```
F1 F2 F3 F4  (done)
  │
  ├─► F5 ─┬─► F6 ─┬─────────────────────► R7 ─► R13 ─► D6
  │       │       └─► V5 ─► D4
  │       ├─► P6 ─────────────► R3
  │       ├─► P10 ─► P11 ─► D1 ─► D2 ─┬─► D3
  │       ├─► P12                     ├─► D5
  │       ├─► P13                     ├─► D7
  │       └─► R8                      └─► D8
  │
  ├─► F7 ─┬─► F10 ─► F11
  │       ├─► R1  R2  R4  R5 ─► R6
  │       └────────────────────► R13 ─► D9
  │
  ├─► F8 ─► R12
  │
  ├─► F9 ─► P4 ─┬─► P5 ──┐
  │             └─► P7 ──┤
  │                      ├─► V1 ─┬─► V2
  ├─► P1 ─┬─► P2 ────────┘       ├─► V3
  │       ├─► P3                 ├─► V4
  │       └─► P8                 └─► D10
  │
  ├─► P9
  └─► R10 ─► R11 ─► V6
```

## Suggested parallel order

**Sprint 1 — unblock everything.**
V: P1 (reduction methodology), F7 (UI skeleton).
B: F5 (database), F8 (generated types).
*No dependency between them. C2 happens at the end of this sprint.*

**Sprint 2 — real data.**
V: P3, P4, P8.
B: P2 (EO client), F6 (evidence store), P6 (boundaries).
*C3 and C4 land here.*

**Sprint 3 — first result and first pixels on screen.**
V: P7 (donor methodology), R1 (counterfactual chart).
B: P10, P11 (jobs and worker), P5 (covariate services).

**Sprint 4 — the MVP.**
V: V1 (Kariba run), R2, R4.
B: R7, R12, R13.
*C5 and C7 land here. This is the MVP exit.*

**Sprint 5 — product and production.**
V: R3, R5, R6, D9.
B: R10, R11, D1–D3.
*C6 and C8 land here.*

The pattern that makes this work: **V starts each phase on methodology while B
starts on infrastructure, and they meet at a port.** Neither blocks the other
for more than one sprint, and only at the eight named coordination points.
