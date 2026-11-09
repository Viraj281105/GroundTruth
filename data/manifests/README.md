# Unit-set manifests

Committed artifacts, unlike the rest of `data/`. Each `<case>-unit-set.json` here is a
generated ADR-011 unit set, pinned as a `DatasetRef` so it enters a request's
`spec_hash`. It records the boundary, every input with its reference period, every
threshold and parameter as executed, the leakage-belt hash, the counts at every rung
climbed, every unit, and the rule that excluded each district.

**There is no manifest here yet: no real unit set has been generated.** One appears only
from a real run, never by hand:

```powershell
python experiments/kariba_benchmark/generate_unit_set.py --write
```

The script refuses until every required setting in `cases/run_parameters/` is decided.
Review a new manifest with both owners before committing it (C7). See
[ADR-011](../../docs/decisions/ADR-011-unit-of-analysis.md), "Reproducibility
requirements".
