# Contributing to GroundTruth

## Setup

```bash
git clone https://github.com/Viraj281105/GroundTruth.git
cd GroundTruth
python -m venv .venv
.venv/Scripts/activate        # Windows; use source .venv/bin/activate elsewhere
pip install -e "packages/groundtruth[api,genai,dev]"
cp .env.example .env
```

Verify the install:

```bash
groundtruth doctor
pytest
```

## Before you open a pull request

```bash
ruff format packages tests
ruff check packages tests
mypy
pytest
```

CI runs all four on Python 3.11, 3.12 and 3.13.

## Non-negotiable rules

These are not style preferences. They are what makes the output defensible, and
a pull request that breaks one will be rejected regardless of how well it works.

**1. Never convert a spectral index into carbon.**
NDVI, EVI and NBR are reflectance ratios. Carbon is a mass stock. Any mapping
between them requires an allometric or biomass model with its own error budget
and its own provenance record. `groundtruth.contracts.units` enforces this; do not
route around it.

**2. Never state or imply fraud.**
A divergence between an independent estimate and a developer's claim means the
claim warrants accredited review. GroundTruth has no standing to find
wrongdoing, and no code path may produce text that says otherwise.

**3. Observed change is not causal effect.**
Every estimate is conditional on the donor pool, the pre-treatment fit and the
identifying assumptions of its estimator. Those conditions travel with the
number, in its provenance and its qualifiers.

**4. The GenAI layer may not compute anything.**
The reporting layer receives a finished `EvidenceBundle` and narrates it. If you
find yourself wanting a model to calculate, derive, annualise or convert
something, that work belongs upstream in the deterministic pipeline.

**5. Prefer an honest refusal to a fragile number.**
`InsufficientDataError`, `DonorPoolError` and the `INCONCLUSIVE` verdict are
features. A due-diligence team is better served by "we cannot tell" than by a
point estimate built on six donors.

**6. Never fabricate results.**
No committed number may describe a real project unless it was actually computed
from real data by code in this repository. Placeholders are marked
`NOT IMPLEMENTED`, `NOT YET OBTAINED` or `SIMULATED DATA`, never filled with a
plausible-looking value.

## Adding a case

Add one YAML file to `cases/`. See `cases/README.md`. A `known_reference` block
records a published third-party finding for post-hoc validation only — the
pipeline must never read it.

Do not set `status: analysed` unless a real run has been produced and reviewed.
A test enforces this.

## Commit messages

Conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `build:`,
`ci:`, `chore:`. Explain *why* in the body, especially for anything touching the
estimators or the grounding rules.

## Project layout

| Path | Contents |
| --- | --- |
| `apps/api`, `apps/worker`, `apps/web` | Deployable entrypoints |
| `packages/groundtruth/src/groundtruth/contracts/` | The shared, versioned boundary |
| `packages/groundtruth/src/groundtruth/engine/` | Analytical engine (Viraj) |
| `packages/groundtruth/src/groundtruth/platform/` | The application (Bhumi) |
| `cases/` | Case definitions |
| `experiments/` | Validation and evaluation harnesses |
| `docs/` | The documentation system |
| `tests/` | The suite, including boundary enforcement |

Where new code goes is answered in [`AGENTS.md`](AGENTS.md) §4. Read
[`DEVELOPMENT.md`](DEVELOPMENT.md) for setup and [`OWNERSHIP.md`](OWNERSHIP.md)
for who owns what.
