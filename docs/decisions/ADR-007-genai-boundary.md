# ADR-007: GenAI strictly downstream, grounding enforced in code

**Status:** Accepted
**Date:** 2026-09-19
**Deciders:** Viraj, Bhumi

## Context

GroundTruth needs to turn statistical output into something a procurement or
ESG analyst can act on. A language model is good at that. It is also capable of
producing a fluent, plausible sentence containing a number that does not exist —
which, in a verification system, is worse than producing nothing at all, because
a reader will trust it.

The competition framing makes the GenAI layer prominent. That raises the stakes
rather than lowering them: a visible AI feature that invents a carbon figure
would discredit the entire project.

## Decision

**The model is downstream of every number.**

```
data → analytical engine → verified evidence bundle → LLM → grounding check → publish
```

Never:

```
data → LLM → invented conclusion
```

Four structural guarantees:

**1. The model never sees raw data.** It receives only the `EvidenceBundle` and
the deterministic report. There is no code path from satellite imagery to a
prompt.

**2. Its output is verified, not trusted.** `contracts/grounding.py` checks
every number against the bundle within tolerance, scans for prohibited
assertions (fraud, legal conclusions, certainty language, index-to-carbon
phrasing), and requires the verdict caveats to survive into the prose.

**3. Failure degrades to correct-and-dry.** On any violation the deterministic
renderer is published instead. `render_deterministic` produces a complete report
with no model, no API key and no network — so **the scientific pipeline has no
dependency on an LLM at all.**

**4. The grounding rules live in `contracts/`, not in the platform.** They
define what a valid report is, so both owners depend on them: Viraj authors the
scientific rules, Bhumi calls them from the report pipeline.

## Alternatives considered

**Prompt instructions alone.** Tell the model not to hallucinate. Reduces the
rate; does not make the failure impossible. Rejected because the consequence of
one escape is severe and the check is cheap. Instructions are still in the
prompt — as a first line, not the only one.

**Human review of every generated report.** Correct, and unscalable. It also
fails in the demo, where reports are generated live.

**No GenAI at all.** Genuinely tempting, and the deterministic renderer means
this remains a supported mode. Rejected because the accessibility gain for
non-specialists is real, and because the enforced-boundary design is itself a
contribution worth demonstrating.

**Let the model compute derived figures** (annualise, convert units, compute
percentages). Rejected: that is analysis, and analysis belongs in the engine
where it is tested and provenance-tracked. If a report needs a derived figure,
the engine emits it as evidence.

## Consequences

**Easier:** the narration layer is optional and swappable; the safety property
holds regardless of which model is used, so provider choice becomes a quality
question rather than a safety one; the architectural claim is demonstrable — a
test shows a hallucinating narrator being rejected and its invented figure
discarded.

**Harder:** the model cannot add anything not already in the bundle, so a
genuinely useful narrative fact must first become evidence.

**Accepted:** numeric grounding cannot catch a *rhetorical* misrepresentation —
text that uses only real numbers while softening "inconclusive" into "results
suggest". The caveat-retention check partially addresses this, and
`inconclusive fidelity` is an explicit metric in the evaluation plan. This is
the residual risk and it is named rather than hidden.

## Revisit when

The narration layer needs to answer free-form user questions rather than render
a fixed report. That is a larger surface: retrieval over multiple bundles, and
grounding checks that span them.
