# Frontend architecture

**Owner: Viraj.** `apps/web/`

**Status: the API contract types exist. No UI is built.**

The evidence bundle format is now stable and versioned, so UI work can proceed
without rewrites. Building views before the bundle settled would have meant
building them twice.

---

## Stack

Next.js (App Router), TypeScript, Tailwind, Recharts for charts, MapLibre for
maps. Types generated from the API OpenAPI schema — **the UI never hand-writes a
backend shape**, which is what keeps it independent of Python internals.

## Views

| View | Purpose | Status |
| --- | --- | --- |
| Case browser | Projects with status; makes clear nothing is `analysed` | Planned |
| Project page | Claim, window, donor region, run history | Planned |
| Counterfactual chart | Project vs synthetic control, gap shaded, treatment date marked | Planned |
| Placebo distribution | Histogram of placebo RMSPE ratios, project highlighted | Planned |
| Map | Project boundary, donor pool, leakage belt, exclusions | Planned |
| Timeline | Crediting period, treatment date, sensor transitions, fire years | Planned |
| Evidence explorer | Every value with unit, interval and provenance drill-down | Planned |
| Report view | Rendered Markdown, generator labelled | Planned |

The counterfactual chart is the centrepiece. It is the one image that makes the
argument — observed versus what comparable regions did — and everything else
supports it.

## Non-negotiable UI rules

These encode the project's scientific commitments into the interface. Helpers
for rules 1, 5 and 6 already exist in `apps/web/src/lib/types.ts`.

1. **The simulated-data banner is persistent and not dismissible** on any view
   showing a simulated run. Driven by `result.is_simulated`, never inferred.
2. **No bare numbers.** Every value shows its unit and, where one exists, its
   interval *with the interval's `kind`*. A sensitivity envelope rendered as a
   confidence interval is a misrepresentation, not a simplification.
3. **Provenance in two clicks** from any number on screen.
4. **Caveats render with the verdict**, never behind a disclosure triangle.
5. **`INCONCLUSIVE` is styled neutrally.** It is a legitimate outcome — often the
   most valuable one — and must not look like an error.
6. **`divergent_from_claim` is amber, never alarm-red.** It means "warrants
   review", not "wrongdoing". No copy, tooltip or colour may imply misconduct.
7. **Refusals are designed states**, not error toasts. They carry the reason and
   the remediation from the structured error.

## Data flow

```
OpenAPI schema ──generate──► TypeScript types ──► typed API client ──► views
```

Regenerating types is part of the API change workflow, not a frontend chore. If
the schema changes and the types are not regenerated, the build should fail.

## Design principles

**Show the uncertainty, do not hide it.** The interval is not a detail to reveal
on hover; it is part of the number.

**Make the counterfactual legible.** A non-specialist should understand "this
line is what actually happened, this line is what comparable places did" without
a statistics background.

**Refusal is a first-class state.** Designed, explained, and visually distinct
from both success and error.

**Accessibility.** Keyboard navigable, charts with text alternatives, and never
colour alone to distinguish observed from counterfactual.
