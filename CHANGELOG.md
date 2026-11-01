# Changelog

Notable changes to GroundTruth. Format based on
[Keep a Changelog](https://keepachangelog.com/); versioning follows
[semver](https://semver.org/).

Three versions are tracked independently:

| Version | Bumped when |
| --- | --- |
| Package | Any release |
| `CONTRACT_VERSION` | The engine/platform schema changes |
| `ENGINE_VERSION` | **Analytical results could change** |

---

## [Unreleased]

### Added

- **Background worker** (#25). `python -m apps.worker.main` claims jobs, runs
  `run_analysis` (unchanged) and records the outcome; Kariba runs to completion in it
  on SIMULATED DATA. A heartbeat thread keeps the lease alive at lease/3 and stops
  the moment the engine returns. Cancellation is cooperative: a cancel during the
  engine discards its result when it returns. A crash writes nothing (the result is
  one transaction) and the job is retried after its lease expires; a bug fails only
  that job. First Ctrl+C/SIGTERM/Ctrl+Break finishes the current job, a second stops
  at once. Logs are JSON lines carrying `run_id`, `case_id`, `stage`, `worker_id`,
  `attempt` and `data_mode`, including the engine's own lines, with the database
  password masked. Startup refuses a missing `DATABASE_URL` or an unmigrated database
  (`--migrate` is opt-in) and warns when `GIT_SHA` is unset, recording `git_sha` as
  null rather than a placeholder. New `groundtruth submit` and `groundtruth job`
  commands queue a job and show its status. `JobStatus` now carries `data_mode` and
  `is_simulated`. No contract or engine change.
- **Analysis job lifecycle** (#24). `platform/jobs/` adds a database-backed queue with
  no broker: `submit`, `claim` with a stored lease, `heartbeat`, cooperative
  `cancel` honoured between stages, `complete`/`fail` with bounded exponential
  backoff (`DATA_UNAVAILABLE`, `DataUnavailableError` and expired leases only), and
  `process_next` as one worker step. A refusal is a SUCCEEDED job with a refused
  result, never FAILED. Claiming is a single write-first statement (`FOR UPDATE SKIP
  LOCKED` on PostgreSQL) and every status change is conditional, so two workers
  cannot take or finish the same job. A request whose `spec_hash` already has a result
  returns that run without recomputing; an identical request in flight returns that
  job. The engine's `run_id` is replaced by the job's. Migration `0003` adds
  `analysis_runs.request` and `jobs.lease_expires_at`. The store's write path is shared
  via `record_result`, and `by_run_id` now returns `None` for a run with no engine
  result yet. No worker runs the queue yet (#25) and the API does not submit to it
  (#35, #37). No contract or engine change.
- **Evidence and provenance store** (#15). `platform/store/` can now save and
  retrieve an `AnalysisResult`: `save_result`, `by_run_id`, `by_spec_hash` and
  `list_for_case`, behind a small `EvidenceStore` interface that needs no database
  library. A stored result reloads equal to the original, provenance fingerprints
  included; a refusal reloads as a full result with no bundle. A run is written once
  (`DuplicateRunError` otherwise), atomically with its bundle. `by_spec_hash` returns
  the most recent finished run and requires `data_mode` and `engine_version`, so a
  simulated result cannot answer an observed lookup (R7) nor an older engine's
  result the current one's (R8). The contract version is checked on read. Migration
  `0002` adds `analysis_runs.engine_contract_version`. Nothing calls the store yet
  (#24, #35). No contract change.
- **Database schema and migrations** (#14). `platform/store/` defines `cases`,
  `analysis_runs`, `evidence_bundles`, `datasets` and `jobs` (SQLAlchemy 2.0,
  Alembic, new optional `db` extra). A bundle is one JSON document (JSONB on
  PostgreSQL) plus indexed projections for listing by case, verdict and date, and
  is stored with the `contract_version` it was written under. Bundles are
  immutable: a database trigger rejects `UPDATE`, so a re-run is a new `run_id`.
  `load_bundle` reads a stored bundle under the contract's compatibility rule.
  Schema only: nothing writes to these tables yet (#15). No contract change.
- **Earth-observation reduction methodology** (#1, engine half).
  `engine/observation/reduction.py` specifies, per sensor (Sentinel-2,
  Landsat 5/7/8/9), the collection, band roles, DN-to-reflectance scale and
  offset, quality mask (SCL classes, or QA_PIXEL bits plus saturation), index
  per scene then annual median, zonal mean over clear pixels, and
  `n_valid_observations` as the zonal median clear-scene count. It is
  published through `describe_engine()["reduction"]` for the platform's Earth
  Engine client (#22). `reduce_period` is a numpy reference implementation,
  validated against known reflectance targets. NBR uses SWIR2. The
  `donors.min_pre_observations` rule is now applied: a candidate is excluded
  when any pre-period has fewer clear scenes than the threshold. A bundle
  warning is added when the provider reports no counts. `ENGINE_VERSION` is
  now 0.10.0.
- **Cluster-robust inference for the DiD cross-check** (#12). The standard
  error is clustered (CR1). A wild cluster bootstrap, Webb six-point below 12
  clusters and Rademacher above, gives a seeded `bootstrap` interval.
  Reported as `crosscheck.did_standard_error`, with the clustering level in
  provenance. No cluster labels reach the engine until #60, so runs are
  unclustered for now and flagged `independent_units_assumed`. The interval is
  control-side only. `ENGINE_VERSION` is now 0.9.0.
- **Engine covariate features module** (#18). `engine/features/` provides
  pure `log1p`, `winsorise` and `standardise` transforms. Each returns the
  parameters it learned, so they can be recorded. `COVARIATE_TRANSFORMS` sets
  the matching scale per covariate: raw for rainfall, elevation and slope,
  `log1p` for road distance and population density, with the rationale in
  `docs/data/sources.md`. `engineer_covariates` applies the same transform to
  the project and every candidate. It is not yet applied in a run; that lands
  with the donor-pool methodology (#3).
- **Specification curve inside a run** (#28). With
  `robustness.specification_curve` set, the engine sweeps one choice at a time
  around the request's specification: ridge, pre-period length, treatment
  date one period earlier, and donor cap. It emits
  `robustness.spec_curve.median` with a `sensitivity-envelope`,
  `robustness.spec_curve.sign_agreement`, and one
  `robustness.spec_curve.estimate.<spec>` per specification, ordered by
  estimate, with the centre marked. A sign flip is named in a warning and
  fails a verdict gate. Failed specifications are listed, never dropped.
  `ENGINE_VERSION` is now 0.8.0.
- **Monorepo structure.** `apps/` for deployable entrypoints (api, worker, web)
  and `packages/groundtruth/` for the Python distribution. Root `pyproject.toml`
  now holds shared tooling configuration only.
- **Documentation system.** `PROJECT_CONTEXT.md`, `ARCHITECTURE.md`,
  `AGENTS.md`, `DEVELOPMENT.md`, `OWNERSHIP.md`, `ROADMAP.md`, `GLOSSARY.md`,
  `SECURITY.md`, `CODE_OF_CONDUCT.md`, and a structured `docs/` tree covering
  architecture, science, data, product, engineering, decisions, operations,
  competition and research.
- **Ten architecture decision records** covering the monorepo, the
  engine/platform boundary, the analysis contract, the evidence object,
  provenance, reproducibility, the GenAI boundary, job architecture, data
  management and deployment.
- **Extension-point architecture** for Earth observation, causal methods,
  evidence, GenAI and continuous monitoring — designed, not built.
- `apps/api` ASGI entrypoint; `apps/worker` placeholder that exits non-zero.
- Capability matrix and phased implementation plan with ownership, dependencies
  and a suggested parallel order.

### Changed

- **Request fields that were accepted and then ignored are now wired or
  reported** (#54). `robustness.in_time_placebo` runs the in-time placebo and
  adds `placebo.in_time_*` evidence plus a gate. `estimation.max_pre_rmse_ratio`
  sets the SD-scaled fit gate. `robustness.confidence_level` sets the placebo
  significance level. The old hardcoded `p < 0.10` is gone, so the default is
  now `p <= 0.05`. A placebo test whose p-value floor `1/(J+1)` is above the
  level fails its gate with that reason. A primary estimator other than
  synthetic control is refused with `not_implemented`. An unknown cross-check
  or a requested specification curve (#28) gets a bundle warning.
  `describe_engine()` reports in-space and in-time placebos separately. A test
  enumerates every `EstimationSpec` and `RobustnessSpec` field.
  `donors.min_pre_observations` still waits for real observation counts (#1).
  `ENGINE_VERSION` is now 0.7.0.
- **The project is never a donor in a placebo fit** (#55). Every in-space
  placebo could load weight on the genuinely treated unit, whose post-period
  path carries the real effect, so the reference distribution was not one of
  untreated outcomes. On the seeded test panel, a large effect inflated the
  largest placebo ratio from 2.44 to 11.56. The shift in p-value is not
  uniformly conservative: under the null it moved from 14/24 to 13/24, and
  with a small effect from 9/24 to 10/24. `in_space_placebo` gains
  `exclude_indices` for further units to bar from placebo pools. The exclusion
  is recorded in the `placebo.*` provenance. `ENGINE_VERSION` is now 0.6.0.
- **The fit gate is scaled by the pre-period outcome SD, and a convex-hull
  gate is added** (#56). The old gate divided pre-RMSPE by the outcome *mean*,
  which for NDVI around 0.6 let an RMSPE of 0.18 pass, so it would essentially
  never fire on a spectral index. It now fails above 0.30 SD
  (`fit.relative_pre_rmspe`). A new `HullDiagnostic` checks two necessary
  conditions for the project to be spanned by its donors (pre-period level
  within the range of donor means, and per-period donor envelope). A material
  failure gives a warning and an `INCONCLUSIVE` verdict
  (`fit.inside_donor_hull`, `fit.hull_level_excess`,
  `fit.hull_periods_outside_envelope`). The estimator docs now state the
  variant actually implemented: no V-matrix, no covariate-informed weighting,
  no intercept. `ENGINE_VERSION` is now 0.5.0.
- **Observed series are aligned to the analysis window before estimation**
  (#53). `run_analysis` used `window.n_pre_periods` as a raw array index and
  stacked donor series without checking them, so a series that started late or
  skipped a year would be fitted against the wrong treatment date, and ragged
  donors escaped as a bare `ValueError`. The new
  `engine.observation.alignment.align_panel` derives the pre/post split from
  period labels and refuses with `insufficient_data` at stage `alignment`,
  naming every offending unit and its missing or non-finite periods. Coverage
  is recorded as `fit.n_pre_periods`, `fit.n_post_periods` and
  `fit.treatment_boundary_period`. `ENGINE_VERSION` is now 0.4.0: a window with
  a gap between `pre_end` and `post_start` now excludes the gap periods instead
  of counting them as post-treatment.
- Repository path discovery now walks up for a marker directory instead of
  counting parents, which broke silently during the package move.

---

## [0.3.0] — 2026-09-19

Contract version 1.0.0 · Engine version 0.3.0

### Added

- **`groundtruth.contracts`** — the shared, versioned boundary between the
  analytical engine and the platform: `AnalysisRequest`, `AnalysisResult`,
  evidence, provenance, units, errors, grounding rules, `DataAccess` ports and
  version-compatibility semantics.
- **`spec_hash`** reproducibility key. Same spec, seed and engine version yields
  identical numbers.
- **Typed error codes** distinguishing a scientific refusal from a malfunction,
  each mapped to an HTTP status (asserted total by test).
- **Two status vocabularies** — `AnalysisStatus` for the job lifecycle and
  `EngineStatus` for what the engine found — so a refusal is a successful job.
- **`data_mode` validation**: a request cannot label synthetic datasets as
  observed.
- **Boundary enforcement tests** parsing the AST of every module.
- `CaseDefinition.to_request()`, which deliberately drops `known_reference`.
- Result metrics: run id, per-stage timings, donor counts, fit counts.

### Changed

- **BREAKING:** split into `contracts/`, `engine/` and `platform/` by ownership.
- The engine now returns a typed result for every domain outcome instead of
  raising.
- `fit.weights_identified` surfaced when donors outnumber pre-periods.

### Fixed

- **Reproducibility:** the synthetic provider seeded from Python's salted
  `hash()`, making runs non-reproducible across processes.
- **Solver:** plain projected gradient was too slow on rank-deficient donor
  matrices. Replaced with FISTA; convergence now assessed on the objective
  rather than the weights, which are genuinely non-unique in that regime.
- **Grounding:** the filter rejected its own mandatory caveat, because the
  standard disclaimer contains the word "fraud". Added negated-assertion
  exemptions and identifier/URL masking.
- **Difference-in-differences:** the parallel-trends screen compared a
  per-period slope against a level difference. Now projects the pre-trend across
  the pre/post midpoint gap to get a commensurable implied bias.

---

## [0.2.0] — 2026-09-19

### Added

- Core domain model, provenance and evidence objects
- Donor matching with recorded eligibility exclusions and balance diagnostics
- Simplex-constrained synthetic control; difference-in-differences cross-check
- In-space and in-time placebo inference, leave-one-out, specification curve
- Evidence assembly with an explicit verdict gate chain
- Deterministic report renderer and enforced GenAI grounding
- FastAPI surface, CLI, three case definitions
- 163 tests; CI on Python 3.11–3.13 plus a scientific-integrity job
- Documentation covering problem, methodology, architecture, data sources,
  causal inference, validation, grounding, limitations, strategy, roadmap and
  demo flow

---

## [0.1.0] — 2026-09-19

### Added

- Initial scaffold: README, LICENSE, `.gitignore`, `.env.example`
