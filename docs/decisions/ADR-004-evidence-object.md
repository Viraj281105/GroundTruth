# ADR-004: The evidence bundle as the unit of scientific output

**Status:** Accepted
**Date:** 2026-09-19
**Deciders:** Viraj, Bhumi

## Context

GroundTruth produces claims about real projects that carry financial and
reputational weight. A bare number — "the effect was 0.042" — is not usable by a
due-diligence team: they need the unit, the uncertainty, how it was computed,
what it depends on, and what it does not mean.

Three consumers need the same output in different shapes: the API, the report
renderer, and the GenAI narration layer. If each derived its own view from raw
estimator internals, they would drift, and the narration layer would have
nothing concrete to be checked against.

## Decision

The engine emits an **`EvidenceBundle`**: an immutable, serialisable collection
of `Evidence` items, each a single value with:

| Field | Purpose |
| --- | --- |
| `id` | Stable dotted slug (`effect.point_estimate`) so consumers can address a specific number |
| `label` | Human-readable description |
| `value` | The number, string or boolean |
| `unit` | From a declared vocabulary, or empty |
| `confidence` | Interval with its `kind` — never a bare range |
| `provenance` | Mandatory. See ADR-005. |
| `qualifiers` | Structured caveats (`is_carbon_quantity: false`) |

The bundle also carries a `verdict` and analyst-facing `warnings`.

Ids are namespaced (`claim.*`, `matching.*`, `effect.*`, `fit.*`, `placebo.*`,
`robustness.*`, `crosscheck.*`) so a new metric family is additive.

Invariants enforced at construction: ids unique, provenance complete, units from
the vocabulary, verdict always carrying the standard caveats.

**The bundle is the only currency the reporting layer may spend.** See ADR-007.

## Alternatives considered

**Return the estimator objects directly.** Each consumer reads what it needs.
Rejected: couples the API and the report to estimator internals, so changing a
solver breaks the UI, and gives the grounding verifier nothing stable to check a
narrated figure against.

**A flat dict of metrics.** Simple and JSON-friendly. Rejected: no place for
units, intervals, provenance or qualifiers, and no way to enforce that they
exist. The whole argument of this project is that a number without its
provenance and uncertainty is not evidence — the data structure should make that
true rather than hope for it.

**A fully normalised relational schema.** Correct for a mature platform.
Rejected as premature: there is no database yet, and a self-describing
serialisable object is what a worker needs to hand back across a process
boundary anyway. The bundle persists cleanly into a relational store later.

## Consequences

**Easier:** one object serves the API, the renderer, the narrator and the
archive; grounding verification becomes mechanical (every narrated number must
appear in `bundle.numeric_values()`); bundles diff cleanly, which is what makes
continuous monitoring a small addition later.

**Harder:** emitting a new metric means adding provenance and choosing a unit
and an id namespace. That friction is intentional.

**Accepted:** the bundle is verbose. Verbosity is the product.

## Revisit when

Bundles grow large enough that serialising them dominates run time — likely at
registry scale with per-donor evidence. The fix is a summary projection for
listing plus the full bundle on demand, which is additive.
