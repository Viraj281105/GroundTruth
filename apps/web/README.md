# GroundTruth frontend

This directory holds the UI and the contract between it and the API: TypeScript
types generated from the same Pydantic schemas the backend serves (see "The API
types are generated" below), so the UI is built without renegotiating the shape of
the data.

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

## The API types are generated

The UI never hand-writes a backend shape. The types come from the API's OpenAPI
schema:

| File | What it is |
| --- | --- |
| `src/lib/generated/openapi.json` | The schema, exactly as `/openapi.json` serves it. Committed. |
| `src/lib/generated/schema.d.ts` | TypeScript generated from it by `openapi-typescript`. Committed; do not edit. |
| `src/lib/types.ts` | The familiar names (`Evidence`, `VerificationResponse`, ...) as aliases of the generated types, plus UI-only helpers. |
| `src/lib/api-client.ts` | A typed `fetch` client (`openapi-fetch`) for the `/runs` and `/jobs` endpoints. Transport only: no demo fallback. |

**After changing any API schema or route, regenerate and commit both files:**

```bash
make api-types
# or, step by step, without make (Windows):
python apps/web/scripts/export_openapi.py      # 1. the schema; needs no server and no database
cd apps/web && npm run generate:api            # 2. the TypeScript
```

If you forget, CI fails: `tests/test_openapi_snapshot.py` (Python job) when the
schema is stale, and `npm run check:api-types` (web job, and `npm run build` via
`prebuild`) when the TypeScript is stale or was edited by hand.

Two details of the schema, both deliberate:

- Every field of a **response** is typed as always present, because FastAPI always
  sends it. Request fields with defaults stay optional.
- `openapi-typescript` is pinned to an exact version, because a different version
  would generate different output and fail the check.

## Demo fixtures are engine output

`src/lib/fixtures/generated/*.json` is written by running the real engine on
the synthetic fixture provider. Do not hand-edit it; regenerate after any
engine change and commit the result:

```bash
.venv/Scripts/python apps/web/scripts/generate_fixtures.py
```

Every file is SIMULATED DATA and carries that marker. Sections under
`not_served_by_api` (counterfactual path, per-candidate donor table, placebo
distribution, refusal detail) are engine intermediates the API does not
return yet. UI code must keep working when they are absent.
