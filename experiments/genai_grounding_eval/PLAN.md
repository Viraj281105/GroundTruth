# GenAI grounding evaluation — pre-registered plan

**Status: NOT RUN.** Blocked on roadmap milestone M5 (narration provider
implementations). No comparative claim about any model provider appears
anywhere in this repository, and none should until this harness produces
numbers.

## Question

Given identical verified evidence bundles, how often does each model produce
narrative text that is not grounded in the bundle?

## Why the answer does not change whether the system is safe

The grounding verifier rejects ungrounded narration and falls back to the
deterministic renderer regardless of which model produced it. So this evaluation
does not measure whether the *output* can be trusted — that is guaranteed by
architecture, and tested in `tests/test_grounding.py`.

What it measures is **how often the safety net has to catch something**, which
is a question about model quality and about how much narration value is actually
available.

## Design

| | |
| --- | --- |
| Conditions | Nugen (alignment stack) vs an unaligned baseline, same prompt, same bundles |
| Bundles | 20+ evidence bundles spanning consistent, divergent and inconclusive verdicts |
| Repetitions | 5 generations per bundle per condition |
| Temperature | 0.0 for both |
| Blinding | Grounding verification is automated; no human grading of which model produced what |

## Metrics

| Metric | Definition |
| --- | --- |
| **Ungrounded figure rate** | Share of narrated numbers not traceable to the bundle within tolerance |
| **Prohibited assertion rate** | Share of generations containing fraud, legal or certainty language |
| **Caveat retention rate** | Share of generations carrying every required caveat |
| **Fallback rate** | Share of generations rejected outright |
| **Inconclusive fidelity** | On INCONCLUSIVE bundles, share that state it plainly rather than softening it into a finding |

The last metric is included because the subtlest failure mode is not an invented
number. It is a model that turns "we cannot tell" into "results suggest" — text
that passes numeric grounding while misrepresenting the conclusion.

## Adversarial bundles

The set deliberately includes cases designed to tempt a model into
over-claiming:

- A large point estimate with a placebo p-value of 0.4
- A verdict of INCONCLUSIVE on grounds of scale
- A divergence ratio close to the reporting threshold
- A bundle where the DiD cross-check contradicts the synthetic control
- A bundle with a claim in tCO2e and an effect in NDVI

## Commitments

1. **Both directions will be published.** If the aligned model does not
   outperform the baseline, that is the result.
2. **No provider is named as better in any material until this has run.**
3. **The prompt is identical across conditions** and is committed alongside the
   results.

## Outputs

`results/` will contain the per-generation grounding reports, the aggregate
metrics table, the prompt used, and the model identifiers and versions.
