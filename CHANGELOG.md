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
