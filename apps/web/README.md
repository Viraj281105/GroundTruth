# GroundTruth frontend

**Status: scaffolded, not implemented.** This directory holds the contract
between the frontend and the API — TypeScript types generated from the same
Pydantic schemas the backend serves — so the UI can be built without
renegotiating the shape of the data.

Planned stack: Next.js (App Router), TypeScript, Tailwind, Recharts.

## Why nothing is built yet

The API and the evidence bundle format are the interface. Building UI before
the bundle stabilised would have meant rewriting it. The bundle is now stable
and versioned (`schema_version`), so the frontend can proceed.

## Planned views

| View | Purpose |
| --- | --- |
| Case browser | Cases with status; makes clear nothing is `analysed` yet |
| Counterfactual chart | Project vs synthetic control over time, gap shaded, treatment date marked |
| Placebo distribution | Histogram of placebo RMSPE ratios with the project highlighted |
| Donor pool | Map and balance table, including every exclusion and its reason |
| Evidence table | Every value with unit, interval and expandable provenance |
| Report | Rendered Markdown with the generator (deterministic or GenAI) labelled |

## Non-negotiable UI rules

1. **The simulated-data banner is unmissable.** Any view showing data from a
   synthetic run displays a persistent banner. It is not dismissible.
2. **No bare numbers.** Every displayed value shows its unit and, where one
   exists, its interval with the interval's `kind`.
3. **Provenance in two clicks.** A reviewer must be able to get from any number
   on screen to its source.
4. **Caveats are not collapsed by default.** The standard caveats render with
   the verdict, not behind a disclosure triangle.
5. **INCONCLUSIVE is styled neutrally.** It is a legitimate outcome, not an
   error state, and must not look like one.
6. **No language that implies wrongdoing**, in copy, in tooltips or in status
   colours. A divergent verdict is amber, never red-as-alarm.

## Getting the API types

The backend serves an OpenAPI schema:

```bash
uvicorn apps.api.main:app --port 8000
curl localhost:8000/openapi.json > frontend/src/lib/openapi.json
```

`src/lib/types.ts` holds the hand-maintained subset until generation is wired
up.
