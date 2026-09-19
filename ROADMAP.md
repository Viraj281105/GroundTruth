# Roadmap

GroundTruth started as a hackathon project. The repository is structured for
what it could become over one to two years: an independent evidence and
intelligence platform for ecosystem restoration and climate claims.

This document describes the stages. It is explicit about what exists and what
does not, because a roadmap that reads like a feature list is a liability in a
project whose entire value proposition is honesty about uncertainty.

**Status vocabulary, used throughout the repository:**

| | |
| --- | --- |
| **Implemented** | Works, tested, running in CI |
| **Planned** | Designed, has an issue, not built |
| **Future** | An extension point exists; no commitment, no timeline |

---

## NOW — foundation and prototype

*Where the repository is today.*

**Implemented**

- Three-package architecture with an enforced contract boundary
- `AnalysisRequest → run_analysis → AnalysisResult`, reproducible by `spec_hash`
- Simplex-constrained synthetic control (FISTA, numpy only), DiD cross-check
- Donor matching with recorded eligibility exclusions and balance diagnostics
- In-space and in-time placebo inference, leave-one-out, permutation intervals
- Evidence assembly with an explicit verdict gate chain
- Deterministic report renderer and an enforced GenAI grounding verifier
- FastAPI surface, CLI, three case definitions
- 194 tests; CI on Python 3.11–3.13 plus a scientific-integrity job

**Not built**

- Any real Earth-observation data. Everything runs on a labelled simulated
  fixture.
- Database, job queue, worker, storage, frontend, deployment
- Any analysis of a real project

**The honest headline:** the machinery is correct — it recovers a known
injected effect and distinguishes it from a null — and it has never seen a real
forest.

---

## MVP — one real answer, end to end

*Goal: `Project → Data → Causal Analysis → Evidence → Visualization` working on
real satellite data for Kariba.*

| Workstream | Owner | Deliverable |
| --- | --- | --- |
| Earth-observation reduction methodology | Viraj | Sentinel-2/Landsat masking, compositing, index math, cross-sensor calibration |
| EO client service | Bhumi | Auth, retries, caching, dataset version pinning behind `ObservationAccess` |
| Covariate methodology | Viraj | Which covariates, how derived and transformed |
| Covariate services | Bhumi | CHIRPS, SRTM, OSM, WorldPop, WDPA behind `CovariateAccess` |
| Boundary acquisition | Bhumi | Registry geometry for all three cases, validated against registered area |
| Donor-pool methodology | Viraj | Ecoregion constraint, leakage belt, protected-area exclusion |
| Persistence and jobs | Bhumi | Database, evidence store, async analysis lifecycle |
| Core visualisations | Viraj | Counterfactual chart, placebo plot, map, evidence explorer |
| Frontend/backend integration | Bhumi | Generated types, API client, wiring |
| Kariba run | Viraj | First real result, reviewed, published whatever it says |

**Exit criterion:** a reviewed evidence bundle for Kariba from real imagery,
visible in the UI, with full provenance — and reported regardless of what it
says.

**Deliberately excluded from MVP:** carbon conversion, GenAI narration,
multiple estimators, continuous monitoring. Each is scoped later for a reason.

---

## Stage 2 — a working analysis platform

*Goal: someone who is not us can analyse a project.*

**Planned**

- Project and case management through the UI, not a YAML pull request
- Asynchronous analysis with progress, cancellation and history
- Analysis comparison: two runs, two specifications, or two projects side by side
- Biomass layer (ESA CCI / GEDI L4B) so index effects become comparable to
  tCO2e claims, with propagated error and honestly wide intervals
- GenAI narration with a measured grounding evaluation published either way
- Specification curve surfaced in the product, not just in experiments
- Report export with provenance intact
- Authentication, rate limiting, audit logging

**Exit criterion:** an analyst with no knowledge of the codebase can define a
project, run an analysis, read the evidence and export a report.

---

## Stage 3 — generalised analysis and automated ingestion

*Goal: GroundTruth analyses projects it was not hand-configured for.*

**Planned**

- Automated registry ingestion (Verra, Gold Standard, Plan Vivo, Berkeley CTP)
- Automatic donor-pool proposal from ecoregion, biome and pressure covariates
- Multi-estimator agreement: synthetic control, matched controls, DiD, event
  study — with disagreement reported as a finding rather than reconciled
- Ecosystem-specific methodology profiles (dry forest, evergreen, mangrove,
  peatland, grassland) so an indicator and window are chosen defensibly
- Batch screening across a registry slice with prioritisation
- Analyst workflow: queue, triage, annotate, escalate

**Exit criterion:** 50+ projects screened in one batch, each with per-project
provenance and a defensible indicator choice.

---

## Long term — continuous evidence intelligence

*Goal: verify once, then keep watching.*

**Future**

- Scheduled re-analysis: re-run a stored `spec_hash` on new imagery and diff
  the bundles
- Event detection: deforestation alerts, fire, ecological deterioration,
  restoration progress
- Automated review triggers when a project diverges from its own trajectory
- Portfolio-level risk intelligence across a buyer's holdings
- Expansion beyond forest carbon: biodiversity, land restoration, ecosystem
  services, water and hydrological restoration
- Public API and methodology publication

The architectural groundwork for this already exists — `spec_hash` makes a
re-run comparable, `DatasetRef` pins what was used, and the evidence bundle is
diffable. None of it is built.

---

## What we explicitly will not build

Scope discipline matters more than ambition here.

| Not building | Why |
| --- | --- |
| Credit issuance, retirement or pricing | Different regulatory category entirely |
| Automated de-listing or enforcement | No system should cost a project its status on a screening signal |
| A replacement for field verification | Ground plots measure pools no satellite sees |
| A fraud-detection product | Satellite data cannot establish intent, and framing it that way would be irresponsible |
| Our own imagery pipeline | Earth Engine and the open archives are better than anything we would build |
| A general-purpose GIS | We are a verification system that uses geospatial data, not a geospatial platform |

---

## What must be decided now, and what can wait

The distinction that keeps a small team from either over-building or painting
itself into a corner.

**Decide now — expensive to change later**

| Decision | Status |
| --- | --- |
| The engine/platform contract shape | **Decided.** ADR-002, ADR-003 |
| Evidence object and provenance model | **Decided.** ADR-004, ADR-005 |
| GenAI strictly downstream of evidence | **Decided.** ADR-007 |
| Reproducibility via `spec_hash` | **Decided.** ADR-006 |
| Ownership boundary and enforcement | **Decided.** ADR-002 |
| Status vocabulary and honesty discipline | **Decided.** This document, `AGENTS.md` |

**Abstract now — cheap to add behind an existing interface**

Earth-observation providers, covariate sources, estimators, robustness checks,
narration providers, dataset versions. Each has a port or a registry key today
and needs no structural change to extend.

**Keep simple — do not build yet**

Database, job queue, worker process, auth, caching, multi-environment config,
containerisation. Each is a small, well-understood change *because* the contract
already carries what it will need.

**Wait for a reason**

| Deferred | Trigger to build it |
| --- | --- |
| Splitting into multiple Python distributions | The engine needs an independent release cadence or an external consumer |
| Carbon conversion | After the indicator-level estimate is validated on Kariba. Stacking a conversion on an unvalidated estimate compounds two uncertainties. |
| Continuous monitoring | After a single analysis is trustworthy and cheap to re-run |
| Registry-scale batch | After one project runs end to end on real data |

---

See [`docs/product/capability-matrix.md`](docs/product/capability-matrix.md) for
the feature-level status table and
[`docs/product/implementation-plan.md`](docs/product/implementation-plan.md) for
the phased task breakdown with owners.
