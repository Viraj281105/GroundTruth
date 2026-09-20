# 3. Architecture

## The one decision that shapes everything

The system is split by a hard boundary:

```
┌──────────────────────── DETERMINISTIC ENGINE ────────────────────────┐
│                                                                      │
│  ingestion → geospatial → matching → causal → uncertainty → evidence │
│                                                                      │
│  No language model runs here. Every value carries Provenance.        │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                         EvidenceBundle (immutable)
                                   │
┌──────────────────────── REPORTING LAYER ─────────────────────────────┐
│                                                                      │
│  deterministic renderer  ──or──  GenAI narration → grounding check   │
│                                          │                           │
│                                    fails → fall back to renderer     │
└──────────────────────────────────────────────────────────────────────┘
```

The bundle is the contract. A language model that receives raw satellite data
and is asked "was this project additional?" is guessing. A model that receives a
verified bundle and is asked "explain these numbers" is doing something it is
actually reliable at.

## Package layout

```
packages/groundtruth/src/groundtruth/
├── contracts/         SHARED, VERSIONED. The boundary both sides depend on.
│   ├── types.py       ProjectClaim, TimeSeries, DonorMatch, Confidence,
│   │                  Indicator, VerdictLabel, VerificationVerdict
│   ├── request.py     AnalysisRequest — the engine's only input
│   ├── result.py      AnalysisResult, AnalysisError, EngineStatus, ErrorCode
│   ├── ports.py       ObservationAccess / CovariateAccess /
│   │                  DonorCandidateAccess protocols, DataAccess bundle
│   ├── provenance.py  Provenance: source, method, parameters, inputs, hash
│   ├── evidence.py    Evidence, EvidenceBundle, EvidenceBuilder
│   ├── grounding.py   the enforced GenAI boundary
│   ├── units.py       unit vocabulary + the index→carbon guard
│   ├── identifiers.py DatasetRef, ModelRef, EngineRef, spec_hash
│   ├── version.py     contract version and compatibility rules
│   └── errors.py      typed exception hierarchy
├── engine/            Viraj. Pure computation. No I/O, no credentials.
│   ├── run.py         run_analysis — the single entrypoint
│   ├── assembler.py   bundle construction + the verdict gate chain
│   ├── observation/   indices.py, masking.py, zonal.py — RS methodology
│   ├── matching/donors.py    donor-pool construction with recorded exclusions
│   ├── causal/
│   │   ├── synthetic_control.py  simplex-constrained FISTA solver + diagnostics
│   │   └── did.py                DiD with a pre-trend divergence diagnostic
│   └── uncertainty/
│       ├── placebo.py     in-space and in-time permutation inference
│       └── robustness.py  leave-one-out, permutation intervals, spec curve
├── platform/          Bhumi. Everything with a socket, a credential or a disk.
│   ├── api/           FastAPI surface (app.py, schemas.py)
│   ├── cases/registry.py     YAML case loading and validation
│   ├── datasets/      access.py (port bundles), synthetic.py, earthengine.py
│   ├── reports/       narrative.py, providers.py
│   ├── jobs/ store/ storage/   declared, not yet built
│   └── config.py      environment-driven settings
├── logging.py
└── cli.py             cases / show / verify / doctor
```

## Dependency direction

Dependencies point one way, inward toward `contracts`. `contracts` imports
nothing from either side. The engine depends on the port protocols, never on
concrete providers, which is why swapping the synthetic fixture for Earth
Engine is a configuration change rather than a refactor. The direction is
enforced by `tests/test_contract_boundary.py`, which parses the AST of every
module and fails the build on a cross-boundary import.

## Why protocols instead of base classes

`contracts.ports` uses `typing.Protocol`. A provider satisfies it structurally,
so a test double, a cached-file reader and a live Earth Engine client are
interchangeable without inheritance ceremony. `run_analysis` accepts any
`DataAccess` bundle whose members have the right shape.

## Why the engine has no SciPy, GDAL or geopandas

The synthetic-control solver is implemented on numpy alone. Heavy geospatial
dependencies live behind the `geo` and `earthengine` extras. The consequence is
that the full analytical pipeline, its tests and CI run anywhere Python runs,
with no system libraries. Raster work needs the extras; causal inference does
not.

## Provenance

Every `Evidence` item carries a `Provenance` record naming its source, the
method that produced it, the parameters needed to reproduce it, and the ids of
the evidence it was derived from. `fingerprint()` gives a stable hash, excluding
the retrieval timestamp, so two runs of the same computation produce the same
fingerprint and a changed parameter produces a different one.

This is what makes the report auditable: any number in it can be traced back
through its provenance chain to the observation it came from.

## Error design

Errors are specific and non-recoverable by default:

| Error | Raised when |
| --- | --- |
| `InsufficientDataError` | Data exists but is too sparse to support an estimate |
| `DonorPoolError` | No admissible donor pool can be constructed |
| `EstimationError` | An estimator is mis-specified or given bad shapes |
| `GroundingViolationError` | Generated text contains unverifiable claims |
| `DataUnavailableError` | A required product cannot be retrieved |

Nothing degrades silently into a weaker claim. An honest failure is more useful
to a due-diligence team than a fragile number.

## API surface

| Endpoint | Behaviour |
| --- | --- |
| `GET /health` | Reports what is genuinely implemented, including the things that are not |
| `GET /cases` | Case definitions with status |
| `GET /cases/{id}` | Full definition including `known_reference` |
| `POST /cases/{id}/verify` | Runs the pipeline; returns the full bundle |

`POST .../verify` with `synthetic: false` returns **501 Not Implemented**. It
does not serve simulated numbers under a real-data label.

## Implementation status

| Component | Status |
| --- | --- |
| Core domain model, provenance, evidence | Implemented |
| Spectral indices, cloud masking, zonal stats | Implemented |
| Donor matching with exclusion accounting | Implemented |
| Synthetic control solver and diagnostics | Implemented |
| Difference-in-differences cross-check | Implemented |
| Placebo inference, leave-one-out, spec curve | Implemented |
| Evidence assembly and verdict gate chain | Implemented |
| Deterministic report renderer | Implemented |
| Grounding verifier and safe fallback | Implemented |
| Pipeline orchestration, CLI, API | Implemented |
| Synthetic data provider | Implemented (simulated data, clearly marked) |
| **Earth Engine observation calls** | **Not implemented** |
| **Real covariate extraction** | **Not implemented** |
| **Project boundary geometry** | **Not obtained** |
| **GenAI narration providers** | **Not implemented** |
| **Biomass / carbon conversion** | **Not implemented, by design for now** |
| **Any analysis of a real project** | **Not run** |

## Planned Earth Engine reduction

Documented in `packages/groundtruth/src/groundtruth/platform/datasets/earthengine.py`:

1. `ee.Initialize` with a service account
2. `COPERNICUS/S2_SR_HARMONIZED` filtered to the AOI and period
3. SCL-based cloud and shadow masking
4. Annual median composite, then the index expression
5. `reduceRegion` with `mean().combine(count())` to get value and coverage
6. Return a `TimeSeries` with `n_valid_observations` populated

---

Previous: [2. Methodology](../science/methodology.md) · Next: [4. Data sources](../data/sources.md)
