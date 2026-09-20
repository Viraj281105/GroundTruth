# Architecture

The single decision that shapes everything else, then the map.

---

## 1. The load-bearing decision

GroundTruth is split into three parts by a formal, versioned contract:

```
┌─────────────────── DETERMINISTIC ENGINE ────────────────────┐
│  ingestion → observation → features → matching → causal     │
│           → uncertainty → evidence assembly                 │
│                                                             │
│  No language model. No I/O. Every value carries provenance. │
└──────────────────────────┬──────────────────────────────────┘
                           │
                  EvidenceBundle (immutable, versioned)
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  REPORTING                                                  │
│  deterministic renderer ──or── GenAI → grounding check      │
│                                    fails → deterministic    │
└─────────────────────────────────────────────────────────────┘
```

The evidence bundle is the currency. A language model handed raw satellite data
and asked "was this project additional?" is guessing. A model handed a verified
bundle and asked "explain these numbers" is doing something it is reliable at.

Everything below follows from wanting that boundary to be real rather than
aspirational.

## 2. Three packages, one direction

```
apps/web  ──generated types──►  apps/api  ──►  groundtruth.platform
                                                      │
                                              contracts (shared)
                                                      │
                                              groundtruth.engine
```

| Package | Owner | Rule |
| --- | --- | --- |
| `contracts/` | shared | Imports neither side. Versioned. Changes need both owners. |
| `engine/` | Viraj | Pure computation. No files, no sockets, no credentials, no database. |
| `platform/` | Bhumi | May import exactly four names from the engine. |

`tests/test_contract_boundary.py` parses the AST of every module and fails the
build on a violation. The 60/40 ownership split is only meaningful because the
code actually has a seam where the two workstreams meet.

Full specification: [`docs/architecture/contract.md`](docs/architecture/contract.md).

## 3. The contract in two directions

**Forward — the main boundary.**

```python
run_analysis(request: AnalysisRequest, data: DataAccess) -> AnalysisResult
```

`AnalysisRequest` is self-contained: the engine reads no YAML, no database, no
environment. `AnalysisResult` is returned for every outcome including refusal,
so a job runner never has to catch and stringify a domain failure.

**Backward — the data ports.**

```python
ObservationAccess.series(spec) -> TimeSeries
CovariateAccess.covariates(unit, keys) -> dict[str, float]
DonorCandidateAccess.candidates(request) -> list[UnitRef]
```

The engine declares what it needs; the platform decides where it comes from.
This is the seam between **methodology** and **plumbing**:

| Engine decides | Platform decides |
| --- | --- |
| Which index, mask, composite | Which provider, which credentials |
| Which covariates, how derived | Retries, rate limits, caching |
| What counts as sufficient coverage | Dataset version pinning |
| What to do when coverage fails | Job orchestration, cancellation |

## 4. Repository map

```
apps/
  api/            thin ASGI entrypoint                        Bhumi  [implemented]
  worker/         background job runner                       Bhumi  [not built]
  web/            Next.js frontend                            Viraj  [contract types only]

packages/groundtruth/src/groundtruth/
  contracts/      request · result · evidence · provenance    shared [implemented]
                  units · errors · grounding · ports · version
  engine/
    observation/  indices · masking · zonal                   Viraj  [implemented]
    features/     covariate engineering                       Viraj  [not built]
    matching/     donor pool, eligibility, balance            Viraj  [implemented]
    causal/       synthetic control · DiD                     Viraj  [implemented]
    uncertainty/  placebo · leave-one-out · spec curve        Viraj  [implemented]
    assembler.py  evidence assembly · verdict gates           Viraj  [implemented]
    run.py        run_analysis                                Viraj  [implemented]
  platform/
    api/          FastAPI, schemas                            Bhumi  [implemented]
    cases/        case registry, request translation          Bhumi  [implemented]
    datasets/     registry, pinning, DataAccess impls         Bhumi  [synthetic only]
    units/        ADR-011 unit construction and ladder        Bhumi  [rules only]
    jobs/         analysis lifecycle                          Bhumi  [not built]
    store/        evidence persistence                        Bhumi  [not built]
    storage/      artifacts and exports                       Bhumi  [not built]
    reports/      rendering · GenAI narration                 Bhumi  [renderer only]
    config.py     settings                                    Bhumi  [implemented]

cases/            project definitions as YAML data
data/             raw · interim · processed · external (contents gitignored)
docs/             architecture · science · data · product · engineering · decisions
experiments/      pre-registered validation harnesses
infrastructure/   docker · deploy                                    [not built]
tests/            suite including boundary enforcement
```

## 5. Extension points

Designed now, built later. Each has a documented interface so adding a
capability does not require restructuring.

| Extension point | Interface today | Adds later |
| --- | --- | --- |
| **Earth observation** | `ObservationAccess` port | Sentinel-1 SAR, MODIS, GEDI, Hansen, fire, hydrology — each a provider behind the same port |
| **Covariates** | `CovariateAccess` port | CHIRPS, SRTM, WorldPop, OSM, WDPA; any raster reducible to a per-unit scalar |
| **Estimators** | `ModelRef` + `EstimationSpec.cross_checks` | Event studies, causal forests, matched controls, HTE — registered by `model_id`, invoked by spec |
| **Robustness** | `RobustnessSpec` flags | Spillover analysis, sensitivity bounds, multi-method agreement |
| **Evidence** | `Evidence.id` namespaces + `qualifiers` | New metric families without a schema change (minor bump) |
| **Reporting** | `Narrator` protocol | Any LLM provider; grounding is enforced downstream of all of them |
| **Datasets** | `DatasetRef` | Version pinning already carried through to results |
| **Monitoring** | `spec_hash` + job lifecycle | Scheduled re-analysis is "re-run the same spec and diff the bundles" |

The reason these are cheap later is that none of them requires changing the
shape of `AnalysisRequest` or `AnalysisResult`. That was the point of spending
effort on the contract early.

Detail: [`docs/architecture/earth-observation.md`](docs/architecture/earth-observation.md),
[`docs/architecture/causal.md`](docs/architecture/causal.md),
[`docs/architecture/monitoring.md`](docs/architecture/monitoring.md).

## 6. Data flow, end to end

```
 1. case YAML                      platform/cases      [implemented]
 2. → AnalysisRequest              case.to_request()   [implemented]
       pins DatasetRefs, drops known_reference
 3. → job queued                   platform/jobs       [NOT BUILT — runs inline]
 4. → DataAccess resolved          platform/datasets   [synthetic only]
 5. → run_analysis                 engine/run.py       [implemented]
       observe → match → estimate → test → assemble
 6. → AnalysisResult
 7. → persisted                    platform/store      [NOT BUILT — in memory]
 8. → report generated             platform/reports    [renderer only]
       grounding check → publish or fall back
 9. → served                       platform/api        [implemented]
10. → rendered                     apps/web            [NOT BUILT]
```

Steps 3, 7 and 10 are the platform work that turns this from a computational
module into a product. Step 4 with real providers is what turns it from a
demonstration into a result.

## 7. Error and status model

Two enums, because the job and the science succeed or fail independently.

```
AnalysisStatus  queued → running → succeeded | failed | cancelled    (platform)
EngineStatus    completed | refused | error                          (engine)
```

A job can be `succeeded` with engine status `refused`. That is the normal,
correct outcome for a project the data cannot support and must not be surfaced
as a failure.

`ErrorCode.is_refusal` separates *the system correctly declining to produce a
fragile number* from *something broke*. The UI styles them differently. A test
asserts every code has an HTTP mapping so a new one cannot silently become 500.

## 8. Technology choices and why

| Choice | Reason |
| --- | --- |
| Python 3.11+ | `StrEnum`, better typing; floor set by what the science libraries need |
| Pydantic v2 | Validation at the boundary, JSON round-trip, OpenAPI generation for free |
| numpy only in the engine core | The synthetic-control solver is hand-written FISTA. No SciPy or CVXPY means the analytical pipeline and CI run anywhere, with no system libraries. Heavy geospatial deps sit behind the `geo` extra. |
| FastAPI | OpenAPI schema is the frontend contract; async when the job layer lands |
| Next.js + TypeScript | Types generated from OpenAPI; the UI never hand-writes a backend shape |
| YAML for cases | Adding a project is a PR against one file, reviewable by a non-programmer |
| Monorepo, one Python distribution | Boundaries enforced by module structure and an AST test rather than by packaging ceremony. See ADR-001. |

## 9. What is deliberately simple

Over-engineering the MVP because the long-term vision is ambitious would be a
mistake. These stay simple until there is a reason:

| Deliberately simple | Stays that way until |
| --- | --- |
| One Python distribution, not five | The engine needs an independent release cadence or an external consumer |
| No database | There is more than one user, or results must survive a restart |
| Synchronous analysis in the API | Real EO calls make a request exceed ~10s |
| In-process job state | Jobs must survive a deploy |
| Environment-variable config only | There is more than one environment |
| No auth | The service is exposed beyond a demo |
| No caching layer | `spec_hash` lookups actually cost something |

Each of these is a *small* change later precisely because the contract already
carries what it would need — `spec_hash` for caching, `AnalysisStatus` for job
state, `DatasetRef` for pinning.

## 10. Known architectural risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Sensor transitions (Landsat↔Sentinel) mimic land-cover change | A spurious headline finding | Cross-calibration with the transform in provenance; transition placed in the pre-period; sensitivity check in the specification curve |
| Donor pool determines the answer | A defensible-looking but wrong estimate | Pool, exclusions and balance are evidence, not implementation detail; leave-one-out sign stability gates the verdict |
| Index→carbon gap unclosed | Cannot compare to a tCO2e claim | Verdict returns `INCONCLUSIVE` rather than manufacturing a comparison. Biomass layer is scoped and deferred, not approximated. |
| GenAI narration passes numeric grounding while misrepresenting a conclusion | A softened "inconclusive" reads as a finding | Caveat-retention check; `inconclusive fidelity` is an explicit metric in the evaluation plan |
| Contract churn blocks both workstreams | Team throughput collapses | Versioned with additive-minor semantics; engine may ship ahead of platform |
| Engine runtime grows with registry scale | Batch screening infeasible | `spec_hash` caching and a separate worker process are already in the design |

## 11. Reading order

| Document | For |
| --- | --- |
| [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) | Why this exists, who it is for, what it must never claim |
| [`AGENTS.md`](AGENTS.md) | Working in the codebase — rules, conventions, where code goes |
| [`docs/architecture/contract.md`](docs/architecture/contract.md) | The boundary, in full |
| [`docs/science/causal-inference.md`](docs/science/causal-inference.md) | The estimator and why NDVI is not carbon |
| [`docs/decisions/`](docs/decisions/) | Why the architecture is the way it is |
| [`OWNERSHIP.md`](OWNERSHIP.md) | Who owns what, and the definition of done |
| [`ROADMAP.md`](ROADMAP.md) | NOW → MVP → Stage 2 → Stage 3 → long term |
