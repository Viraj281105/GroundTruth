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

## Run states from the stored-run API

`GET /runs` and `GET /runs/{run_id}` (#35) send a `result_state` so the UI derives
nothing. It uses the existing `ResultState` values `running`, `measured`, `refused` and
`failed`, and adds two the UI does not have yet:

| New value | Meaning | Suggested rendering |
| --- | --- | --- |
| `queued` | Recorded, not yet picked up by a worker | The `running` style; it is waiting, not failing |
| `cancelled` | Cancelled before it produced evidence | Neutral, like `not_started`; not an error |

A stored refusal is a normal `200` response with `result_state: "refused"` and the full
structured `error` (including `detail`), so the refusal view can be driven from it. Every
run carries `is_simulated`; the persistent banner is driven by that field and by
`contains_simulated` on a page or a comparison, never inferred. A comparison with
`comparable: false` has no diff by design: render its `not_comparable` reasons, not a
table of changes.

### Watching a job

`POST /jobs` returns at once with a `status_url`; poll `GET /jobs/{run_id}` about once a
second until `terminal` is true. The response carries `stages` (claim, data, engine,
record) with a state each, so the UI can show where a job is. It deliberately has **no
percentage**: the engine is one uninterruptible step, so while it runs the UI gets
`elapsed_ms` (time spent) and nothing about how much is left. Do not synthesise a
progress bar from it. The engine's own per-stage timings arrive in `engine_metrics` after
it finishes, for completed analyses only. A refusal is `result_state: "refused"` with
every stage `done`, and renders as the refusal state, not an error. Cancelling a running
job returns `202` and `cancel_requested: true`; keep polling until `terminal`, because the
engine cannot be interrupted and the cancel completes when it returns.

## Data flow

```
OpenAPI schema ──generate──► TypeScript types ──► typed API client ──► views
```

Regenerating types is part of the API change workflow, not a frontend chore:
`make api-types` after any API schema or route change (see `apps/web/README.md`).
If the schema changes and the types are not regenerated, CI fails, and so does
`npm run build`.

`src/lib/types.ts` keeps its old names as aliases of the generated types, plus
UI-only helpers. These are the places where the UI and the API still differ, kept
visible rather than papered over:

| Where | UI | API | Note |
| --- | --- | --- | --- |
| `Confidence.kind` | `ConfidenceKind`, four values | `string` | The contract types it as a free string. Narrowing it is a `contracts/` change. Components only compare it to strings, so they are unaffected. |
| `VerificationResponse` identity fields | were optional | always present | `run_id`, `spec_hash`, `engine_version`, `contract_version`, `duration_ms`. The UI is now stricter, which is safe. |
| `ResultState` | `not_started`, `running`, `measured`, `refused`, `failed` | `result_state` adds `queued`, `cancelled` | See "Run states" above. |
| Donor ADR-011 types (`DonorExclusionCategory`, `DonorLadderRung`, `DonorCandidateSummary`) | hand-copied from `platform.units.rules` | not served by any endpoint | Generation cannot protect them; a change in Python would go unnoticed. |

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
