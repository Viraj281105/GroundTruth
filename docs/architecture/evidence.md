# Evidence and provenance architecture

The evidence object is the most important artefact in GroundTruth. Everything
upstream exists to produce one; everything downstream exists to render, store,
narrate or compare one.

**Status: the core object model is implemented.** Persistence, comparison and
signing are not.

---

## Why it exists

A bare number is not evidence. "The effect was 0.042" is unusable by a
due-diligence team: they need the unit, the uncertainty, how it was computed,
what it depends on, and what it does not mean.

Three consumers need the same output in different shapes — the API, the report
renderer, the GenAI narrator. Without a single structured object they would
each derive their own view from estimator internals and drift apart, and the
narration layer would have nothing concrete to be checked against.

See [ADR-004](../decisions/ADR-004-evidence-object.md).

---

## Current structure

```python
EvidenceBundle(
    case_id, schema_version,
    items:    tuple[Evidence, ...],
    verdict:  VerificationVerdict | None,
    warnings: tuple[str, ...],
)

Evidence(
    id,          # "effect.point_estimate" — stable dotted slug
    label,       # human-readable
    value,       # float | int | str | bool
    unit,        # from the declared vocabulary, or ""
    confidence,  # interval WITH its kind
    provenance,  # mandatory
    qualifiers,  # structured caveats
)
```

Invariants enforced at construction: ids unique; provenance complete; units from
the vocabulary; the verdict always carrying the standard caveats.

### Id namespaces

Stable and structured, so the UI can address a specific number and the grounding
verifier can check a narrated figure against it.

| Namespace | Contents |
| --- | --- |
| `claim.*` | Developer-reported figures under test |
| `matching.*` | Donor counts, exclusions, covariate balance |
| `effect.*` | Point estimate, cumulative effect |
| `fit.*` | RMSPE, ratio, convergence, donor weights, weight identification |
| `placebo.*` | Permutation p-value, placebo unit count |
| `robustness.*` | Leave-one-out shift, sign stability |
| `crosscheck.*` | DiD estimate and pre-trend divergence |

A new metric family is a new namespace — additive, a minor contract bump.

---

## Provenance

```python
Provenance(source, method, stage, source_uri, retrieved_at,
           code_version, parameters, inputs, notes)
```

Mandatory on every item; construction is refused without `source` and `method`.

**`inputs` forms a derivation graph** across the bundle. That graph is what makes
"provenance in two clicks" possible in the UI and what lets an auditor trace a
verdict back to an observation.

```
effect.point_estimate
  └─ inputs: matching.n_donors_admitted
       └─ inputs: (observation provenance: dataset, mask, composite)
```

**`fingerprint()`** is a stable 16-character hash excluding `retrieved_at`, so
the same computation fingerprints identically while a changed parameter does
not.

**Two constructors, deliberately distinct.** `computed()` for values GroundTruth
produced; `external()` for published third-party figures, marked
`stage="external"` so a registry figure can never be mistaken for our own
result. This is what keeps the Kariba reference honest.

See [ADR-005](../decisions/ADR-005-provenance-model.md).

---

## Uncertainty

Intervals are never bare. Each carries its `kind`, because these are not
interchangeable:

| `kind` | Meaning |
| --- | --- |
| `permutation` | From the placebo reference distribution |
| `bootstrap` | Resampling-based |
| `analytic` | Closed-form standard error |
| `sensitivity-envelope` | The **range** across specifications or leave-one-out refits. **Not a confidence interval.** |

Rendering a sensitivity envelope as a 95% confidence interval is a
misrepresentation, not a simplification. The UI must show `kind`.

---

## The target evidence object

The current structure is a working subset of where this is going. The fields
below are the long-term target; everything not marked implemented is future.

| Field | Status | Notes |
| --- | --- | --- |
| Project / case id | Implemented | `bundle.case_id` |
| Metric id and label | Implemented | `Evidence.id`, `.label` |
| Value and unit | Implemented | Unit from a declared vocabulary |
| Uncertainty | Implemented | `Confidence` with `kind` |
| Source dataset | Implemented | `Provenance.source` |
| **Dataset version** | Implemented at result level | `DatasetRef` on `AnalysisResult`; **future:** per-item |
| Transformation chain | Partial | `Provenance.method` + `parameters`; **future:** explicit ordered steps |
| Methodology reference | Partial | `method` is a slug; **future:** a link to the documented method |
| Model version | Implemented at result level | `EngineRef`; **future:** `ModelRef` per item |
| Experiment id | Implemented | `run_id`, `spec_hash` |
| Parameters | Implemented | `Provenance.parameters` |
| Provenance graph | Implemented | `Provenance.inputs` |
| Timestamp | Implemented | `retrieved_at`, result timestamps |
| **Spatial scope** | **Future** | Currently implicit in the case; should be explicit per item |
| **Temporal scope** | **Future** | Currently implicit in the window; should be explicit per item |
| **Limitations** | Partial | Verdict caveats and `qualifiers`; **future:** structured per item |
| **Signature** | **Future** | Proves authenticity, not just derivation |

**Why spatial and temporal scope matter later.** Today one bundle describes one
project over one window, so scope is unambiguous. As soon as a bundle carries
per-donor evidence, leakage-belt evidence, or per-period event-study estimates,
each item needs to say what area and what period it refers to. Adding those
fields is additive; retrofitting the *meaning* later would not be.

---

## Persistence — planned

| Concern | Decision |
| --- | --- |
| Storage | Bundle JSON as a column, plus indexed projections for listing and filtering |
| Immutability | Bundles are never updated. A re-run is a new `run_id`. |
| Contract version | Stored alongside, so an old bundle stays readable after a minor bump |
| Retrieval | By `run_id`, or by `spec_hash` for cache hits |
| Comparison | Diff two bundles by evidence id — the basis for continuous monitoring |

Indexing the whole bundle relationally would be premature. Storing the document
plus the handful of fields actually queried is the right size, and the object is
already shaped for it.

---

## What evidence enables downstream

| Consumer | Uses |
| --- | --- |
| API | Projections for listing, detail, comparison |
| Deterministic renderer | The whole bundle, rendered as a table plus provenance |
| GenAI narrator | The bundle as input; `numeric_values()` as the grounding allow-list |
| UI evidence explorer | Ids for addressing, `inputs` for drill-down |
| Continuous monitoring | Bundle-to-bundle diff by id |
| Validation harness | `spec_hash` replay, numeric equality |

The grounding check is only mechanical *because* the bundle exists: "every
number in this prose must appear in `bundle.numeric_values()`" is a
one-line rule that would otherwise be a judgement call.

---

See also: [`docs/architecture/contract.md`](contract.md) for schemas,
[`docs/architecture/genai.md`](genai.md) for how the bundle bounds the model.
