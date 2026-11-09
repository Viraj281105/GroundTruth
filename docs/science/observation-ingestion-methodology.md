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
