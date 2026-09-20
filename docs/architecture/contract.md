# 12. The engine/platform contract

The contract is the boundary between the analytical engine (Viraj) and the
platform (Bhumi). It lives in `packages/groundtruth/src/groundtruth/contracts/` and is the only
thing both sides depend on.

```
Project definition ──► Analysis engine ──► Structured evidence object

User ──► UI ──► API ──► Analysis job ──► Engine ──► Evidence store ──► API ──► UI / GenAI report
```

The UI never depends on a Python implementation detail. The backend is the
contract layer: it serves projections of `AnalysisResult` over HTTP, and the
frontend consumes TypeScript types generated from the OpenAPI schema.

---

## 1. Input schema — `AnalysisRequest`

Complete, self-contained and serialisable. The engine reads **nothing else**:
no YAML, no database, no environment variables, no filesystem. That property is
what makes a run replayable months later, and what lets the platform queue,
cache, retry and replay analyses without knowing any engine internals.

```python
AnalysisRequest(
    contract_version: str = "1.0.0",
    case_id:          str,                # stable slug
    project:          UnitRef,            # geometry or centroid + attributes
    claim:            ClaimUnderTest,     # under test; never an estimator input
    indicator:        Indicator,          # ndvi | evi | nbr | tree_cover_fraction | ...
    window:           AnalysisWindow,     # pre_start, pre_end, post_start, post_end
    donors:           DonorSpec,
    estimation:       EstimationSpec,
    robustness:       RobustnessSpec,
    datasets:         tuple[DatasetRef, ...],   # pinned by the platform
    seed:             int = 20260101,
    data_mode:        "observed" | "simulated",
    requested_by:     str | None,
    notes:            str,
)
```

| Sub-object | Carries |
| --- | --- |
| `UnitRef` | `unit_id`, GeoJSON-like `geometry`, centroid, `area_ha`, `attributes` |
| `ClaimUnderTest` | Developer's name, registry id, standard, area, claimed tCO2e, source URI |
| `AnalysisWindow` | Pre/post ranges; validates ordering and exposes period counts |
| `DonorSpec` | Candidates, search region, pool caps, covariates and weights, caliper, exclusions, leakage belt, coverage minimum |
| `EstimationSpec` | Primary `ModelRef`, cross-checks, ridge, minimum pre-periods, fit tolerance |
| `RobustnessSpec` | Which placebo/leave-one-out/specification-curve checks to run, confidence level |

### Validation at construction

- The window must satisfy `pre_start < pre_end < post_start <= post_end`.
- The window must supply at least `estimation.min_pre_periods` pre-periods.
- `min_donors` may not exceed `max_donors`.
- **`data_mode="observed"` with any synthetic dataset is rejected.** This is the
  one failure mode the system must not have, so it is caught at the type level
  rather than in review.

### Who builds it

The platform. `CaseDefinition.to_request()` translates a stored case into a
request and pins dataset references. It deliberately **drops the
`known_reference` block** — the published third-party figure recorded for
post-hoc validation — because feeding it forward would destroy the independence
the whole system exists to provide. A test asserts it never reaches the engine.

---

## 2. Output schema — `AnalysisResult`

```python
AnalysisResult(
    contract_version: str,
    run_id:           str,              # "run_<16 hex>"
    case_id:          str,
    spec_hash:        str,              # the request that produced this
    status:           EngineStatus,     # completed | refused | error
    engine:           EngineRef,        # engine version, contract version, git sha
    datasets:         tuple[DatasetRef, ...],
    seed:             int,
    data_mode:        str,
    started_at:       str | None,       # ISO 8601
    finished_at:      str | None,
    bundle:           EvidenceBundle | None,   # present when COMPLETED
    error:            AnalysisError | None,    # present when REFUSED or ERROR
    metrics:          RunMetrics,
)
```

Validated on construction: a `COMPLETED` result **must** carry a bundle, and a
non-completed result **must** carry an error. There is no ambiguous state.

`result.is_simulated` is the single source of truth for the UI banner. It is
true if `data_mode` is simulated *or* any referenced dataset has a synthetic
provider — so a fixture run cannot be presented as real even if a flag is set
wrongly somewhere upstream.

---

## 3. Evidence object structure

`EvidenceBundle` is the structured evidence object the whole system is built
around. It is immutable, serialisable, diffable and fully reproducible from its
provenance.

```python
EvidenceBundle(
    case_id:        str,
    schema_version: str = "1.0",
    items:          tuple[Evidence, ...],
    verdict:        VerificationVerdict | None,
    warnings:       tuple[str, ...],
)

Evidence(
    id:         str,          # "effect.point_estimate" — stable, dotted, lowercase
    label:      str,          # human-readable
    value:      float | int | str | bool,
    unit:       str,          # from the declared vocabulary, or ""
    confidence: Confidence | None,
    provenance: Provenance,   # mandatory
    qualifiers: dict,         # structured caveats
)
```

Evidence ids are stable and structured, which is what lets the UI address a
specific number and the grounding verifier check narrated figures against it:

| Namespace | Contents |
| --- | --- |
| `claim.*` | Developer-reported figures under test |
| `matching.*` | Donor counts, exclusions, covariate balance |
| `effect.*` | Point estimate, cumulative effect |
| `fit.*` | Pre-period RMSPE, RMSPE ratio, convergence, donor weights, weight identification |
| `placebo.*` | Permutation p-value, placebo unit count |
| `robustness.*` | Leave-one-out shift, sign stability |
| `crosscheck.*` | Difference-in-differences estimate and pre-trend divergence |

Bundle invariants: ids are unique; every item has complete provenance; units
come from the declared vocabulary; the verdict always carries the standard
caveats.

---

## 4. Provenance metadata

Every value records where it came from. Without this a number cannot be
audited, and an un-auditable number is not admissible in a verification report.

```python
Provenance(
    source:       str,          # "COPERNICUS/S2_SR_HARMONIZED"
    method:       str,          # "annual-median-composite/ndvi"
    stage:        str,          # ingestion|geospatial|matching|causal|uncertainty|external
    source_uri:   str | None,
    retrieved_at: datetime | None,
    code_version: str | None,
    parameters:   dict,         # everything needed to reproduce the value
    inputs:       tuple[str],   # evidence ids this was derived from
    notes:        str | None,
)
```

`fingerprint()` is a stable 16-character hash that **excludes** `retrieved_at`,
so two runs of the same computation produce the same fingerprint while a
changed parameter produces a different one.

`inputs` forms a directed graph across the bundle, which is what makes
"provenance in two clicks" possible in the UI.

Two constructors, deliberately distinct:

- `Provenance.computed(...)` — produced by the GroundTruth engine.
- `Provenance.external(...)` — a published third-party figure GroundTruth did
  **not** compute. Marked `stage="external"` so it can never be mistaken for
  our own result.

---

## 5. Error states

```python
AnalysisError(
    code:        ErrorCode,
    message:     str,     # plain language, safe to show a user
    stage:       str,
    detail:      dict,    # structured context
    remediation: str | None,
)
```

| Code | Meaning | HTTP | Refusal? |
| --- | --- | ---: | :---: |
| `invalid_request` | Failed validation | 422 | no |
| `contract_version_mismatch` | Engine cannot serve this contract version | 409 | no |
| `data_unavailable` | A required dataset could not be retrieved | 503 | no |
| `insufficient_data` | Data exists but is too sparse to support an estimate | 422 | **yes** |
| `donor_pool_inadequate` | No admissible donor pool could be constructed | 422 | **yes** |
| `estimation_failed` | An estimator was mis-specified or failed to fit | 500 | no |
| `not_implemented` | The interface exists, the implementation does not | 501 | no |
| `internal_error` | Unexpected failure | 500 | no |

**`is_refusal` is the important distinction.** A refusal is a legitimate
scientific outcome — the system correctly declining to produce a fragile
number — and the UI must render it as such, with its explanation, not as an
error state. A malfunction is a problem to be fixed. Conflating them would
teach users to dismiss the most valuable thing the system does.

A test asserts every `ErrorCode` has an HTTP mapping, so a new code cannot
silently become a 500.

---

## 6. Analysis status states

Two enums, because the job and the science can succeed or fail independently.

**`AnalysisStatus`** — platform job lifecycle:

```
queued ──► running ──► succeeded          (terminal)
              │
              ├──────► failed             (terminal: timeout, crash, upstream down)
              └──────► cancelled          (terminal)
```

**`EngineStatus`** — what the engine found:

```
completed   evidence bundle produced, verdict attached
refused     declined to estimate; a legitimate scientific outcome
error       could not run; malformed request or internal failure
```

A job can be `succeeded` while its engine status is `refused`. That is the
normal, correct outcome for a project the data cannot support, and it must not
be surfaced as a failed job.

---

## 7. Versioning requirements

`CONTRACT_VERSION` follows semver with explicit semantics:

| Bump | Meaning | Requires |
| --- | --- | --- |
| **major** | Breaking. A field removed or renamed, a type changed, or an existing value given a new meaning. | Both owners agree; migration for stored bundles |
| **minor** | Additive. New optional field, new enum member older consumers can ignore. | Safe for the engine to ship ahead of the platform |
| **patch** | Documentation or validation tightening, no shape change. | Either owner |

`is_compatible(produced_under, consumer)` is true when major versions match and
the consumer is not older than the producer at the minor level. A newer
consumer reads older bundles; an older consumer does not read newer ones.

Stored evidence records the contract version it was produced under, so a bundle
written months ago still loads and renders correctly.

`ENGINE_VERSION` is separate and bumped whenever results could change. A
methodology fix that alters an estimate is an engine bump even if the contract
is untouched.

---

## 8. Model and experiment identifiers

```python
EngineRef(engine_version, contract_version, git_sha)   # which build ran
ModelRef(model_id, variant, parameters)                # which estimator
DatasetRef(dataset_id, version, provider, asset, source_uri, retrieved_at)
run_id     = "run_<16 hex>"        # this execution
spec_hash  = blake2b(specification)  # this specification
```

`EngineRef` and `ModelRef` are deliberately distinct: one engine build offers
several estimators, and a specification curve runs many `ModelRef`s over one
request.

**`spec_hash` is the reproducibility key.** Two requests with the same hash
must produce the same result under the same engine version and datasets. It
excludes `requested_by` and `notes`, because who asked for a run does not
change what the run computes, and it excludes `retrieved_at` on dataset
references for the same reason. It is computed with `blake2b`, not Python's
`hash()`, which is salted per process and would differ between runs.

The platform uses `spec_hash` as its cache key. Validation uses it to assert
that a replayed analysis reproduces its original numbers exactly.

---

## 9. Dataset identifiers

```python
DatasetRef(
    dataset_id:   "sentinel2-l2a",
    version:      "2024.1",                      # provider version or snapshot date
    provider:     "google-earth-engine",
    asset:        "COPERNICUS/S2_SR_HARMONIZED",
    source_uri:   "...",
    retrieved_at: "2026-09-19T...",
)
```

**The platform pins dataset versions; the engine never chooses one.** A re-run
months later uses the same imagery rather than whatever the provider currently
serves, which is what makes a published result checkable.

`is_synthetic` is true when the provider is `synthetic`. This propagates
automatically into `AnalysisResult.is_simulated`, the evidence bundle warnings,
the verdict caveats, the API response and the UI banner — nobody has to
remember to set a flag.

---

## 10. Uncertainty representation

Intervals are never bare. Each carries its `kind`, because these are not
interchangeable and presenting them as if they were would be misleading:

```python
Confidence(lower, upper, level=0.95, kind=...)
```

| `kind` | What it means |
| --- | --- |
| `permutation` | Derived from the placebo reference distribution |
| `bootstrap` | Resampling-based |
| `analytic` | Closed-form standard error |
| `sensitivity-envelope` | The **range across specifications or leave-one-out refits**. Not a confidence interval, and must not be rendered as one. |

Additional uncertainty carried outside the interval:

| Field | Meaning |
| --- | --- |
| `placebo.p_value` | Permutation p-value with the add-one (Phipson–Smyth) correction, so it is never zero. With *J* donors the floor is `1/(J+1)`, and the system states this. |
| `fit.pre_rmspe` | How well the model fitted before treatment — the denominator that makes a post-period gap meaningful |
| `fit.rmspe_ratio` | Post/pre ratio, the placebo test statistic |
| `fit.weights_identified` | False when donors outnumber pre-periods: the counterfactual path is determined, the individual weights are not |
| `robustness.max_absolute_shift` | Largest estimate change from dropping one contributing donor |
| `robustness.sign_stable` | Whether the sign survives every leave-one-out refit |

The UI must render `kind` alongside every interval. A sensitivity envelope shown
as a 95% confidence interval is a misrepresentation, not a rounding of detail.

---

## 11. The DataAccess ports

The contract's second direction. The engine declares what data it needs; the
platform decides where it comes from.

```python
class ObservationAccess(Protocol):
    def series(self, spec: ObservationSpec) -> TimeSeries: ...
    def dataset(self, indicator: Indicator) -> DatasetRef: ...
    def provenance(self, spec: ObservationSpec) -> Provenance: ...

class CovariateAccess(Protocol):
    def covariates(self, unit: UnitRef, keys: tuple[str, ...]) -> dict[str, float]: ...
    def dataset(self, key: str) -> DatasetRef: ...

class DonorCandidateAccess(Protocol):
    def candidates(self, request: AnalysisRequest) -> list[UnitRef]: ...

DataAccess(observations=..., covariates=..., donors=...)
```

This is the seam between **methodology** and **plumbing**:

| Engine decides (Viraj) | Platform decides (Bhumi) |
| --- | --- |
| Which index responds to the thing being screened | Which provider serves it |
| Which pixels are usable, and how a year is reduced to one number | Authentication and credential handling |
| Which covariates matter and how they are derived | Retries, rate limits, timeouts |
| What counts as sufficient coverage | Caching and dataset version pinning |
| What to do when coverage is insufficient | Job orchestration and cancellation |

The engine must never open a socket, read a credential or touch the filesystem.
If it needs something, it asks a port. `test_contract_boundary.py` enforces this
by rejecting imports of `requests`, `httpx`, `socket`, `os`, `pathlib`, database
drivers and `ee` anywhere under `engine/`.

---

## 12. Change process

1. Open an issue labelled `contract` describing the change and why.
2. Both owners agree on the shape **before** either side implements against it.
3. Bump `CONTRACT_VERSION` per the semantics above.
4. Update this document in the same pull request.
5. Add or update a test in `tests/test_contract_boundary.py`.
6. If major: write the migration for stored bundles and confirm old bundles
   still load.

A contract change that lands without both owners on the pull request should be
reverted, regardless of how correct it is. The value of the boundary is that it
is reliable, not that it is optimal.

---

Previous: [11. Demo flow](../competition/demo-flow.md) · Next: [13. Implementation plan](../product/implementation-plan.md)
