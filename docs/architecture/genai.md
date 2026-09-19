# 7. GenAI grounding

## Where the model sits

```
NOT THIS:   raw satellite data  →  LLM  →  "the project over-issued 57%"

THIS:       raw data → stats/CV/ML engine → verified evidence bundle
                                                     ↓
                                          LLM narrates the bundle
                                                     ↓
                                          grounding verifier
                                                     ↓
                                    pass → publish   fail → deterministic report
```

The language model is downstream of every number. It explains; it does not
compute, estimate, infer or conclude.

## Why this is architecture and not prompting

Instructing a model to avoid hallucination reduces the rate. It does not make
the failure mode impossible, and in a verification system a single fluent
invented figure is worse than no report at all — it is exactly the kind of
output a reader will trust.

So the constraint is enforced downstream of the model, where it does not depend
on the model complying:

1. The model receives only the `EvidenceBundle` and the deterministic report.
   There is no path from raw data to the model.
2. Its output is parsed and every number checked against the bundle.
3. Its output is scanned for prohibited assertions.
4. Required caveats must survive into the prose.
5. On any failure the deterministic report is published instead.

The system degrades to **correct and dry**, never to **fluent and wrong**.

## The deterministic renderer

`render_deterministic` produces a complete Markdown report — verdict, evidence
table with units and intervals, caveats, and a full provenance section with
fingerprints — with no model, no API key and no network.

This matters beyond convenience: **the scientific pipeline has no dependency on
a language model.** Remove the GenAI layer entirely and the system still works.
A test asserts that the deterministic renderer passes its own grounding check,
so the fallback is never the weaker product in terms of correctness.

## The three checks

### 1. Numeric grounding

Every number in the text must match a bundle value within a 2% relative
tolerance. Percentage renderings of a bundle value are accepted, so a model may
write "3.85 percent" for a stored 0.0385.

Exempt without a match: four-digit years, small integers 0–10 (list markers and
counts), and anything in `extra_allowed_values`.

Masked before scanning, because they contain digit runs that assert nothing:

- backticked identifiers and hex provenance fingerprints
- URLs

A backticked span holding *only* a plain number is still scanned, so a figure
cannot be smuggled past the check by wrapping it in backticks.

Identifiers like `donor-031` are not read as negative numbers: a minus sign
only counts as a sign when it does not follow a word character.

### 2. Prohibited assertions

| Pattern class | Why blocked |
| --- | --- |
| fraud, scam, deliberate inflation, lied, deceived | GroundTruth has no standing to allege misconduct |
| criminal, illegal, guilty | Legal conclusions are outside its competence |
| proves that, conclusively shows, definitive, certainly | Overstates what a screening estimate supports |
| "NDVI of X equals Y tCO2e" | A spectral index is not a carbon stock |

**Negated forms are exempt.** The mandatory caveat says "not evidence of fraud",
which contains the word the fraud filter looks for. Without the exemption the
system would reject its own disclaimer — and the failure would be quiet, because
the safe fallback would simply fire on every correctly-caveated report. The
exemption list is in `NEGATED_ASSERTION_PATTERNS`, and a test covers it.

### 3. Required caveats

`policy_for_bundle` derives required phrases from the verdict's caveats. A
distinctive fragment of each must appear, so the model may re-flow wording
without dropping meaning.

## The system prompt

The narration prompt states the rules explicitly, and notes that they are
checked automatically afterwards:

1. Every number must appear in the bundle. No new computation, no re-rounding,
   no annualising, no unit conversion.
2. Never state or imply fraud, deception, intent or illegality.
3. Never describe a vegetation index as an amount of carbon.
4. Never write that anything is proven, definitive, certain or conclusive.
5. Reproduce every caveat.
6. If the outcome is inconclusive, say so plainly. Do not soften it.

## Provider status

| Provider | Status |
| --- | --- |
| Deterministic renderer | Implemented, always available |
| `EchoNarrator` (test double) | Implemented |
| Nugen | Interface defined, HTTP call **not implemented** |
| OpenAI | Interface defined, HTTP call **not implemented** |
| Anthropic | Interface defined, HTTP call **not implemented** |

`build_narrator` raises `ConfigurationError` if a provider is selected without a
key, rather than silently disabling narration — a silent degrade would hide a
deployment mistake.

## The planned evaluation

`experiments/genai_grounding_eval/` specifies a comparison of Nugen's alignment
stack against an unaligned baseline on identical evidence bundles, measuring:

- **ungrounded figure rate** — numbers not traceable to the bundle
- **prohibited assertion rate** — fraud, legal or certainty claims
- **caveat retention rate** — required caveats surviving into the prose
- **fallback rate** — how often the deterministic report has to take over

**This evaluation has not been run.** No comparative claim about any provider
appears anywhere in this repository, and none should until the harness produces
numbers.

Note that the grounding verifier makes the *outcome* safe regardless of which
model is used. What the evaluation measures is how often the safety net has to
catch something — which is a question about model quality, not about whether the
system can be trusted.

## Testing the boundary

`tests/test_grounding.py` covers:

- grounded text accepted
- invented figures rejected
- plausible-but-wrong figures rejected (the dangerous case)
- percentage renderings accepted
- eight varieties of accusatory and overclaiming text rejected
- index-to-carbon phrasing rejected
- the approved "warrants review" framing accepted
- caveat-dropping rejected
- the deterministic renderer passing its own check
- a hallucinating narrator triggering fallback with its output discarded
- a failing provider degrading safely
- the narrator receiving the bundle and the rules

---

Previous: [6. Validation](06-validation.md) · Next: [8. Limitations](08-limitations.md)
