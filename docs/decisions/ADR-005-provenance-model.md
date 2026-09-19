# ADR-005: Mandatory provenance on every value

**Status:** Accepted
**Date:** 2026-09-19
**Deciders:** Viraj, Bhumi

## Context

GroundTruth exists because carbon-credit claims are asserted without an
independent, checkable basis. A system that replaced one unverifiable number
with another unverifiable number would have no reason to exist.

Anyone reading a GroundTruth result must be able to ask "where did this come
from?" and get a complete answer without reading the source code.

## Decision

Every `Evidence` item carries a mandatory `Provenance` record:

```python
Provenance(
    source,        # "COPERNICUS/S2_SR_HARMONIZED"
    method,        # "annual-median-composite/ndvi"
    stage,         # ingestion|matching|causal|uncertainty|external
    source_uri, retrieved_at, code_version,
    parameters,    # everything needed to reproduce the value
    inputs,        # evidence ids this was derived from
    notes,
)
```

Construction is refused if `source` or `method` is missing.

**`inputs` forms a derivation graph** across the bundle, which is what makes
"provenance in two clicks" possible in the UI and what lets an auditor trace a
verdict back to an observation.

**`fingerprint()`** is a stable hash excluding `retrieved_at`, so the same
computation produces the same fingerprint while a changed parameter produces a
different one.

**Two constructors, deliberately distinct.** `Provenance.computed()` for values
GroundTruth produced; `Provenance.external()` for published third-party figures,
marked `stage="external"` so a registry figure can never be mistaken for our own
result.

## Alternatives considered

**Provenance at the bundle level only.** One record describing the whole run.
Much less code. Rejected: different values in a bundle genuinely have different
provenance — a registry-reported claim, a Sentinel-2 composite and a placebo
p-value are not the same kind of thing, and collapsing them would make the
external-figure distinction impossible.

**Optional provenance, added where convenient.** Rejected: it would be omitted
exactly where it is least convenient and most needed. Mandatory at construction
means it cannot be forgotten.

**Full W3C PROV-O modelling.** Standards-compliant and interoperable. Rejected
as disproportionate: the graph here is shallow, and the cost of PROV tooling
exceeds the benefit until someone external actually consumes it. The current
model maps onto PROV-O later if needed.

## Consequences

**Easier:** every number is auditable; the derivation graph drives the UI;
fingerprints support caching and reproducibility checks; third-party figures are
structurally distinguishable from ours.

**Harder:** every emitted value needs a provenance record. This is the single
largest source of verbosity in the assembler, and it is the point.

**Accepted:** provenance is not cryptographically signed, so it proves
derivation, not authenticity. Signing is a future item, noted in `SECURITY.md`.

## Revisit when

An external party consumes bundles and needs interoperable provenance, or
evidence integrity needs to survive an untrusted intermediary.
