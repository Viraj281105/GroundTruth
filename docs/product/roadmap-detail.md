# 10. Roadmap

Milestone-gated. Each milestone has an exit criterion that can be checked, not
a vibe.

## M0 — Foundation ✅ complete

Core domain model, provenance and evidence objects; donor matching; synthetic
control with placebo inference and robustness checks; evidence assembly with the
verdict gate chain; deterministic reporting with an enforced grounding boundary;
CLI and API; three case definitions; 163 tests; CI on Python 3.11–3.13.

**Exit criterion met:** the pipeline runs end to end on the synthetic fixture,
recovers a known injected effect, and refuses to compare an index effect against
a tCO2e claim.

## M1 — Real observation data (P0)

Make the pipeline see real forests.

- [ ] Earth Engine service-account authentication
- [ ] Sentinel-2 SCL-masked annual median composites
- [ ] Landsat 5/7/8 composites for long pre-periods
- [ ] `reduceRegion` returning value **and** clear-observation count per period
- [ ] Landsat↔Sentinel cross-calibration with the transform in provenance
- [ ] Obtain and validate registry boundary geometry for all three cases
- [ ] Inward boundary buffering with its caveat recorded
- [ ] Integration tests behind the `network` marker

**Exit:** `groundtruth verify kariba-redd` runs on real Sentinel-2 and Landsat
data and produces an NDVI series with honest coverage accounting.

## M2 — Real donor pools (P0)

- [ ] Candidate region generation over an ecoregion-constrained search area
- [ ] CHIRPS rainfall, SRTM elevation and slope
- [ ] OSM-derived road-distance raster
- [ ] WorldPop population density
- [ ] WDPA protected-area exclusion
- [ ] Leakage-belt geometry (10 km default) and donor exclusion
- [ ] Balance diagnostics on a real pool

**Exit:** a Kariba donor pool with worst covariate SMD ≤ 0.25 and every
exclusion carrying a reason.

## M3 — First real estimate (P0)

- [ ] Full pipeline on Kariba with real data
- [ ] Placebo distribution over real donors
- [ ] Specification curve across NDVI, EVI and forest-area indicators
- [ ] Sensor-transition sensitivity check
- [ ] Internal review before `status: analysed` is set

**Exit:** a reviewed evidence bundle for Kariba, with a result reported whatever
it says.

## M4 — Biomass and carbon conversion (P1)

The step that makes claims commensurable. Deliberately after M3, because a
conversion layer on top of an unvalidated indicator estimate compounds two
uncertainties.

- [ ] ESA CCI Biomass and/or GEDI L4B above-ground biomass density
- [ ] Index → biomass relationship fitted with its own error budget
- [ ] Carbon fraction and CO2-equivalent conversion with propagated error
- [ ] `assert_not_index_to_carbon` routed through the explicit conversion step
- [ ] Wide, honest intervals — the deliverable, not a problem

**Exit:** a Kariba estimate in tCO2e with a propagated interval, comparable to a
registry figure.

## M5 — GenAI narration (P1)

- [ ] Nugen client implementation
- [ ] OpenAI client as the unaligned baseline
- [ ] Run the hallucination evaluation harness
- [ ] Report ungrounded-figure, prohibited-assertion, caveat-retention and
      fallback rates
- [ ] Publish the comparison, whichever way it goes

**Exit:** measured grounding rates for both providers on identical bundles.

## M6 — Frontend (P1)

- [ ] Case browser
- [ ] Project-vs-synthetic-counterfactual time-series chart with the gap shaded
- [ ] Placebo distribution plot with the project highlighted
- [ ] Donor pool map and balance table
- [ ] Evidence table with provenance expansion per row
- [ ] Prominent, unmissable simulated-data banner

**Exit:** a reviewer can trace any number on screen back to its source in two
clicks.

## M7 — Scale (P2)

- [ ] Batch runs across a registry slice
- [ ] PostgreSQL + PostGIS persistence
- [ ] Result caching and incremental re-runs
- [ ] Portfolio-level triage ranking
- [ ] Public methodology note

**Exit:** 50+ projects screened in one batch with per-project provenance.

## Priorities

**P0 — blocking a real result.** M1, M2, M3. Without these the system is
machinery without an application.

**P1 — completes the story.** M4 makes claims comparable. M5 substantiates the
GenAI claim with measurements. M6 makes it demonstrable.

**P2 — productisation.** M7. Valuable, but nothing here changes whether the
method is correct.

## Explicitly out of scope

- Issuing, retiring or pricing carbon credits
- Automated de-listing or any enforcement action
- Replacing accredited field verification
- Any claim of fraud or legal conclusion

---

Previous: [9. Competition strategy](../competition/strategy.md) · Next: [11. Demo flow](../competition/demo-flow.md)
