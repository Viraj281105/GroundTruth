# ADR-011 amendment 1: a masked unit is a raster, not a multipolygon

**Status:** Agreed by both owners (Viraj, Bhumi — 2026-11-05, recorded under C4). This
note amends one sentence of ADR-011 and otherwise leaves its decision text unchanged.
**Amends:** [ADR-011](ADR-011-unit-of-analysis.md), "Identifier and attribute scheme":
*`UnitRef.geometry` carries the masked multipolygon.*

## Why

A mask built from a 30 m forest layer over a ~7,000 km² district cuts it into a very
large number of fragments. As a polygon that would be an estimated millions of
vertices (an estimate, not a measurement), carried in every request and every stored
result, and too large to fetch from Earth Engine in one call. ADR-011 itself lists the
"pixel/vector convention at boundaries" as a parameter to fix, so choosing the raster
form is within what it left open. Only the sentence naming a multipolygon needs to
change.

## The decision

A masked unit is a **raster mask rebuilt from a recipe**, not a stored polygon.

`UnitRef.geometry` holds the unit's **unmasked outline** as ordinary GeoJSON (the GAUL
district, or the registry boundary for the treated unit), plus a foreign GeoJSON member,
`groundtruth_mask`, holding the mask's recipe: every pinned input and threshold, as plain
data. No contract change is needed, since `geometry` is already a free-form mapping.

Exactly as agreed:

1. **Pixels outside the district are set to 0 before eroding**, so district edges erode
   exactly as mask edges do.
2. **Erosion is a 300 m circular kernel, which is 10 pixels at 30 m.** It is applied last,
   to the masked raster, as ADR-011 requires of its inward buffer.
3. **Eligible area is pixel count × pixel area in the pinned equal-area CRS.**
4. **Fragment count is the connected-components count** of the eroded mask. It is recorded
   and never used to split or drop a unit, as ADR-011 requires.
5. **`geometry_hash` gets a raster equivalent:** a hash of the recipe, the outline and the
   eligible pixel count. The recipe alone would not notice an input changing underneath
   it; the pixel count does.
6. **The manifest hash already enters `spec_hash`**, because the manifest is pinned as a
   `DatasetRef`, so ADR-006's reproducibility guarantee holds for raster units as it would
   have for polygons. The recipe also travels inside each unit's geometry, so any request
   that embeds candidates hashes it directly.

## Implementation details, for review

These came up while building it and were **not** part of what the owners agreed above.
Neither changes which pixels are eligible.

- Fragments are counted with 8-connectivity (Earth Engine's `reduceToVectors`, using
  `eightConnected=true`). The count is a recorded diagnostic and decides nothing.
- A district with no baseline forest in a target ecoregion skips the erosion, because its
  mask is empty by definition.

## Still open

Settings that remain required and undecided are in
`cases/run_parameters/kariba-redd.yaml`. The code refuses to generate a unit set until
each is filled in, and no value is defaulted.

## Consequences

**Easier:** requests and stored results stay small; the mask is auditable as a short list
of inputs and thresholds; the same recipe drives area, covariates and NDVI.

**Harder:** a reader cannot open a unit in a GIS tool from the request alone, since the
raster has to be rebuilt in Earth Engine. Also, the recipe depends on pinned assets
staying available. Two of them are already marked deprecated in the Earth Engine catalog
(GAUL 2015 and Hansen 2023 v1.11), and WDPA snapshots may not stay public. The manifest
records eligible pixels and hashes, so a rebuild that differs is at least detected.
