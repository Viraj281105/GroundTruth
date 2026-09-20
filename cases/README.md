# Case definitions

Each `*.yaml` file here defines one project the pipeline can screen. Cases are
data, not code: adding a project is a pull request against a single file.

| Case | Role | Status |
| --- | --- | --- |
| `kariba-redd` | Primary validation case — benchmarkable against a published correction | scaffolded |
| `southern-cardamom-redd` | Stress case — canopy saturation and persistent cloud | scaffolded |
| `mikoko-pamoja` | Negative control — below the effective resolution of the method | scaffolded |

**No case has been analysed.** `status: scaffolded` means the definition exists
and validates, but no real Earth-observation data has been wired in and no result
has been produced. The status field progresses
`scaffolded` → `data-wired` → `analysed`, and only a reviewed run may set
`analysed`.

## The `known_reference` block

Several cases carry a `known_reference` block recording a published third-party
finding. **The pipeline never reads it.** It exists so the validation harness in
`experiments/` can compare an independent estimate against it *after* that
estimate has been produced. Feeding it forward would destroy the independence
that is the entire point of the system.

## Boundaries

Boundaries must come from the registry record, not be redrawn by hand: a
hand-drawn boundary changes the estimate and cannot be audited.

`kariba-redd` has one, taken from Verra's approved boundary document for VCS
902 and committed with its source file and a provenance record. Its area does
not reconcile with the registry's own area field, which is recorded as a
finding in the case notes rather than corrected. The other two cases have no
boundary yet. See [boundaries/README.md](boundaries/README.md).
