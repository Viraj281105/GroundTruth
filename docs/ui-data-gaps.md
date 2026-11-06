# UI data gaps

Places where the UI cannot show something because the API does not return it. The UI says so
instead of computing or inventing values (R6).

## Counterfactual Playground (`src/features/case/playground`)

True live scrubbing needs the API to return, or compute on request:

- **Per-year counterfactual.** The counterfactual path is only served for the engine's own
  intervention year, and only in the demo fixture (`not_served_by_api.counterfactual_path`).
  Moving the intervention year therefore moves the marker and post-period shading only. Showing a
  re-fitted path needs a `POST /runs` variant that accepts `treatment_year` and returns the series.
- **Estimate for an arbitrary year.** Only the engine's `treatment-N-earlier` specifications
  (`robustness.spec_curve.estimate.*`) are shown, when they exist. Later-than-engine years have none.
- **Leave-one-out per donor.** Only the aggregate `robustness.max_absolute_shift` and
  `robustness.sign_stable` are returned. Toggling a donor off cannot show a new estimate; the view
  sums the returned weights of the donors switched off and offers "Re-run with this change".
- **All donor weights.** `fit.donor_weight.N` carries only the largest weights, so the Playground
  lists those donors only.
- **Run parameters.** `/cases/{id}/run?treatment_year=..&exclude_donors=..` is a proposed
  contract. `SubmitJobRequest` has no field for a treatment year or a donor exclusion list yet.

## Evidence page

- The observed/synthetic series, the placebo distribution and the per-candidate donor table are not
  returned by `GET /runs/{id}`; they exist only in the demo fixture. For a stored run the page shows
  an explicit "not served" note and the numeric evidence.
- There is no "latest run for a case" endpoint, so a stored run is opened with `?run=<run_id>`.

## Donor map (`src/features/case/map`)

- `GET /cases/{id}/boundary.geojson` gives the project boundary only. Donor regions are shaded by
  weight only when a feature carries `properties.role = "donor"` and a numeric `properties.weight`;
  no donor geometry exists in the data today, and the map says so.
- Basemap tiles are not requested (no external tile dependency); the map is boundary-only.
- `maplibre-gl` 4.7.1 is declared in `package.json`; until the lockfile is refreshed the map shows a
  text summary (bounding box, centre) instead of a canvas.
