# Earth-observation architecture

How GroundTruth gets from satellite archives to an indicator time series, and
how that layer is designed to absorb sensors and products it does not yet
support.

**Status: the Earth Engine observation service is implemented (#22) and tested
offline; it has not yet produced a series that a person has reviewed.** It runs
only when asked (`--run-network`, a key), and observed-data *analysis runs* are
still refused (`501`) until a reviewed unit set exists. Every analysis today
comes from a labelled simulated fixture.

---

## The seam

```
engine (Viraj)                    │  platform (Bhumi)
──────────────────────────────────┼──────────────────────────────────
which index responds to the       │  which provider serves it
  thing being screened            │  authentication and credentials
which pixels are usable           │  retries, rate limits, timeouts
how a year reduces to one number  │  caching and dataset version pinning
what counts as sufficient         │  job orchestration and cancellation
  coverage                        │
what to do when it is not         │
```

They meet at one interface:

```python
class ObservationAccess(Protocol):
    def series(self, spec: ObservationSpec) -> TimeSeries: ...
    def dataset(self, indicator: Indicator) -> DatasetRef: ...
    def provenance(self, spec: ObservationSpec) -> Provenance: ...
```

`ObservationSpec` carries the unit, indicator, period range, cloud tolerance,
compositing strategy and inward buffer. Everything the engine needs to *ask for*
data; nothing about *how* it arrives.

This is why adding Sentinel-1 or GEDI later is a provider, not a refactor.

---

## Processing chain

```
1. resolve       platform picks a pinned DatasetRef for the indicator   [platform, #22]
2. filter        collection → AOI ∩ calendar year ∩ snapshot            [platform, #22]
3. reflectance   DN × scale + offset; outside [0, 1] masked [engine, specified]
4. mask          S2: SCL classes · Landsat C2: QA_PIXEL bits + QA_RADSAT
                                                            [engine, specified]
5. index         per clear scene: NDVI / EVI / NBR          [engine, specified]
6. composite     per-pixel annual median of the index       [engine, specified]
7. reduce        zonal mean over clear pixels; n_valid = zonal median of
                 per-pixel clear-scene count; clear-pixel fraction
                                                            [engine, specified]
8. audit         flag periods below the coverage threshold  [engine, implemented]
9. emit          TimeSeries with n_valid_observations
```

Steps 3–8 are methodology. They are specified in
`engine/observation/reduction.py` and published as plain data through
`describe_engine()["reduction"]`, which is the coordination point C3 handover.
`reduce_period` is a numpy reference implementation of the same chain, so a
platform client can check an Earth Engine chip against it. Steps 1–2 and the
network call under them are plumbing (#22): the platform client translates the
published spec into Earth Engine calls and chooses none of it.

### Reflectance before band math

Collection 2 Landsat stores `DN`, with `ρ = DN × 0.0000275 − 0.2`. The harmonized
Sentinel-2 collection stores `ρ × 10000`. Index formulae assume reflectance: EVI's
`+1` term is wrong on digital numbers. Pixels whose scaled value falls outside
`[0, 1]` are fill or artefacts and are masked.

### Index per scene, then the median

The index is computed on each clear scene, and the per-pixel median is taken
across the year. A band-first composite would pair red from one date with NIR
from another and describe a pixel that was never observed.

### Which sensor serves which year

| Sensor | Collection | Years | NBR SWIR band |
| --- | --- | --- | --- |
| Sentinel-2 | `COPERNICUS/S2_SR_HARMONIZED` | 2017– | B12 |
| Landsat 9 | `LANDSAT/LC09/C02/T1_L2` | 2022– | SR_B7 |
| Landsat 8 | `LANDSAT/LC08/C02/T1_L2` | 2013– | SR_B7 |
| Landsat 7 | `LANDSAT/LE07/C02/T1_L2` | 1999–2022 (SLC-off from mid-2003) | SR_B7 |
| Landsat 5 | `LANDSAT/LT05/C02/T1_L2` | 1984–2011 | SR_B7 |

Kariba's pre-period (2001–2010) predates Sentinel-2 and Landsat 8, so it rests on
Landsat 5/7. Calibration across the transition is #5 and is not done here.

**Decided for Kariba: Landsat 7 for all of 2001–2022 — agreed with Viraj (C3),
2026-11-03.** One sensor across the whole window, so the series contains no sensor
transition. Scenes after the 2003 scan-line-corrector failure have no-data
stripes, which the mask removes; they lower clear-observation counts rather than
bias values. The decision is recorded in `platform/datasets/catalog.py`
(`AGREED_SENSORS`) and in every series' provenance. **Future work:** a per-year
sensor rule published by the engine, and cross-sensor calibration (#5). Until
then the observation service reduces only an agreed sensor, for its agreed years.

**Scene-level cloud filter: not applied — agreed with Viraj (C3), 2026-11-03.**
`ObservationSpec.max_cloud_fraction` has no counterpart in the reduction spec, so
no scene is dropped for its cloud cover; cloud is removed by the per-pixel masks
only. Provenance records both the decision and the value the request carried.

### Why median, not mean

Residual undetected cloud is a heavy positive-reflectance outlier. A mean
absorbs it; a median rejects it. This matters more than it sounds: undetected
cloud is the dominant source of spurious "greening" in tropical series.

### Why clear-observation counts travel with the data

A year backed by two usable scenes is not the same measurement as a year backed
by twenty. `TimeSeries.n_valid_observations` carries the count per period so
downstream stages can refuse or down-weight cloud-starved years rather than
silently interpolating over them. Dropping this field would make the series look
more trustworthy than it is.

---

## The Earth Engine client (#22)

`platform/datasets/observation.py` (`EarthEngineObservationAccess`) is the
platform's `ObservationAccess`. Built from the environment with
`earth_engine_observations()`.

```
ObservationSpec ─► check ─► per year: cache ─(miss)─► sign in once ─► list scenes ─► reduce ─► store
                                                   rate-limited, retried, redacted
TimeSeries(values, n_valid_observations) + Provenance(dataset, snapshot, C3 decisions, spec, scenes)
```

| Concern | How |
| --- | --- |
| **Boundary with the engine** | Reads the (sensor, indicator) spec from `describe_engine()["reduction"]` and translates it (`earthengine.py`); imports nothing else from the engine. Requests outside the agreement — another sensor, years outside 2001–2022, a non-spectral indicator, an inward buffer (unit construction, ADR-011/#23), a unit without geometry — are refused before any network call. |
| **Credentials** | `GEE_SERVICE_ACCOUNT_JSON`: a key file path or the key JSON, held as a `SecretStr`. Read and used only on the first `series` call. Missing or rejected → `ConfigurationError`, raised `from None` so no original exception (which might quote the key) is chained. External error text is redacted against the key before it reaches a message or log. |
| **Retries** | Per call: 4 attempts, waits 2, 4, 8 s, for transient errors only (HTTP 408/429/5xx, dropped connections, "too many concurrent aggregations", capacity). Permanent errors ("Computation timed out", "User memory limit exceeded", asset not found, permission denied, anything unrecognised) are not retried. Either way the result is `DataUnavailableError`. The job layer (#24) retries whole attempts minutes apart on top, so a persistent outage is bounded at 4 × 3 tries. |
| **Rate limiting** | One process-wide budget, calls spaced evenly: `EARTH_ENGINE_MAX_REQUESTS_PER_MINUTE` (default 60). |
| **Version pinning** | `DatasetRef` `landsat7-c2-l2@C02-T1-L2@2026-11-01`: product version plus snapshot date. Scenes whose `system:version` is after 2026-11-01 are filtered out, so reprocessing cannot silently change a re-run. If that filter removes every scene of a year, the error says so and names the snapshot date. The snapshot is a constant in code; moving it is a new dataset version and changes `spec_hash`. |
| **Scene fingerprint** | Each year records a hash of the scene ids and their versions, in the cache and in provenance. |
| **Cache** | `data/interim/earthengine/` (`EARTH_ENGINE_CACHE_DIR`), one JSON file per (geometry, year). Key: pinned dataset + geometry hash + year + the reduction spec + grid. Each file holds its full key and a read is a hit only if every field matches; anything else is a miss and is rewritten. Failures are never cached. |
| **Grid** | Zonal reductions run in `EPSG:4326` at the spec's 30 m, unweighted (a pixel is in or out), `bestEffort=false` (the scale is methodology), `tileScale=4`. |
| **Geometry** | Passed as delivered, geodesic with the left-inside rule, so the Kariba part 1/5 overlap is inside once rather than cut out. Provenance records its hash. |
| **Failure** | Always raises. Nothing on this path imports or falls back to the synthetic provider; a test enforces it. |

**Not wired into analysis runs yet.** `earth_engine_access()` still raises, and
`/verify` and `POST /jobs` answer `501` for observed data: no reviewed unit set
exists yet, and a fixture may not stand in for real donors or covariates.

**Tests.** `tests/test_earthengine.py` covers all of the above against a fake
backend, offline. `tests/test_earthengine_network.py` is opt-in
(`pytest -m network --run-network tests/test_earthengine_network.py -v -s`): the
Kariba NDVI series 2001–2022, and a small chip checked against the engine's
`reduce_period`.

**Known risk.** The Kariba boundary is about 1.07 million ha, roughly 12 million
pixels at 30 m. One year's reduction may exceed Earth Engine's interactive
time limit; the service then raises `DataUnavailableError` ("Computation timed
out") rather than return a partial number, and the remedy is a batch-export
path (a follow-up issue).

---

## Covariates and units (#23)

The same session, cache and retries serve two more things.

**`EarthEngineCovariateAccess`** (`platform/datasets/covariates.py`) implements
`CovariateAccess`: raw values for the five covariates, over the masked unit. Definitions
and reference periods are in [`docs/data/sources.md`](../data/sources.md).

**`EarthEngineUnitConstruction`** (`platform/units/provider.py`) measures what ADR-011's
rules need, one district at a time, with each step cached so a timeout loses only that
step. The rules stay in `platform/units/rules.py`. The mask is a raster rebuilt from a
recipe that travels inside `UnitRef.geometry`
([ADR-011 amendment 1](../decisions/ADR-011-amendment-1-raster-units.md)), and #22's
service applies the same mask when reducing NDVI.

**`experiments/kariba_benchmark/generate_unit_set.py`** drives it. It sits outside
`platform/` because the ladder's stopping rule needs Viraj's `match_donors`, and it fetches
only pre-period NDVI, so no post-treatment outcome is touched before the pool is fixed.

```
--list          literal names to fix the settings from; no counts
--timing-trial  seconds per step on one district; no counts
(no flag)       climb the ladder and report; --write also writes the manifest
```

Before any Earth Engine call it checks `cases/run_parameters/kariba-redd.yaml` and refuses,
naming each undecided setting. A setting nobody has decided is `null` there; nothing is
defaulted. It also refuses while the engine does not apply covariate transforms in its runs
(V9(a), Viraj's #3), because the ladder would then match on a different scale than the run.

**Compute limits.** A district is around 8 million pixels at 30 m, with several reductions
each, and every rung climbed costs another pass. Some steps may exceed Earth Engine's
interactive time limit. Fragment counting looks the most likely to, so it runs only for
units that stay in the pool. A timeout raises `DataUnavailableError` with nothing partial
returned, and the timing trial exists to measure this on one district before anyone builds
a batch-export path.

---

## Supported and planned sources

| Product | Role | Status |
| --- | --- | --- |
| Sentinel-2 L2A | Primary optical, 2017– | **Planned** — MVP |
| Landsat 8/9 C2 L2 | Bridge to the Sentinel era, 2013– | **Planned** — MVP |
| Landsat 5/7 C2 L2 | Deep pre-periods, 1984– | Landsat 7: **Implemented** in the observation service (agreed sensor for 2001–2022); Landsat 5: **Planned** |
| Hansen Global Forest Change | Annual loss year, tree cover | **Planned** |
| CHIRPS | Rainfall covariate | **Planned** — MVP |
| SRTM | Elevation, derived slope | **Planned** — MVP |
| WorldPop | Settlement pressure | **Planned** |
| OpenStreetMap | Road-distance raster | **Planned** |
| WDPA | Protected-area **exclusion** | **Planned** |
| Sentinel-1 SAR | Cloud-independent structure | **Future** |
| MODIS | Long, coarse, daily record | **Future** |
| GEDI L4B | Above-ground biomass density | **Future** — needed for carbon |
| ESA CCI Biomass | Biomass density | **Future** — needed for carbon |
| FIRMS / MCD64 | Fire, to separate burn from clearing | **Future** |
| JRC Global Surface Water | Hydrology, inundation | **Future** |
| Commercial imagery | Sub-metre verification of specific sites | **Future** |

Protected areas are an **exclusion criterion, not a covariate**. A protected area
is itself a conservation intervention, so using one as a control estimates the
project effect relative to another intervention — not the quantity anyone is
buying.

---

## Extension points

Each future capability has a place to land without restructuring.

| Capability | How it attaches | Needs a contract change? |
| --- | --- | --- |
| A new optical sensor | New provider behind `ObservationAccess` | No |
| Sentinel-1 SAR | Same port; a new `Indicator` member for backscatter | Minor (additive enum) |
| SAR + optical fusion | A composite provider wrapping two others | No |
| Change detection | A new `Indicator` plus its reduction | Minor |
| Land-cover classification | A provider returning class fractions per period | Minor |
| Biomass proxies | A provider plus the conversion step in the engine | Minor |
| Anomaly detection | Consumes stored bundles; no EO change | No |
| Temporal reconstruction (gap filling) | A provider decorator, with the method recorded in provenance | No |

The reason these are cheap is that none changes the shape of `TimeSeries` or of
`AnalysisRequest`. A decorator pattern over `ObservationAccess` covers fusion,
gap-filling and caching uniformly.

---

## Known hazards

These are the things most likely to produce a wrong answer. Each has a
mitigation, none has a guarantee.

**Sensor transitions.** Landsat 5/7/8 and Sentinel-2 differ in band centres,
calibration and atmospheric correction. A series stitched naively across a
transition contains a step that looks exactly like land-cover change. This is
the single most likely source of a spurious headline finding. Mitigations, in
preference order: keep the window on one sensor family; cross-calibrate on
overlap years with the transform recorded in provenance; place the transition
inside the pre-period so the synthetic control fit is forced to absorb it — and
say so in the report.

**Canopy saturation.** NDVI stops responding above ~0.8. A forest can double its
above-ground carbon with no NDVI signal. Why Southern Cardamom uses EVI.

**Cloud.** Tropical evergreen regions can yield fewer than five usable scenes in
a year. Surfaced by the masking audit, never interpolated.

**Tidal state.** Mangrove reflectance depends on water level at acquisition.
Composites must be restricted to a consistent tidal window before Mikoko Pamoja
can run on real data at all.

**Fire.** A burn scar is a large index drop that is not land-use change. NBR is
computed alongside NDVI so fire years can be identified and handled explicitly.

**Boundary accuracy.** Registry boundaries are sometimes coarse or inconsistent
with the project narrative. An inward buffer reduces mixed-pixel error but
changes what the estimate is *of*, so the buffer is recorded as a caveat.

---

## Implementation status

| Component | Status |
| --- | --- |
| `ObservationAccess` / `CovariateAccess` / `DonorCandidateAccess` ports | Implemented |
| NDVI, EVI, NBR, SAVI band math | Implemented and unit-tested against published formulae |
| SCL cloud masking, median compositing, coverage audit | Implemented |
| Zonal statistics, edge-buffer and leakage-belt caveats | Implemented |
| Synthetic fixture provider | Implemented, labelled simulated |
| Earth Engine observation service: auth, retries, rate limit, cache, pinning (#22) | Implemented; tested offline; network test opt-in |
| Covariate service and ADR-011 unit construction (#23) | Implemented; tested offline; network tests opt-in |
| Observed-data analysis runs | **Not available** — `501` until a reviewed unit set exists |
| **Cross-sensor calibration** | **Not implemented** |

The Earth Engine service raises rather than falling back to fixtures. A silent
fallback would let simulated numbers be served under a real-data label, which is
the one failure mode this system must not have.

---

See also: [`docs/data/sources.md`](../data/sources.md) for product detail,
[`docs/architecture/contract.md`](contract.md) for the port definitions.
