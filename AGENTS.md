# AGENTS.md — operating instructions for AI coding agents and new developers

Read this before changing anything. It is the shortest path to being useful
here and the fastest way to avoid the mistakes that matter.

If you read nothing else, read **§3 Non-negotiable rules** and **§4 Where code
goes**.

---

## 1. What GroundTruth is

An independent screening system for climate restoration and carbon-credit
claims. It estimates what a project *actually achieved* by comparing it to a
counterfactual built from comparable regions the project did not touch, using
satellite time series and causal inference, and reports that estimate with its
uncertainty and full provenance.

It is **not** a fraud detector, not a carbon accounting system, and not a
replacement for accredited field auditing. See `PROJECT_CONTEXT.md`.

## 2. Repository shape in one screen

```
apps/          deployable entrypoints — api (thin ASGI), worker (not built), web (Next.js)
packages/
  groundtruth/ the Python distribution
    src/groundtruth/
      contracts/   SHARED, VERSIONED. The boundary. Both sides depend on it.
      engine/      Viraj. Pure computation. AnalysisRequest -> AnalysisResult.
      platform/    Bhumi. API, cases, datasets, jobs, store, storage, reports.
cases/         project definitions as YAML data
data/          raw/interim/processed/external — gitignored contents
docs/          architecture/ science/ data/ product/ engineering/ decisions/ ...
experiments/   pre-registered validation harnesses
tests/         the whole suite, including the boundary enforcement test
```

## 3. Non-negotiable rules

These are not style preferences. Breaking one produces output that is
scientifically wrong or ethically unsafe, and the build is wired to catch most
of them.

**R1 — NDVI is not carbon.**
A spectral index is a reflectance ratio; carbon is a mass. Any mapping needs an
allometric or biomass model with its own error budget.
`groundtruth.contracts.units.assert_not_index_to_carbon` raises on implicit
conversion. Do not weaken, bypass or `# noqa` it.

**R2 — Never state or imply fraud.**
A divergence between an independent estimate and a developer's claim means the
claim *warrants accredited review*. That is all it means. No `VerdictLabel`
value may read as an accusation, and
`groundtruth.contracts.grounding` blocks fraud, legal-conclusion and
certainty language in generated text.

**R3 — Observed change is not causal effect.**
Every estimate carries its donor pool, pre-treatment fit, placebo p-value and
identifying assumptions. Those conditions travel with the number, in its
provenance and qualifiers.

**R4 — The GenAI layer computes nothing.**
It receives a finished `EvidenceBundle` and narrates it. If you want a model to
calculate, derive, annualise or convert something, that work belongs upstream
in the deterministic engine.

**R5 — Prefer an honest refusal to a fragile number.**
`InsufficientDataError`, `DonorPoolError` and `EngineStatus.REFUSED` are
features. "We cannot tell" beats an estimate built on six donors.

**R6 — Never fabricate results.**
No committed number may describe a real project unless it was computed from
real data by code in this repository. Placeholders are marked `NOT IMPLEMENTED`,
`NOT YET OBTAINED` or `SIMULATED DATA` — never filled with a plausible value.

**R7 — Simulated data must be impossible to mistake for real.**
`data_mode` is declared by the platform and validated: a request cannot label
synthetic datasets as observed. The flag propagates into warnings, caveats, the
API response and the UI banner. Do not add a path that bypasses it.

**R8 — Reproducibility is a requirement.**
Same `spec_hash` + same seed + same engine version ⇒ identical numbers. Never
seed from Python's `hash()`; it is salted per process. Use
`contracts.identifiers.spec_hash` or `blake2b`.

## 4. Where code goes

Ask: *is this a scientific decision, a plumbing decision, or a shared
vocabulary decision?*

| If you are... | It goes in | Owner |
| --- | --- | --- |
| Deciding which index, mask, composite or covariate to use | `engine/observation/`, `engine/features/` | Viraj |
| Changing how donors are selected, weighted or excluded | `engine/matching/` | Viraj |
| Changing an estimator, placebo or uncertainty method | `engine/causal/`, `engine/uncertainty/` | Viraj |
| Changing what evidence is emitted or how the verdict is decided | `engine/assembler.py` | Viraj |
| Building any UI | `apps/web/` | Viraj |
| Adding an endpoint, schema or validation | `platform/api/` | Bhumi |
| Fetching, authenticating, caching or pinning a dataset | `platform/datasets/` | Bhumi |
| Persisting anything | `platform/store/`, `platform/storage/` | Bhumi |
| Queueing, retrying or scheduling work | `platform/jobs/` | Bhumi |
| Generating or narrating a report | `platform/reports/` | Bhumi |
| Deploying, monitoring or hardening | `infrastructure/`, `.github/` | Bhumi |
| Changing a shared type, error code or the contract | `contracts/` | **both** |

**The heuristic that resolves most cases:** methodology belongs to the engine,
plumbing belongs to the platform. *Which* covariates matter is methodology;
*how* they are fetched, retried and cached is plumbing.

## 5. What you must not change without agreement

| Do not change | Why |
| --- | --- |
| Anything in `contracts/` | Both workstreams depend on it. Needs both owners on the PR and a version bump. |
| `contracts/units.py` guards | R1 lives here |
| `contracts/grounding.py` prohibited patterns | R2 lives here |
| The verdict gate chain in `engine/assembler.py` | Removing a gate creates a weak-positive path that does not currently exist |
| `tests/test_contract_boundary.py` | It is the boundary. Weakening it to make an import pass defeats the purpose. |
| `known_reference` handling in `cases/` | Feeding a third-party figure into the engine destroys the independence the system exists to provide |
| Any case's `status: analysed` | Only a reviewed real run may set it; a test enforces this |

If a test in this list fails, the fix is almost always in your change, not in
the test.

## 6. How to validate a change

```bash
pip install -e "packages/groundtruth[api,genai,dev]"   # once
ruff format packages tests && ruff check packages tests
mypy
pytest
```

All four must pass. CI runs them on Python 3.11, 3.12 and 3.13, plus a
`scientific-integrity` job that asserts the claims the README makes.

Additional checks for specific work:

| If you changed... | Also run |
| --- | --- |
| An estimator | `pytest tests/test_causal.py tests/test_uncertainty.py` — the recovery test must still recover the known effect |
| Grounding rules | `pytest tests/test_grounding.py` — including the hallucinating-narrator fallback |
| Anything in `contracts/` | `pytest tests/test_contract_boundary.py` and bump `CONTRACT_VERSION` |
| Package structure | `pytest tests/test_contract_boundary.py` — the AST import checks |
| A case definition | `groundtruth cases && groundtruth show <case>` |
| The pipeline end to end | `groundtruth verify kariba-redd --synthetic` |

## 7. Conventions

**Python.** 3.11+ floor. `from __future__ import annotations` everywhere. Full
type annotations on public functions; `mypy` runs with `disallow_untyped_defs`.
Pydantic v2 for anything crossing a boundary; frozen models for value objects.
Line length 100. Google-style docstrings that say *why*, not *what* — the code
already says what.

**Errors.** Specific and typed, from `contracts/errors.py`. Never swallow an
exception into a weaker claim. Domain failures inside the engine become a typed
`AnalysisResult`, not a raise; programming errors still raise.

**Naming.** Evidence ids are lowercase dotted slugs (`effect.point_estimate`).
Dataset ids are lowercase kebab (`sentinel2-l2a`). Case ids are lowercase kebab
(`kariba-redd`).

**TypeScript.** Types come from the generated API client, never hand-written
against a Python implementation detail.

**Commits.** Conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`,
`test:`, `build:`, `ci:`, `chore:`). Explain *why* in the body, especially for
estimator or grounding changes.

**Comments.** Match the density of the surrounding file. Explain reasoning and
non-obvious constraints; do not narrate the code.

## 8. Things that look like bugs but are not

Before "fixing" one of these, read the linked doc.

| Behaviour | Why it is correct |
| --- | --- |
| Kariba returns `INCONCLUSIVE` | An NDVI effect and a tCO2e claim are not commensurable. Closing the gap needs a biomass layer. `docs/science/causal-inference.md` |
| `fit.weights_identified` is `False` | More donors than pre-periods means weights are not unique, though the counterfactual path is. This is reported, not hidden. |
| Placebo p-value never reaches 0 | Add-one correction. With *J* donors the floor is `1/(J+1)`. |
| `earth_engine_access` raises instead of returning fixtures | A silent fallback would let simulated numbers be served under a real-data label. R7. |
| Mikoko Pamoja is expected to be inconclusive | ~117 ha is below what a 30 m annual composite resolves. It is a negative control on the method. |
| The engine returns `REFUSED` rather than raising | A domain failure is information to persist and show, not an exception to stringify at a job boundary. |
| DiD disagrees with synthetic control | Usually means parallel trends fails. Both are reported; the disagreement is the finding. |

## 9. Status discipline

The repository is explicit about what exists. Keep it that way.

- **Implemented** — works, tested, in CI.
- **Planned** — designed, has an issue, not built.
- **Future** — an extension point exists; no commitment.

**No analysis of a real project has been run.** Everything the pipeline
currently produces comes from a simulated fixture. Do not write documentation,
UI copy or commit messages that imply otherwise. If you add a capability,
update the status tables in `README.md`, `ARCHITECTURE.md` and
`docs/product/capability-matrix.md` in the same change.

## 10. When you are unsure

1. Check `docs/decisions/` — the ADR may already have decided it.
2. Check `GLOSSARY.md` — the term may mean something specific here.
3. Prefer the option that makes a wrong answer *impossible* over the one that
   makes it *unlikely*. Most of this codebase is built that way on purpose.
4. If it touches `contracts/`, stop and ask both owners.
