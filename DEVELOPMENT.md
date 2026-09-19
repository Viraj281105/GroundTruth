# Development

Everything needed to get productive. If a step here does not work, that is a
bug in this document — fix it in the same PR.

---

## Setup

Requires Python 3.11+ and git. Nothing else: the full pipeline runs offline with
no credentials, no network and no system libraries.

```bash
git clone https://github.com/Viraj281105/GroundTruth.git
cd GroundTruth
python -m venv .venv
.venv/Scripts/activate            # Windows
source .venv/bin/activate         # macOS / Linux
pip install -e "packages/groundtruth[api,genai,dev]"
cp .env.example .env
```

Verify:

```bash
groundtruth doctor                        # what is configured and what is not
groundtruth verify kariba-redd --synthetic
pytest
```

`groundtruth doctor` is the honest status check. It reports what is genuinely
implemented, including the things that are not.

### Optional extras

| Extra | Adds | Needed for |
| --- | --- | --- |
| `api` | FastAPI, uvicorn | Running the HTTP service |
| `genai` | httpx | Narration providers (not implemented yet) |
| `dev` | pytest, ruff, mypy | Any contribution |
| `geo` | geopandas, rasterio, shapely, xarray | Real raster work (not needed for the causal pipeline) |
| `earthengine` | earthengine-api, geemap | Real Earth-observation access |

The core deliberately avoids SciPy, GDAL and GEOS so the analytical pipeline and
CI run anywhere. Install `geo` only when you are doing raster work.

---

## Daily commands

```bash
make help          # list targets
make check         # lint + typecheck + test, what CI runs
make test          # pytest
make lint          # ruff check
make format        # ruff format + autofix
make typecheck     # mypy
make api           # uvicorn on :8000, docs at /docs
make cli           # demo run on the Kariba case
```

Without `make`:

```bash
ruff format packages tests && ruff check packages tests
mypy
pytest
uvicorn apps.api.main:app --reload --port 8000
```

---

## Repository layout

```
apps/api          thin ASGI entrypoint          apps/web     Next.js frontend
apps/worker       job runner (not built)
packages/groundtruth/src/groundtruth/
  contracts/      shared boundary               engine/      Viraj, pure computation
  platform/       Bhumi, the application
cases/            project definitions as YAML   experiments/ validation harnesses
docs/             the documentation system      tests/       the suite
```

Where new code goes is answered in [`AGENTS.md`](AGENTS.md) §4. The short
version: **methodology belongs to the engine, plumbing belongs to the
platform**, and anything shared is a contract change needing both owners.

---

## The rules that will fail your build

Read [`AGENTS.md`](AGENTS.md) §3 in full. The short list:

1. NDVI is not carbon — no implicit index→carbon conversion
2. Never state or imply fraud
3. Observed change is not causal effect — conditions travel with the number
4. The GenAI layer computes nothing
5. Prefer an honest refusal to a fragile number
6. Never fabricate results — placeholders are marked, not filled
7. Simulated data must be impossible to mistake for real
8. Reproducibility is a requirement — never seed from `hash()`

These are enforced by tests, not by review alone.

---

## Testing

```bash
pytest                                    # everything
pytest tests/test_causal.py -v            # one file
pytest -k "placebo"                       # by keyword
pytest --cov --cov-report=term-missing    # with coverage
pytest -m "not slow"                      # skip slow tests
```

| File | Covers |
| --- | --- |
| `test_contract_boundary.py` | The ownership seam — AST import checks, versioning, request/result invariants |
| `test_core.py` | Units, provenance, evidence bundle |
| `test_causal.py` | Estimator recovery, simplex constraints, DiD diagnostics |
| `test_matching.py` | Donor eligibility, exclusions, balance |
| `test_uncertainty.py` | Placebo inference, leave-one-out, intervals |
| `test_grounding.py` | The GenAI boundary, including hallucination fallback |
| `test_pipeline.py` | End to end through the contract, case registry, observation methodology |
| `test_api_cli.py` | HTTP surface and command line |

**What a good test looks like here.** The suite is deliberately written as
executable specification: `test_the_verdict_refuses_to_compare_an_index_against_a_tco2e_claim`
says what the system guarantees. Name tests after the guarantee, not the method
under test. Assert on behaviour a user would notice.

The most important tests are the ones that would catch a *scientifically wrong*
result, not a crash: effect recovery on a known panel, the null case, refusal
paths, and the grounding rejections.

Markers: `slow` for long-running, `network` for anything requiring external
APIs. Neither runs by default in a quick loop.

---

## Adding things

### A case

One YAML file in `cases/`. See `cases/README.md` and an existing case for the
shape. Do not set `status: analysed` — only a reviewed real run may, and a test
enforces it. A `known_reference` block records a third-party figure for
post-hoc validation; the pipeline never reads it.

```bash
groundtruth cases && groundtruth show <case-id>
```

### An estimator

Add it under `engine/causal/`, register a `model_id`, and make it selectable via
`EstimationSpec`. It must report its own diagnostics — a new estimator that
cannot say when it is unreliable does not go in.

### A data source

Implement the relevant port in `platform/datasets/`. Pin a `DatasetRef` version.
Never fall back to fixtures on failure — raise, so a real-data label can never
cover simulated numbers.

### An evidence item

Add it in `engine/assembler.py` with complete provenance, an id in the right
namespace, a unit from the declared vocabulary, and a qualifier for anything a
reader could misinterpret.

### An API endpoint

`platform/api/`. Validate at the boundary. Map every error to a status code, and
keep refusals distinguishable from malfunctions in the response body.

---

## Debugging

```bash
groundtruth doctor                                  # capability check
groundtruth verify kariba-redd --synthetic --json   # full AnalysisResult
groundtruth --log-level DEBUG verify kariba-redd --synthetic
```

The `--json` output is the complete `AnalysisResult` including provenance,
metrics and per-stage timings — usually faster than a debugger for
"where did this number come from".

`spec_hash` is stable, so two runs that should agree and do not indicate a
genuine nondeterminism bug. That is always worth chasing: reproducibility is a
requirement, not a nicety.

---

## Git

Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `build:`,
`ci:`, `chore:`. Explain *why* in the body, especially for estimator or
grounding changes.

Branch from `main`, open a PR, fill in the template including the scientific
integrity checklist. CI must be green.

A change to `contracts/` requires both owners on the PR and a `CONTRACT_VERSION`
bump.

---

## CI

Two jobs on every push and PR:

**`quality`** — ruff, `ruff format --check`, mypy and pytest on Python 3.11,
3.12 and 3.13.

**`scientific-integrity`** — asserts the claims the README makes: no spectral
index is reported as carbon, the GenAI layer cannot invent numbers or allege
wrongdoing, no case claims an analysed status without a reviewed run, and the
pipeline runs end to end.

The second job exists so that if a claim in the documentation stops being true,
the build fails rather than the documentation quietly becoming a lie.

---

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `ModuleNotFoundError: groundtruth` | Not installed editable. Run the `pip install -e "packages/groundtruth[...]"` line. |
| `unknown case 'kariba-redd'. Available cases: none` | Running from outside the repo. Case discovery walks up for a marker directory. |
| mypy fails on numpy stubs | Checker targets 3.12; the runtime floor is 3.11. Do not lower `python_version` in `[tool.mypy]`. |
| Tests slow (~90s) | Expected. Placebo inference refits the estimator once per donor. |
| `DataUnavailableError` on verify | Correct. Real EO access is not implemented; use `--synthetic`. |
| Verdict is `INCONCLUSIVE` | Usually correct. Read the rationale — it names the gate that failed. |
