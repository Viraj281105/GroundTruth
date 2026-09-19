# Testing strategy

**194 tests.** CI runs them on Python 3.11, 3.12 and 3.13, plus a separate
scientific-integrity job.

---

## What we are actually defending against

Most software testing defends against crashes. Here the more dangerous failure
is a **result that is wrong but plausible** — a number that renders fine,
survives review, and is scientifically meaningless. Tests are weighted
accordingly.

| Failure mode | Defence |
| --- | --- |
| Estimator silently wrong | Recovery test on a panel with a known injected effect |
| False positive on a null | Null-panel test asserting no effect is found |
| Non-reproducible output | Same-spec-same-numbers assertion |
| Simulated data presented as real | `data_mode` validation test |
| Index reported as carbon | Parametrised over every index × carbon pair |
| Model inventing a figure | Adversarial grounding suite with fallback assertion |
| Ownership boundary eroding | AST import checks over every module |

## Layers

| Layer | Files | Covers |
| --- | --- | --- |
| Contract | `test_contract_boundary.py` | Import boundaries, versioning, request/result invariants |
| Domain | `test_core.py` | Units, provenance, evidence bundle |
| Method | `test_causal.py`, `test_matching.py`, `test_uncertainty.py` | Estimators, donor eligibility, inference |
| Safety | `test_grounding.py` | The GenAI boundary |
| Integration | `test_pipeline.py` | End to end through the contract |
| Interface | `test_api_cli.py` | HTTP and command line |

## What a good test looks like here

The suite is written as executable specification. Test names state guarantees:

```
test_the_verdict_refuses_to_compare_an_index_against_a_tco2e_claim
test_a_hallucinating_narrator_is_rejected_and_falls_back
test_an_underpowered_donor_pool_is_refused_not_raised
test_simulated_datasets_cannot_be_labelled_observed
```

Name the test after the guarantee, not the method under test. Assert on
behaviour a user would notice. A test named `test_fit_synthetic_control_works`
tells a future reader nothing about what must stay true.

## The tests that matter most

**Recovery.** `test_recovers_a_known_injected_effect` generates a panel from the
exact process synthetic control assumes, injects a known effect, and asserts the
estimator finds it within tolerance. An estimator that cannot do this on clean
data has no business pointing at a real forest.

**Null.** `test_reports_no_effect_when_none_exists`. The other half of
correctness, and the half people forget.

**Grounding fallback.** A narrator that hallucinates a figure and alleges fraud
is rejected, and its invented number does not appear in the published output.
This is the test that makes the architectural claim demonstrable rather than
rhetorical.

**Boundary.** AST checks over every module. If weakened to make an import pass,
the ownership split is gone.

## Running

```bash
pytest                                  # everything, ~90s
pytest tests/test_causal.py -v
pytest -k "placebo"
pytest --cov --cov-report=term-missing
pytest -m "not slow"
```

The suite is slow because placebo inference refits the estimator once per donor.
That is real work, not waste.

## Markers

| Marker | Meaning |
| --- | --- |
| `slow` | Long-running |
| `network` | Requires external APIs — never in the default run |

## Fixtures

`conftest.py` provides seeded panels (`factor_panel` with a known effect,
`null_panel` without), a `bundle` with a verdict, and `kariba_case`. Every
fixture is seeded; a test that depends on unseeded randomness is a bug, not a
flake.

## CI

**`quality`** — ruff, `ruff format --check`, mypy and pytest across three Python
versions.

**`scientific-integrity`** — asserts the claims the README makes. If a
documented guarantee stops holding, the build fails rather than the
documentation quietly becoming a lie.

## Planned

| Layer | Status |
| --- | --- |
| Frontend component tests (Vitest) | Planned |
| API integration tests against a real database | Planned |
| End-to-end (UI → API → worker → store) | Planned |
| Reproducibility replay in CI | Planned |
| Load testing | Future |
