# GroundTruth documentation

Read in order for the full argument, or jump to what you need.

| # | Document | What it answers |
| --- | --- | --- |
| 1 | [Problem](01-problem.md) | Why unverified climate claims are a real and measurable problem |
| 2 | [Methodology](02-methodology.md) | How a counterfactual is constructed, stage by stage |
| 3 | [Architecture](03-architecture.md) | How the code is organised and why the boundaries fall where they do |
| 4 | [Data sources](04-data-sources.md) | Which products, which assets, and what each one cannot tell you |
| 5 | [Causal inference](05-causal-inference.md) | The estimator, its assumptions, and why NDVI is not carbon |
| 6 | [Validation](06-validation.md) | The pre-registered plan for testing the method against Kariba |
| 7 | [GenAI grounding](07-genai-grounding.md) | How "the model explains, it never invents" is enforced |
| 8 | [Limitations](08-limitations.md) | What is not built, what could be wrong, and what this must never be used for |
| 9 | [Competition strategy](09-competition-strategy.md) | The PCCOE IGC 2026 positioning |
| 10 | [Roadmap](10-roadmap.md) | Milestones with checkable exit criteria |
| 11 | [Demo flow](11-demo-flow.md) | A seven-minute live demo that runs today |

## If you only read three

- **[5. Causal inference](05-causal-inference.md)** — the scientific core, and
  the section on why a vegetation index is not a carbon stock.
- **[7. GenAI grounding](07-genai-grounding.md)** — the architectural claim that
  most distinguishes this project, and how it is made enforceable.
- **[8. Limitations](08-limitations.md)** — what has not been built and where
  the method could be wrong.

## Three rules that recur

1. **Observed change is not causal effect.** Everything in the pipeline exists
   to close that gap honestly, and to state what is left open.
2. **NDVI is not carbon.** A spectral index is a reflectance ratio. Converting
   it to a mass requires a biomass model with its own error budget, and the code
   refuses to do it implicitly.
3. **Model divergence is not fraud.** A gap between an independent estimate and
   a developer's claim means the claim warrants accredited review. Nothing in a
   satellite time series can establish intent.

## Status

Nothing in this repository contains an analysis of a real project. Every number
the pipeline currently produces comes from a simulated fixture and is labelled
as such in its provenance, its warnings and its verdict caveats. See
[8. Limitations](08-limitations.md) for the full implemented-versus-scaffolded
table.
