# Experiments

Validation and evaluation harnesses. Each subdirectory holds a runnable script,
its pre-registered criteria, and a `results/` directory that is empty until the
experiment has actually been run.

| Experiment | Question | Status |
| --- | --- | --- |
| `estimator_recovery/` | Does the estimator recover a known effect? | **Run** — see the test suite |
| `kariba_benchmark/` | Does an independent estimate agree with the published correction? | **Not run** — blocked on M1/M2 |
| `genai_grounding_eval/` | How often does each model produce ungrounded text? | **Not run** — blocked on M5 |
| `specification_curve/` | Does the sign survive alternative specifications? | **Not run** — blocked on M3 |

## Rules

1. **Pre-register the criteria.** Write down what counts as success before
   running anything. A method tuned until it reproduces a known answer has
   proved only that it can be tuned.
2. **Commit negative results.** A failed benchmark is a finding about the limits
   of satellite-based causal screening. Suppressing it would make every other
   claim in this repository worthless.
3. **Never commit a fabricated result.** `results/` stays empty until real
   output exists.
4. **Record the environment.** Seed, package version, git SHA and data
   retrieval date go in every result file.
