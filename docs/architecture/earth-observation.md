# Earth-observation architecture

How GroundTruth gets from satellite archives to an indicator time series, and
how that layer is designed to absorb sensors and products it does not yet
support.

**Status: the interface is implemented; no real provider is.** Everything today
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
1. resolve       platform picks a pinned DatasetRef for the indicator
2. filter        collection → AOI ∩ calendar year
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
network call under them are plumbing (#22).

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

## Supported and planned sources

| Product | Role | Status |
| --- | --- | --- |
| Sentinel-2 L2A | Primary optical, 2017– | **Planned** — MVP |
| Landsat 8/9 C2 L2 | Bridge to the Sentinel era, 2013– | **Planned** — MVP |
| Landsat 5/7 C2 L2 | Deep pre-periods, 1984– | **Planned** |
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
| Earth Engine configuration, band maps, index expressions | Implemented |
| **Earth Engine network calls** | **Not implemented — raises `DataUnavailableError`** |
| **Covariate extraction from real products** | **Not implemented** |
| **Cross-sensor calibration** | **Not implemented** |

The Earth Engine provider raises rather than falling back to fixtures. A silent
fallback would let simulated numbers be served under a real-data label, which is
the one failure mode this system must not have.

---

See also: [`docs/data/sources.md`](../data/sources.md) for product detail,
[`docs/architecture/contract.md`](contract.md) for the port definitions.
