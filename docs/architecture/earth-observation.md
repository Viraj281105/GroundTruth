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
2. filter        collection → AOI ∩ period
3. mask          SCL cloud/shadow/snow rejection            [engine methodology]
4. composite     annual median per period                   [engine methodology]
5. index         band math: NDVI / EVI / NBR / SAVI         [engine, implemented]
6. reduce        zonal mean + clear-observation count       [engine methodology]
7. audit         flag periods below the coverage threshold  [engine, implemented]
8. emit          TimeSeries with n_valid_observations
```

Steps 3–7 are methodology. Steps 1–2 and the network call under them are
plumbing.

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
