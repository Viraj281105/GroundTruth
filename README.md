# GroundTruth

**Independent causal verification for climate restoration and carbon-credit claims**

[![CI](https://github.com/Viraj281105/GroundTruth/actions/workflows/ci.yml/badge.svg)](https://github.com/Viraj281105/GroundTruth/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> PCCOE International Grand Challenge 2026 · Indradhanu · Theme: AI for Climate
> Change · Track 5: Biodiversity, Ecosystem Conservation & Climate Awareness
>
> Submission title: *Restoration & Carbon-Credit Causal Impact Verifier*
> Team: Viraj Jadhao, Bhumi Sirvi

---

## The problem

Voluntary carbon markets sell **additionality**: the climate benefit that exists
*because* a project happened and would not have existed otherwise. That is a
counterfactual quantity — it describes a world that never occurred — so it must
be estimated.

Today it is estimated largely by the project developer, using a baseline the
developer proposes. The party with the strongest financial interest in a high
number produces the number.

The gap this creates is not hypothetical. Following a two-year investigation
concluded in 2025, the registry Verra found that a reported **57% of the ~27
million credits issued by the Kariba REDD+ project** (Zimbabwe, 785,000 ha) were
in excess of the emission reductions actually achieved.

*That figure is Verra's, not ours. It is why Kariba is our benchmark: it is one
of the few projects where an independent method can be checked against a
published third-party correction.*

## The insight

**Before-and-after satellite comparison is not verification.**

```
naive:   effect = indicator_after − indicator_before
```

This absorbs every regional trend — rainfall cycles, commodity prices, road
building, conflict — into the estimate. A project in a region where
deforestation slowed for unrelated reasons looks successful.

```
GroundTruth:  effect = indicator_project − indicator_synthetic_counterfactual
```

The counterfactual is built from regions that are comparable on rainfall,
elevation, slope, road access and settlement pressure, and were not subject to
the intervention. If a weighted combination of them tracks the project for a
decade *before* the intervention, their later path is a defensible estimate of
what the project area would have done.

## Where AI sits — and where it deliberately does not

```
NOT THIS:   raw satellite data  →  LLM  →  "this project over-issued 57%"

THIS:       raw data → stats/CV/ML engine → verified evidence bundle
                                                    ↓
                                        LLM narrates the bundle
                                                    ↓
                                          grounding verifier
                                                    ↓
                                pass → publish    fail → deterministic report
```

The language model is downstream of every number. It explains; it never
computes, estimates or concludes.

**And this is enforced, not promised.** Every number in generated prose is
checked back against the evidence bundle. Text alleging fraud, asserting a legal
conclusion, claiming something is proven, or converting a vegetation index into
carbon is rejected. On any failure the deterministic report is published
instead. The system degrades to *correct and dry*, never to *fluent and wrong*.

`tests/test_grounding.py` demonstrates a hallucinating narrator being rejected
and its invented figure discarded.

## Three rules the system will not break

**1. NDVI is not carbon.** A spectral index is a reflectance ratio; carbon is a
mass. `contracts.units.assert_not_index_to_carbon` raises on any implicit conversion,
and a parametrised test asserts it for every index/carbon pair.

**2. Observed change is not causal effect.** Every estimate carries its donor
pool, its pre-treatment fit quality, its placebo p-value and its identifying
assumptions.

**3. Model divergence is not fraud.** A gap between an independent estimate and
a developer's claim means the claim *warrants accredited review*. No verdict
label reads as an accusation, and the grounding layer blocks text that would
supply one.

---

## Quick start

```bash
git clone https://github.com/Viraj281105/GroundTruth.git
cd GroundTruth
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -e "packages/groundtruth[api,genai,dev]"
```

No credentials and no network needed — the full pipeline runs offline.

```bash
groundtruth doctor                        # what is configured and what is not
groundtruth cases                         # list case definitions
groundtruth show kariba-redd              # inspect one case
groundtruth verify kariba-redd --synthetic
```

Run the API:

```bash
uvicorn apps.api.main:app --reload --port 8000
# http://localhost:8000/docs
```

Run the checks:

```bash
pytest          # 194 tests
ruff check packages tests
mypy
```

## What a run actually produces

`groundtruth verify kariba-redd --synthetic` prints a simulated-data banner,
then a report whose verdict is:

> **Outcome: Inconclusive** — A robust incremental effect on the observed
> indicator was estimated, but the developer's claim is not expressed in
> commensurable units, so no comparison against the claim can be made without a
> biomass conversion step.

**That refusal is the point.** The pipeline passed every robustness gate — donor
count, pre-treatment fit, placebo distinguishability, leave-one-out sign
stability, covariate balance — and still declines to score the claim, because
the effect is in NDVI and the claim is in tonnes of CO₂. Those are not the same
kind of quantity. Building the bridge needs a biomass model with its own error
budget, which is the next milestone.

A system that multiplies by something and returns a confident percentage is
easier to demo. It is also wrong.

---

## Architecture

```
┌──────────────────── DETERMINISTIC ENGINE — no LLM runs here ────────────────┐
│ ingestion → geospatial → matching → causal → uncertainty → evidence         │
│ every value carries Provenance: source, method, parameters, derived-from     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
                          EvidenceBundle (immutable, versioned)
                                      ↓
┌──────────────────── REPORTING — the only place a model may run ─────────────┐
│ deterministic renderer  ──or──  GenAI narration → grounding check → fallback │
└─────────────────────────────────────────────────────────────────────────────┘
```

```
apps/
  api/            thin ASGI entrypoint                    Bhumi  [implemented]
  worker/         background job runner                   Bhumi  [not built]
  web/            Next.js frontend                        Viraj  [types only]

packages/groundtruth/src/groundtruth/
  contracts/      the shared, versioned boundary          shared [implemented]
  engine/         observation, matching, causal,          Viraj  [implemented]
                  uncertainty, evidence assembly
  platform/       api, cases, datasets, jobs, store,      Bhumi  [partial]
                  storage, reports, config

cases/  data/  docs/  experiments/  infrastructure/  tests/
```

Two people own this, ~60/40. The split is enforced architecturally, not by
convention: `tests/test_contract_boundary.py` parses the AST of every module and
fails the build if the platform reaches into the engine, if the engine performs
I/O, or if the contract depends on either side. See
[`OWNERSHIP.md`](OWNERSHIP.md).

## Scientific method

**Synthetic control.** Donor weights minimise pre-treatment discrepancy subject
to $w_j \ge 0$ and $\sum_j w_j = 1$. The simplex constraint forbids
extrapolation outside the convex hull of observed donors, so the counterfactual
is always an attainable combination of real places. Solved with FISTA on numpy
alone — no SciPy, no CVXPY.

**Permutation inference.** With one treated unit there is no sampling
distribution. Each donor is refit as a placebo, and the project's post/pre RMSPE
ratio is ranked within that distribution. The Phipson–Smyth add-one correction
means a p-value is never reported as zero: with 40 donors the smallest
attainable value is 0.024, and the system says so.

**Explicit gate chain.** The verdict is decided by rules, not by a model:
enough donors → good pre-treatment fit → placebo distinguishability →
leave-one-out sign stability → covariate balance. **Any failed gate
short-circuits to `INCONCLUSIVE`.** There is no weak-positive path.

**Honest refusal over fragile numbers.** `DonorPoolError`,
`InsufficientDataError` and the `INCONCLUSIVE` verdict are features. A
due-diligence team is better served by "we cannot tell" than by an estimate
built on six donors.

Full detail: [docs/science/causal-inference.md](docs/science/causal-inference.md).

## Cases

| Case | Role |
| --- | --- |
| [`kariba-redd`](cases/kariba-redd.yaml) | Primary benchmark — the only case with a published third-party correction |
| [`southern-cardamom-redd`](cases/southern-cardamom-redd.yaml) | Stress case — NDVI saturation and persistent cloud (uses EVI) |
| [`mikoko-pamoja`](cases/mikoko-pamoja.yaml) | **Negative control on the method** — at ~117 ha it is below what a 30 m annual composite can resolve, so `INCONCLUSIVE` is the correct answer |

Cases are data, not code. Each carries a `known_reference` block recording
published third-party findings — **which the pipeline never reads.** They exist
so the validation harness can compare *after* an independent estimate exists.

---

## Status: implemented vs scaffolded

**No analysis of any real project has been run.** Every number the pipeline
currently produces comes from a simulated fixture, and says so in its
provenance, its run warnings, its verdict caveats and a banner on stderr.

| Implemented and tested | Scaffolded / not built |
| --- | --- |
| Domain model, provenance, evidence bundle | Earth Engine observation calls |
| Unit vocabulary with the index→carbon guard | Real covariate extraction (CHIRPS/SRTM/OSM/WorldPop) |
| Spectral indices, SCL masking, zonal stats | Project boundary geometry |
| Donor matching with exclusion accounting | Biomass / carbon conversion (deliberately deferred) |
| Synthetic control solver and diagnostics | GenAI narration providers |
| DiD cross-check with pre-trend diagnostic | Frontend (API contract types only) |
| Placebo inference, leave-one-out, spec curve | Persistence layer |
| Evidence assembly and verdict gate chain | Kariba benchmark run |
| Deterministic renderer | Nugen vs baseline evaluation |
| Grounding verifier and safe fallback | |
| Pipeline, CLI, API | |
| Synthetic fixture provider (labelled) | |

Anything not implemented raises rather than guessing.
`POST /cases/{id}/verify` with `synthetic: false` returns **501**, not simulated
numbers under a real-data label.

## Tests and CI

194 tests. CI runs ruff, `ruff format --check`, mypy and pytest on Python 3.11,
3.12 and 3.13.

A second CI job asserts the claims this README makes: no spectral index is
reported as carbon, the GenAI layer cannot invent numbers or allege wrongdoing,
no case claims an analysed status without a reviewed run, and the pipeline runs
end to end. If a claim here stops being true, the build fails rather than the
README quietly becoming a lie.

## Documentation

| Start here | |
| --- | --- |
| [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) | Why this exists, who it is for, what it must never claim |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | The load-bearing decision and the system map |
| [`AGENTS.md`](AGENTS.md) | Operating instructions for developers and AI agents |
| [`DEVELOPMENT.md`](DEVELOPMENT.md) | Setup, commands, testing, troubleshooting |
| [`ROADMAP.md`](ROADMAP.md) | NOW to MVP to Stage 2 to Stage 3 to long term |
| [`OWNERSHIP.md`](OWNERSHIP.md) | Who owns what, and the definition of done |
| [`GLOSSARY.md`](GLOSSARY.md) | Terms that mean something specific here |

| Deeper | |
| --- | --- |
| [docs/architecture/contract.md](docs/architecture/contract.md) | The engine/platform contract, in full |
| [docs/science/causal-inference.md](docs/science/causal-inference.md) | The estimator, its assumptions, why NDVI is not carbon |
| [docs/architecture/genai.md](docs/architecture/genai.md) | How the narration boundary is enforced |
| [docs/science/limitations.md](docs/science/limitations.md) | What is not built and where this could be wrong |
| [docs/product/capability-matrix.md](docs/product/capability-matrix.md) | Implemented / planned / future, per capability |
| [docs/decisions/](docs/decisions/) | Ten ADRs on why the architecture is the way it is |
| [docs/](docs/) | Full index |

## What this is not

- **Not a fraud detector.** Divergence triggers review; it does not establish
  intent, and nothing in a satellite time series could.
- **Not a replacement for accredited field auditing.** Ground plots measure
  carbon pools no satellite can see.
- **Not a carbon accounting system.** It does not issue, retire or price
  credits.
- **Not a basis for enforcement.** No project should lose status on this output
  alone.

It is a **screening and decision-support system**: a way to decide which claims
deserve a closer, expensive, accredited look.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The non-negotiable rules are there —
they are what makes the output defensible, not style preferences.

## License

MIT — see [LICENSE](LICENSE).

---

> *Let evidence, not claims, drive climate finance.*
