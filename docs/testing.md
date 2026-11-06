# Testing

## Python

    PYTHONPATH=packages/groundtruth/src python -m pytest tests

- `tests/properties/` holds Hypothesis property tests (skipped if `hypothesis` is not installed).
- `tests/test_golden_reproducibility.py` compares the Kariba synthetic run with
  `tests/golden/kariba_synthetic.json`. Floats are rounded to 6 decimals; run ids, timestamps and
  metrics are ignored. To regenerate intentionally: `GROUNDTRUTH_UPDATE_GOLDEN=1 pytest
  tests/test_golden_reproducibility.py`, then review the diff.

## Mutation testing

mutmut is not configured in `pyproject.toml`. Run ad hoc:

    pip install mutmut
    mutmut run --paths-to-mutate packages/groundtruth/src/groundtruth/engine \
      --tests-dir tests --runner "python -m pytest -x -q tests"
    mutmut results

Surviving mutants point at behaviour no test pins down.

## End-to-end (Playwright)

From `apps/web`:

    npm install
    npx playwright install chromium
    npm run dev          # in another terminal, serves http://localhost:3000
    npm run test:e2e

Projects: `chromium` (desktop) and `phone` (375px). Visual specs use `toHaveScreenshot`; create
or update baselines with `npm run test:e2e -- --update-snapshots` and review the images.
