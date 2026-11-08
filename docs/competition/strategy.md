# 9. Competition strategy — PCCOE IGC 2026 (Indradhanu)

| | |
| --- | --- |
| Event | PCCOE International Grand Challenge 2026, Indradhanu, Pune |
| Theme | AI for Climate Change |
| Track | 5 — Biodiversity, Ecosystem Conservation & Climate Awareness |
| Topic | Ecosystem Restoration |
| Submission title | Restoration & Carbon-Credit Causal Impact Verifier |
| Team | Viraj Jadhao (CE, PESMCOE), Bhumi Sirvi (IT, PESMCOE) |

## The thesis

Most entries in an "AI for Climate" track will apply a model to a climate
dataset. This one attacks the **integrity of climate finance itself**, with a
method whose central claim — that before-and-after change is not causal effect —
is both scientifically correct and immediately legible to a non-specialist
judge.

The differentiator is not the model. It is the discipline.

## Six defensible claims

| # | Claim | How it is backed in the repo |
| --- | --- | --- |
| 1 | **Causal, not correlational** | Simplex-constrained synthetic control with placebo inference, not before/after differencing |
| 2 | **Independent** | The developer's claim is an assertion under test; it never enters the counterfactual |
| 3 | **Uncertainty-first** | Intervals labelled by `kind`; add-one permutation p-values; leave-one-out envelopes |
| 4 | **Self-benchmarking** | Kariba provides a published third-party correction to test against |
| 5 | **Scalable** | Cases are YAML; one pipeline runs a registry |
| 6 | **Grounded GenAI** | The narration boundary is *enforced in code and tested*, not promised in a prompt |

## Where AI actually sits

```
raw data → stats/CV/ML engine → verified numbers → GenAI → human report
```

not

```
raw data → LLM guesses the result
```

This is the slide that lands with technical judges, and it is the one this
repository can actually substantiate: `tests/test_grounding.py` demonstrates a
hallucinating narrator being rejected and its output discarded.

## The strongest asset: refusing to over-claim

The pipeline currently returns `INCONCLUSIVE` on Kariba, with the rationale that
an NDVI effect and a tCO2e claim are not commensurable.

That is not a weakness to hide in the demo. It is the single most persuasive
thing the project can show, because it demonstrates:

- the team understands that NDVI is not carbon;
- the gate chain actually fires rather than decorating a pre-determined answer;
- the system refuses rather than producing a plausible number.

Any competitor can show a dashboard with a confident percentage. Very few can
show a system that declines to produce one and explains precisely why.

## Handling hard questions

**"Did you reproduce the 57% figure?"**
No. GroundTruth has not reproduced or contradicted Verra's published figure. Verra's
~57% finding is recorded in `cases/kariba-redd.yaml` as a third-party validation target
and is never an input to the pipeline. An earlier version of this document claimed an
independent 57.04% recovery; the independent audit
(`INDEPENDENT_POST_EXECUTION_AUDIT.md`) showed that number came from a hard-coded NDVI
value back-calculated from the published result, and it has been withdrawn. Converting an
NDVI effect to tCO2e needs a site-calibrated biomass model, and none is shipped, so the
pipeline reports **INCONCLUSIVE / NOT CALIBRATED** for Kariba. The honest position is that
the benchmark is open, and the refusal is the feature.

**"Aren't you accusing projects of fraud?"**
No, and the system is built so it cannot. `VerdictLabel` has no value that reads
as an accusation (`divergent_from_claim` vs `fraud`). Standard caveats are enforced by a
schema validator, and the grounding layer blocks accusatory and legal language in
generated text. Divergence triggers accredited review, not condemnation.

**"Are your numbers synthetic or real?"**
Today every end-to-end run uses **SYNTHETIC** data. The repository ships a precomputed
Kariba benchmark fixture (`data/synthetic_fixtures/kariba_synthetic_benchmark.json`); it
is not satellite data, no Sentinel-2 or Landsat scenes were retrieved to produce it, and
it is labelled `synthetic` in its dataset reference, provenance and every report. The
real-data path (`groundtruth verify <case>` without a synthetic flag) refuses with an
explicit error for every case, because real Earth-observation ingestion is scaffolded but
has not been executed end to end. The platform never substitutes fixtures for real data.

**"Why not just use a neural network on the imagery?"**
Because the question is counterfactual, not predictive. A convolutional net or
vision transformer can tell you what the land cover *is*. It cannot tell you what it
*would have been* in the absence of the carbon project. That requires a causal
identification strategy (Abadie-style synthetic control with placebo inference).

**"How is this different from Global Forest Watch?"**
GFW reports observed forest loss. GroundTruth estimates the difference between
observed change and a matched counterfactual. Observation is the input, not the
conclusion.

## Presentation order

1. The problem — additionality is estimated by the party that profits from it
2. Kariba — a documented, third-party-confirmed case of the gap being large
3. The insight — before/after is not causal; you need a counterfactual
4. The architecture — where AI sits, and where it deliberately does not
5. **Live demo** — including the refusal (see [11. Demo flow](demo-flow.md))
6. What is implemented vs scaffolded, stated plainly
7. The roadmap to a registry-scale triage layer

## Scoring alignment

| Criterion | Evidence |
| --- | --- |
| Innovation | Causal counterfactual verification with an enforced GenAI grounding boundary |
| Technical depth | Simplex-constrained FISTA solver, permutation inference, 163 tests, CI on three Python versions |
| Scientific rigour | Pre-registered validation criteria; documented limitations; the system refuses rather than over-claims |
| Real-world impact | A ~$2–5B market with a documented integrity failure |
| Scalability | Case-as-data; one pipeline per registry |
| Presentation | A working CLI and API, and a report with full provenance |

## Risks

| Risk | Mitigation |
| --- | --- |
| Judges read "no real results" as incomplete | Lead with the correctness of the machinery and the honesty of the refusal; show the recovery test |
| Method fails on Kariba | Pre-registered as a publishable negative result about method limits |
| "This is just statistics, not AI" | The ML/CV pipeline is the analytical engine; the GenAI layer is real, and its grounding boundary is the novel part |
| Over-scoping before Stage 2 | Roadmap is milestone-gated; P0 issues are narrow and shippable |

---

Previous: [8. Limitations](../science/limitations.md) · Next: [10. Roadmap](../product/roadmap-detail.md)
