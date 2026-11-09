# Observation ingestion and claim matching: methodology and provenance

This describes how GroundTruth turns a user's project boundary into annual vegetation observations,
what is recorded so another person can check them, and exactly what the platform does and does not
conclude from them. It describes the code as it is; it makes no claim that the outputs are
scientifically *validated* (see §8).

## 1. Scope

For a project defined by an uploaded boundary, an authorised user can request Sentinel-2 surface
reflectance observations. A worker process fetches the scenes, reduces them to one value per year per
vegetation index, stores the result, and records what it did. The same stored observations then feed
the project's readiness checks, assessment, observation charts, technical dossier and claim matching.

Implemented in `platform/projects/ingestion.py` (request, queue, status, summary, ledger record) on
top of the existing pipeline `data_access/aoi_pipeline.py` and `data_access/stac.py`. Nothing here is
simulated: if no scene can be found, a year stays empty.

## 2. Request validation (before anything is fetched)

| Check | Rule |
|---|---|
| Boundary | The project's stored boundary must be readable polygon geometry. |
| Years | 2017 to the current year (Sentinel-2 L2A is not available earlier); at most 12 years. |
| Season window | `MM-DD` start and end inside one calendar year. A window crossing New Year must be two requests. |
| Cloud limit | 0–80 % scene cloud cover. |
| Indicators | `ndvi`, `evi`, `ndmi`, `nbr`. NDVI is always stored. |
| Resolution | 20–500 m analysis grid. |
| Size | At most 30 scenes per request (years x scenes per year) and about 1.5 million grid cells, estimated from the boundary extent. |
| Concurrency | One queued or running request per project. |

Rejections carry a code, a plain message and a hint. Only a user with owner-level edit access to the
project can request; any other organisation receives a 404 as if the project did not exist.

## 3. Processing steps

1. **Scene discovery.** STAC search on Microsoft Planetary Computer, collection `sentinel-2-l2a`,
   by the boundary's bounding box, the season window of each year and the cloud limit. Boundaries that
   span several MGRS tiles are processed as a mosaic (multi-tile). Where the provider hosts the same
   acquisition under two processing baselines, one is preferred (`data_access/stac.py`).
2. **Retrieval.** Cloud-optimised GeoTIFF assets are read through the provider's free signed-URL
   service. No paid API is used.
3. **Radiometric harmonisation.** For processing baseline 04.00 and later the +1000 `BOA_ADD_OFFSET`
   is removed so reflectance is comparable across the 2022 baseline change; the scene record keeps
   `processing_baseline` and whether the offset was applied. Reflectance scale is 1e-4.
4. **Grid.** Bands are resampled to a UTM grid at the requested resolution over the boundary's extent.
5. **Quality mask.** Per scene, pixels whose Scene Classification Layer value is 0 (no data),
   1 (saturated/defective), 3 (cloud shadow), 8 or 9 (cloud, medium/high probability), 10 (thin
   cirrus) or 11 (snow/ice) are discarded (`engine/observation/masking.py`).
6. **Indices**, per pixel and scene:
   NDVI = (NIR − Red) / (NIR + Red); NDMI = (NIR − SWIR1) / (NIR + SWIR1);
   NBR = (NIR − SWIR2) / (NIR + SWIR2);
   EVI = 2.5 (NIR − Red) / (NIR + 6 Red − 7.5 Blue + 1).
7. **Annual composite.** For each year, the per-pixel median of the clear observations of that year's
   season window. A pixel with no clear observation is excluded, not filled.
8. **Zonal reduction.** The mean of the composite over the clear pixels inside the project polygon.
9. **Coverage.** `aoi_coverage_pct` is the percentage of pixels inside the polygon that have a clear
   composite value (it reflects both tile coverage and cloud). A year is *spatially complete* only at or
   above 95 %. A year with no clear pixel has no value and evidence state `UNAVAILABLE` (never estimated).

## 4. Outcome of a request

| Status | Meaning |
|---|---|
| `succeeded` | Every requested year has a value and coverage is at or above 95 %. |
| `partial` | Some requested year has no usable value, or coverage is below 95 %. Reported as incomplete, with the years named; empty years are not estimated. |
| `failed` | Nothing usable was produced, the provider could not be reached, or the request was invalid. A plain reason and an error code are stored. Nothing is reported as data. |
| `cancelled` | Cancelled while still queued. |

A worker that dies mid-run leaves a request with no heartbeat; a sweep marks it failed ("interrupted").

## 5. Provenance recorded for every observation

* Per year: scene ids, acquisition dates, contributing tiles, scene count, clear-pixel fraction,
  area coverage, collection ids, and `scenes_sha256` (a hash over the sorted scene ids).
* Per bundle: catalogue URL, bounding box, raster grid (CRS, bounds, resolution, size), method name,
  code version, and all parameters. Stored as JSON in the provenance-checked cache, keyed by the
  project's id; a bundle that fails its provenance check is not served.
* Per request: parameters, status, times, worker id, and the measured result summary.
* Audit ledger: a record of kind `observation.ingested` holding the request parameters, the coverage
  summary and the SHA-256 of every stored file, chained to the project's other records
  (`platform/audit/ledger.py`). The ledger can be recomputed from stored content; it is not externally
  timestamped.

## 6. Reproducibility

Given the same scene ids, boundary, parameters and code version, the computation is deterministic.
It is **not** guaranteed that a later request returns the same scenes: the provider may add scenes,
reprocess scenes or change which baseline it hosts. To re-check a stored result, compare the recorded
scene ids and `scenes_sha256`, re-run with the recorded parameters, and compare the file hash with the
ledger record. Differences in the scene set explain differences in the values.

## 7. What the observations can and cannot show

* They measure **greenness and canopy moisture of the land inside the boundary** in one season each
  year. A greenness change between two years is an *observation*.
* They do **not** measure tree survival, number of trees, carbon, biodiversity or ecosystem recovery.
  A vegetation index is not carbon (rule R1) and no biomass conversion is provided.
* They do **not** show that the project caused a change (rule R3). Rainfall, season timing and
  land-use change also move greenness, and no comparison with untreated land is computed for user
  projects.
* At 100 m, a pixel mixes several surfaces; small plots are poorly resolved. Cloud, haze and the
  chosen season affect which pixels are clear.

## 8. Validation status (be sceptical)

The pipeline's plumbing is tested (masking, indices, provenance, queue, coverage classification,
isolation) against fake scene chips and in isolated end-to-end runs. The **values have not been
validated against field measurements or an independent reference product**, and the registry marks
Sentinel-2 as accessible but unvalidated for that reason. Passing tests show the code does what it
says, not that the numbers are scientifically correct for a given site.

## 9. Claim matching (`claims/evidence_match.py`)

A promoted claim is compared with stored evidence and reported as supported, partially supported,
contradicted, or insufficiently evidenced. It is never reported as verified.

| Claim | Evidence used | Rule |
|---|---|---|
| Area (ha) | Geodesic area of the uploaded boundary | Within ±5 %: supported (as the project area). Smaller: partially supported (fits; restored extent not shown). Larger: contradicted. |
| Greenness change | Observed change between two annual values | Wrong direction, or observed < half the claimed change: contradicted. Within max(0.02, 25 % of the claimed change): supported. Otherwise partial. Coverage below 95 % in either year downgrades a match to partial. Fewer than two observed years: insufficiently evidenced. |
| Survival, trees planted, carbon, biodiversity, ecosystem recovery, causation, absolute wording | none available | Always insufficiently evidenced, with the reason and the evidence that would be needed. |

The tolerances are engineering choices, stated in code and shown with each outcome; they are not
derived from field data.

## 10. Worked example (acceptance run, 2026-11-10)

A fresh NGO account created a 4 x 4 km test boundary near Pune (about 1,870 ha; treatment start 2021)
and requested Sentinel-2 observations through the app: 2021-2026, season 15 January to 15 March, cloud
limit 20 %, 100 m grid, 2 scenes per year, NDVI and EVI. A real worker process on PostgreSQL ran it
against Microsoft Planetary Computer and finished as `succeeded`.

| Year | Scenes (tile 43QCA) | Area covered | NDVI | EVI |
|---|---|---|---|---|
| 2021 | 2 | 99.8 % | 0.317 | 0.189 |
| 2022 | 2 | 100.0 % | 0.349 | 0.185 |
| 2023 | 2 | 99.4 % | 0.420 | 0.222 |
| 2024 | 2 | 99.9 % | 0.338 | 0.184 |
| 2025 | 2 | 99.7 % | 0.327 | 0.177 |
| 2026 | 2 | 100.0 % | 0.371 | 0.199 |

The assessment became **Level 1 (basic monitoring), evidence confidence Moderate**, with the observed
change labelled "not a causal effect" and attribution **Inconclusive**: causal assessment needs five
pre-treatment years, and Sentinel-2 L2A only reaches back to 2017.

Document claims written *before* any data was fetched were then promoted by a user and matched:

| Claim (as stated) | Outcome | Basis |
|---|---|---|
| "restores 1,900 hectares" | Supported (as the project area) | Boundary 1,870 ha, +1.6 % |
| "NDVI increased by 0.05 since 2021" | Supported, with a limitation | Observed +0.054 (2021 to 2026). The record is not monotonic (0.317 to 0.420), so the limitation says a two-year difference can reflect year-to-year variation. |
| "85 % of planted seedlings survived" | Insufficiently evidenced | Survival needs field plots |
| "sequestered 40,000 tCO2e" | Insufficiently evidenced | A vegetation index is not carbon |
| "proves biodiversity has fully recovered" | Insufficiently evidenced | Not observable from greenness; absolute wording |

### Independent cross-check of the numbers

For three years the NDVI was re-derived from the *same scene ids* by a separate script that does not
use GroundTruth's pipeline (rasterio directly, native 10 m, SCL mask, per-pixel median of the two
scenes, mean over the boundary):

| Year | Processing baseline | Independent | Stored | Difference |
|---|---|---|---|---|
| 2021 | 2.12 | 0.3137 | 0.3170 | -0.0033 |
| 2024 | 5.1 | 0.3333 | 0.3381 | -0.0049 |
| 2026 | 5.11 / 5.12 | 0.3653 | 0.3712 | -0.0059 |

The independent values are 1.0 to 1.6 % lower. A small, consistent offset is expected from computing at
10 m instead of the 100 m analysis grid and from window rounding. The agreement across baselines 2.12,
5.1 and 5.1x also shows the baseline-04.00 offset handling does not introduce a step.
**This shows the implementation agrees with an independent reimplementation of the same formula on the
same scenes. It does not validate NDVI against field measurements.**

### Traceability checks performed

* The SHA-256 of each stored bundle on disk equals the hash in the `observation.ingested` ledger record.
* The technical dossier contains per-year scene ids and `scenes_sha256` (`observations.csv`), the claims
  with their document wording and outcomes (`claims.json`) and the request record
  (`observation-ingestions.json`); every file is listed in `manifest.json` with its SHA-256.
* Downloading the dossier twice from unchanged state produced byte-identical files (same report SHA-256).
* Altering one ledger record directly in PostgreSQL made the auditor's Reports page show "Integrity check
  failed" naming the record; restoring it returned the ledger to verified with the same ledger root.
