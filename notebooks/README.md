# notebooks

Exploratory analysis. **Owner: Viraj** for scientific exploration.

Rules:

1. **Notebooks are exploration, never a source of truth.** Anything that
   produces a reported number must live in `packages/groundtruth/` with tests.
2. **No notebook output is committed.** Clear outputs before committing, so
   diffs stay readable and stale results are not mistaken for current ones.
3. **A notebook that matters gets promoted.** If an analysis is worth repeating,
   move it to `experiments/` with a pre-registered plan.

See [`docs/engineering/testing.md`](../docs/engineering/testing.md).
