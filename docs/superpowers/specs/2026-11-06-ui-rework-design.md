# UI rework — design spec

Date: 2026-11-06 · Status: draft for review · Scope: `apps/web` only

## 1. Intent

The current UI is one dense, dark, monospace "terminal" page per surface. The case
page alone is a single 1,174-line file. A first-time visitor meets a banner, stat
tiles, a status box and a filter bar before any content. The visual language reads
as generic "AI dashboard".

**Goal:** a premium, calm, multi-page product that explains one idea at a time,
works in proper light and dark themes, and makes the science explorable without
overwhelming. **Success:** a first-time visitor can say what GroundTruth does within
10 seconds, reach a case verdict in two clicks, and run an analysis without reading
documentation; an expert can reach every diagnostic that exists today.

**Non-goals:** no backend changes beyond what is listed in §8; no new analytical
claims; nothing that makes simulated data look real.

## 2. Hard constraints (from `AGENTS.md`)

- **R7** simulated data must be unmistakable. A slim, permanent "Simulated data"
  chip is on every page; it is never dismissible. Banner size shrinks, prominence
  does not.
- **R2** no fraud/legal/certainty language in any UI copy, including the claims
  workbench. Divergence is worded as "warrants accredited review".
- **R3/R5** every number keeps its donor pool, fit, placebo p and assumptions
  reachable; refusals are a first-class, well-designed outcome.
- **R6** no fabricated figures. Anything the API does not return is not shown, or
  is computed from returned data and labelled as such.
- Types come from the generated API client (`src/lib/generated`); no hand-written
  backend shapes. `npm run check:api-types` and `check:fixture-fallback` stay green.
- `contracts/` and verdict logic are untouched.

## 3. Information architecture

| Route | Job | Replaces |
| --- | --- | --- |
| `/` | Story hero, 3-step "how it works", 3 featured cases | `page.tsx` |
| `/cases` | Search, filter, card grid | filter bar on `/` |
| `/cases/[id]` | One-screen overview: verdict, headline number, mini chart, **Run analysis** | top of case page |
| `/cases/[id]/evidence` | Counterfactual chart, donors, placebo, fit | case page sections |
| `/cases/[id]/robustness` | Specification multiverse, DiD cross-check | case page sections |
| `/cases/[id]/method` | Method, assumptions, provenance, signature | `ProvenanceDrawer` |
| `/cases/[id]/report` | Narrative report, citation, PDF export | `NarrativeReport` |
| `/cases/[id]/run` | Stepper: configure → live run → results | inline run panel |
| `/compare` | Side-by-side cases | none |
| `/claims` | Claims workbench | none |
| `/method`, `/status` | How it works + glossary; system health | `/health` |

Case sub-pages are real routes (deep-linkable, back-button friendly) under one
shared layout with a tab bar; the existing scientific components are moved, not
rewritten, wherever their logic is sound.

## 4. Progressive disclosure: three lenses

A persistent control (stored locally, URL-overridable `?lens=`):

- **Story** — plain language, one number, one chart, glossary on hover.
- **Explorer** — interactive evidence (default).
- **Auditor** — full diagnostics, provenance chain, hashes, signature state.

Each component declares which lens reveals which detail. Technical terms resolve
through one glossary module (sourced from `GLOSSARY.md`) so wording is consistent.

## 5. Signature experiences

1. **Scrollytelling hero.** Canvas animation: project line and synthetic twin move
   together then diverge at the intervention year. Uses the simulated fixture and is
   labelled as such. Honors `prefers-reduced-motion` (static frame).
2. **Counterfactual Playground.** Scrub the intervention year and toggle donors; the
   chart updates instantly from results the API already returns (leave-one-out,
   specification curve, placebo). Anything not precomputed triggers a real job via
   the API, with progress shown. **Reproduce in your browser** (Pyodide running the
   deterministic engine) is attempted behind a feature flag; fallback is a server
   re-run. See risk R-1.
3. **Donor Map.** MapLibre view with the case boundary (`/cases/{id}/boundary.geojson`)
   and donor regions shaded by weight; hover shows covariates and contribution.
4. **Live Run Theatre.** Animated stage pipeline driven by `/jobs/{id}/events` (SSE),
   with polling fallback. Refusal renders as an explained outcome, not an error.
5. **Multiverse explorer.** Specification curve as hoverable/filterable points.
6. **Claims Workbench.** Paste/upload text; the backend `claims` module extracts
   stated figures with source spans; each is shown beside the independent estimate in
   neutral wording. Needs an API endpoint (§8).
7. **Trust surfaces.** Signed-evidence badge (verified / unverified / not signed),
   per-evidence deep links, copy-as-citation, shareable evidence cards with generated
   preview images, print/PDF report.

## 6. Visual system

- **Tokens first.** CSS custom properties for color, type, space, radius, shadow,
  motion; semantic names (`--surface-raised`, `--text-muted`), never raw values in
  components. Light and dark are both first-class, `system` default, toggle in the
  header, no flash on load, WCAG AA contrast verified for text and for chart marks.
- **Palette.** Warm neutral base, deep green accent, amber for caution, restrained
  red only for refusal/error. No neon, no gradients-as-decoration beyond a subtle
  ambient background.
- **Type.** Serif display for headlines, Inter for UI text, tabular figures for all
  numbers; no all-caps monospace labels. A real modular scale and an 8-pt spacing
  scale.
- **Surfaces and motion.** Layered soft surfaces, spring-based micro-interactions,
  view-transition page changes, skeleton loaders, toasts. Motion is purposeful and
  fully disabled under reduced-motion.

## 7. UX features

Command palette (`Ctrl/⌘+K`, includes natural-language jumps such as "compare
kariba and mikoko"), keyboard shortcuts with a cheat sheet (`?`), breadcrumbs,
recently viewed, first-run guided tour, empty/error/refusal states with plain-language
copy and a next action, copy-link everywhere, installable PWA with offline demo mode,
English plus Hindi and Marathi (message catalogs; English is source of truth, missing
keys fall back to English).

## 8. Backend touchpoints (small, additive)

- `POST /claims/analyze` — wraps `groundtruth.claims` (extract + compare). New router,
  OpenAPI snapshot and generated types regenerated.
- Verify that existing endpoints expose what the Playground and Multiverse need
  (leave-one-out, spec curve, placebo). If a datum is not returned, the UI does not
  show it; adding it is out of scope unless trivial and agreed.
- No changes to `contracts/`.

## 9. Architecture

Next 14 App Router, TypeScript, CSS Modules on top of the token layer. New
dependencies kept small and lazy-loaded: `cmdk`, `maplibre-gl` (+ `deck.gl` only if
needed), a small motion library, Pyodide loaded on demand. Layout:

```
src/styles/tokens.css, themes.css, base.css
src/components/ds/        design-system primitives (Button, Card, Tabs, Chip, Tooltip, ...)
src/components/shell/     AppShell, Header, ThemeToggle, LensSwitch, CommandPalette, Tour
src/features/<area>/      home, cases, case, run, compare, claims, status
src/lib/                  api client (generated types), glossary, i18n, lens state
```

Existing `scientific/*` components are migrated into `features/case/*` and rethemed
via tokens. Files stay focused (target under ~300 lines each).

## 10. Performance and quality budgets

First load JS under ~200 kB on `/` and `/cases`; map, Pyodide, canvas hero and
palette lazy-loaded; LCP under 2.5 s on a mid-range laptop profile; no layout shift
from theme or fonts (`font-display: swap`, size-adjusted fallbacks). Accessibility:
full keyboard operation, visible focus, ARIA for tabs/dialogs/live regions, axe clean.

## 11. Testing

Existing vitest suite stays green and grows with logic (lens state, glossary,
formatters, i18n fallback). Playwright specs updated for the new routes, run at
desktop and 375 px, light and dark; visual baselines generated after the build.
`check:api-types`, `check:fixture-fallback`, lint, typecheck and `npm run build`
must pass. A scripted browser pass screenshots every route in both themes.

## 12. Delivery plan

1. Design system, tokens, themes, shell, routing skeleton (me, sequential).
2. Parallel agents, one per area, on that base: Home + Cases; Case overview + lenses;
   Evidence + Playground + Map + Multiverse; Run Theatre; Claims + Compare + Status +
   Method. Disjoint folders under `features/`.
3. Integration, polish layer (palette, tour, PWA, i18n), accessibility and visual
   audit, Playwright baselines, CI, push to `viraj`.

## 13. Risks and open questions

- **R-1 Pyodide:** running the engine in-browser needs numpy, pandas and pydantic
  wheels plus the package; cold start is multi-second and heavy. Ship as an opt-in
  "Reproduce" action behind a flag; if it proves impractical, replace with a
  server-side re-run and say so.
- **R-2 Data availability** for instant scrubbing (§5.2) depends on what results
  contain; verified during step 1, scope trimmed honestly if absent.
- **R-3 Scope:** this is large. Order in §12 means each stage is shippable; anything
  unfinished is cut from the end (i18n beyond English, PWA, shareable cards first).
- **R-4 Fonts and licensing:** use open-licensed fonts (self-hosted via `next/font`).
- **R-5 npm advisories** on `next`/`postcss`: upgrade within the 14.x line during
  step 1 where possible; a major upgrade is a separate decision.
