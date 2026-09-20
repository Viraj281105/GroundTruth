# 4. Data sources

> **Status: none of these are wired in yet.** The pipeline currently runs on the
> synthetic fixture provider. This document is the specification the Earth
> Engine integration is being built against, not a description of data already
> flowing.

## Optical imagery

| Product | Asset | Resolution | Coverage | Role |
| --- | --- | --- | --- | --- |
| Sentinel-2 L2A | `COPERNICUS/S2_SR_HARMONIZED` | 10–20 m | 2017– | Primary for recent periods |
| Landsat 8 C2 L2 | `LANDSAT/LC08/C02/T1_L2` | 30 m | 2013– | Bridges to the Sentinel era |
| Landsat 7 C2 L2 | `LANDSAT/LE07/C02/T1_L2` | 30 m | 1999– | Long pre-periods (SLC-off after 2003) |
| Landsat 5 C2 L2 | `LANDSAT/LT05/C02/T1_L2` | 30 m | 1984–2012 | Deep baselines |

**Sensor harmonisation is a real problem, not a detail.** Landsat 5, 7, 8 and
Sentinel-2 have different band centres, different radiometric calibration and
different atmospheric correction. An NDVI series stitched naively across a
sensor change contains a step that looks exactly like a land-cover change.

Mitigations, in order of preference:

1. Keep the whole analysis window on one sensor family where possible.
2. Cross-calibrate using overlap years, and record the transform in provenance.
3. If neither is possible, place the sensor transition **inside the pre-period**
   so the synthetic control fit is forced to absorb it, and say so in the
   report.

## Forest cover and change

| Product | Asset | Notes |
| --- | --- | --- |
| Hansen Global Forest Change | `UMD/hansen/global_forest_change_*` | Annual loss year, 2000 tree cover, 30 m |
| JRC Global Forest Cover | `JRC/GFC2020/V2` | Independent cross-check |
| Global Forest Watch API | REST | Alerts and integrated loss statistics |

Hansen "loss" is canopy cover loss, not deforestation. It includes harvest,
fire, windthrow and plantation rotation. Treating it as deforestation
overstates land-use change in managed landscapes.

## Matching covariates

| Covariate | Source | Asset | Why it matters |
| --- | --- | --- | --- |
| Rainfall | CHIRPS | `UCSB-CHG/CHIRPS/DAILY` | Dominant driver of interannual greenness in dry forest |
| Elevation | SRTM | `USGS/SRTMGL1_003` | Proxy for temperature, accessibility, land-use suitability |
| Slope | Derived from SRTM | — | Steep land is less profitable to clear |
| Road distance | OpenStreetMap | derived raster | Access is the strongest predictor of deforestation pressure |
| Population density | WorldPop | `WorldPop/GP/100m/pop` | Settlement and subsistence pressure |
| Protected status | WDPA | `WCMC/WDPA/current/polygons` | **Exclusion criterion**, not a covariate |
| Land cover | ESA WorldCover | `ESA/WorldCover/v200` | Ecosystem stratification |

Protected areas are excluded from the donor pool rather than matched on. A
protected area is itself a conservation intervention, so using one as a control
estimates the project's effect *relative to another intervention*, which is not
the quantity anyone is buying.

## Unit construction

These products do not supply covariates. They define *what one analysis unit is*
— the administrative partition and the pre-treatment eligibility mask applied to
every unit, project and donor alike. The rule is
[ADR-011](../decisions/ADR-011-unit-of-analysis.md).

| Product | Asset | Role |
| --- | --- | --- |
| FAO GAUL 2015 level 2 | `FAO/GAUL/2015/level2` | The administrative partition. Frozen edition, chosen so the unit set cannot drift |
| RESOLVE Ecoregions 2017 | `RESOLVE/ECOREGIONS/2017` | Target miombo ecoregions; ≥50% rule and the search-region ladder |
| Hansen tree cover 2000 | `UMD/hansen/global_forest_change_*`, band `treecover2000` | Baseline forest mask, dated before the window by construction |
| JRC Global Surface Water | `JRC/GSW1_4/GlobalSurfaceWater`, band `occurrence` | Permanent water subtraction, `occurrence >= 90%` over the full record, applied uniformly with no per-unit exception |
| WDPA | `WCMC/WDPA/current/polygons`, `STATUS_YR <= 2000` including `0`, designated/inscribed/established only | Protected-area subtraction, pre-window designations only |

**The mask must not condition on a post-treatment outcome.** ESA WorldCover
exists only for 2020–2021, so it may be used for stratification but must never be
used to build units: masking with it would remove precisely the pixels cleared
during the study period. The same applies to protected areas gazetted after 2000.

That test is about the *variable*, not the file date, and two of the layers above
are not dated before 2001. GSW occurrence spans 1984–2021, and WDPA supplies
current boundaries for pre-2000 designations. Both are admitted for reasons
stated in ADR-011 and recorded in `docs/science/limitations.md`. A record of
*other interventions* — registered carbon projects, whenever they were
registered — is deliberately not restricted to the pre-period: a district
credited in 2016 is not a clean control for 2011–2022.

**WDPA is a monthly release and is not publicly archived for long.** Pinning a
release string is necessary but not sufficient for a re-run a year later; the
generated unit set must be materialised as a committed artifact. See ADR-009.

## Registry and claim data

| Source | Contents | Access |
| --- | --- | --- |
| Verra VCS registry | Project documents, issuance and retirement serials | Web, manual |
| Gold Standard registry | Project documents, issuance | Web |
| Plan Vivo registry | Project documents | Web |
| Berkeley Carbon Trading Project | Consolidated cross-registry database | Public download |

Claim figures are entered into case YAML with a `source_uri` and marked
`developer_reported: true` in the evidence bundle. They are inputs under test,
never inputs to the estimate.

## Known data limitations

**Cloud cover.** Tropical evergreen regions can have fewer than five usable
scenes in a year. The Southern Cardamom case exists partly to force this
problem into the open. Sparse years are flagged by the masking audit, not
interpolated.

**NDVI saturation.** Over closed canopy, NDVI stops responding to additional
biomass. This is why the Southern Cardamom case uses EVI.

**Tidal state.** Mangrove reflectance depends on water level at acquisition.
Composites must be restricted to a consistent tidal window before the Mikoko
Pamoja case can be run on real data at all.

**Boundary accuracy.** Registry boundaries are sometimes low-resolution or
inconsistent with the narrative project description. An inward buffer reduces
mixed-pixel error but changes what the estimate is *of*, so it is recorded.

**Sensor transitions.** See above. This is the most likely source of a spurious
finding in a long series.

**Fire.** A burn scar is a large NDVI drop that is not land-use change. NBR is
computed alongside NDVI so fire years can be identified and handled explicitly.

## Credentials

See `.env.example`. Required for real data:

- `GEE_SERVICE_ACCOUNT_JSON` and `GOOGLE_CLOUD_PROJECT`
- `SENTINEL_HUB_CLIENT_ID` / `SENTINEL_HUB_CLIENT_SECRET` (optional alternative)
- `GLOBAL_FOREST_WATCH_API_KEY` (optional)

`groundtruth doctor` reports what is configured. No credential is ever logged.

---

Previous: [3. Architecture](../architecture/system.md) · Next: [5. Causal inference](../science/causal-inference.md)
