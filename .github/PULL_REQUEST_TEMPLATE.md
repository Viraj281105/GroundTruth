## What changed

<!-- One paragraph. What does this do and why? -->

## Scientific integrity checklist

- [ ] No spectral index is converted to a carbon quantity
- [ ] No code path can emit text alleging fraud, intent or illegality
- [ ] Every new reported value carries complete `Provenance`
- [ ] Uncertainty is reported with its `kind` (permutation / sensitivity-envelope / analytic)
- [ ] No fabricated results; placeholders are explicitly marked
- [ ] The GenAI layer computes nothing new

## Engineering checklist

- [ ] `ruff format src tests` and `ruff check src tests` pass
- [ ] `mypy` passes
- [ ] `pytest` passes
- [ ] New behaviour has tests
- [ ] Documentation updated if methodology changed
