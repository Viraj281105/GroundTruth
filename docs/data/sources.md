# 4. Data sources

> **Status: no analysis runs on these yet.** Every analysis today uses the synthetic
> fixture provider. The Earth Engine services for observations (#22), covariates and
> unit construction (#23) exist and are tested offline, but no real series, covariate
> or unit set has been reviewed, and observed-data runs still answer `501`.

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
| Road distance | gROADS v1 | our own uploaded asset ([steps](groads-upload.md)) | Access is the strongest predictor of deforestation pressure |
| Population density | WorldPop | `WorldPop/GP/100m/pop` | Settlement and subsistence pressure |
| Protected status | WDPA | `WCMC/WDPA/YYYYMM/polygons` (a dated snapshot) | **Exclusion criterion**, not a covariate |
| Land cover | ESA WorldCover | `ESA/WorldCover/v200` | Ecosystem stratification |

### How each covariate is measured

Agreed with Viraj (C4), 2026-11-05. **Every covariate is measured over the masked unit,
at the dataset's native scale.** The service returns raw values; transforms stay in the
engine. A missing value raises rather than being left out, because `match_donors` drops
a candidate with a missing covariate and records no reason.

| Covariate key | Measure | Native scale | Reference period | Pre-treatment for 2011? |
| --- | --- | --- | --- | --- |
| `rainfall_mm` | Mean annual total over calendar years **2001–2010**, then the mean over the unit | ~5.5 km, not 30 m | 2001–2010 | Yes |
| `elevation_m` | Mean of per-pixel values | 30 m | February 2000 | Yes |
| `slope_deg` | Slope computed per pixel from SRTM first, then the mean | 30 m | February 2000 | Yes |
| `road_distance_km` | Mean of per-pixel distance to the nearest road | Required setting; a vector layer has no native scale | 1980–2010, mixed vintage | Yes, nominally |
| `population_density` | Summed population ÷ the unit's eligible area, people per km² | ~100 m | 2000, matching Hansen `treecover2000` | Yes |

**`WorldPop/GP/100m/pop` is deprecated in the Earth Engine catalog.** Its replacement,
`WorldPop/GP/100m/R2025A/v1/pop`, starts in 2015, after treatment, so the deprecated asset
is the one with a 2000 image. The listing network test confirms that image still exists.

**The forest-only mask removes most towns**, so `population_density` measures rural
settlement pressure on eligible forest, not district population. The `log1p` rationale
below ("a single town would dominate") is therefore partly moot for this covariate. It is
harmless, and `log1p` stays.

**Roads are not a present-day layer.** gROADS v1 spans 1980–2010 with a vintage that
varies by place, so it is a better match to the pre-period than current OpenStreetMap, not
a clean snapshot. It is uploaded as our own asset ([steps](groads-upload.md)) and pinned
by asset id, source sha256 and upload date. The road source is a required setting that
names which layer is used. Current OSM, as a time-invariant access proxy, is allowed only
if the upload proves impossible, and only as a departure recorded in
[`limitations.md`](../science/limitations.md).

**Reference year versus release.** Each `DatasetRef.version` carries both, as
`<release>;ref=<epoch>` (for example `2023-v1.11;ref=2000`), so the reference year reaches
`spec_hash`. The manifest repeats it in `dataset_reference_periods`. A proper `DatasetRef`
field would be a future contract change (C1).

### Matching scale

Each covariate is compared on the scale set in
`engine/features/transforms.py` (`COVARIATE_TRANSFORMS`). The same transform is
applied to the project and to every candidate, and the transform is recorded
for provenance. A covariate a case requests without a registered scale fails
`tests/test_features.py`.

| Covariate key | Scale | Rationale |
| --- | --- | --- |
| `rainfall_mm` | raw | Roughly symmetric across the dry-forest range, and greenness responds to it close to linearly there |
| `elevation_m` | raw | No heavy tail at the scale of a donor search region; a metre means the same anywhere in it |
| `slope_deg` | raw | Bounded and already on the scale clearing decisions respond to |
| `road_distance_km` | `log1p` | Strongly right-skewed. Access pressure falls off steeply: 1 km versus 5 km matters far more than 51 versus 55. `log1p` keeps a unit on a road finite |
| `population_density` | `log1p` | Heavy right tail from towns. On a raw scale a single town would dominate the distance; zero density stays finite |

Not yet applied in a run: matching on these scales lands with the donor-pool
methodology (#3), which also has to keep raw values in the donor table.

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
| Hansen tree cover 2000 | `UMD/hansen/global_forest_change_2023_v1_11`, band `treecover2000` | Baseline forest mask, dated before the window by construction |
| JRC Global Surface Water | `JRC/GSW1_4/GlobalSurfaceWater`, band `occurrence` | Permanent water subtraction, `occurrence >= 90%` over the full record, applied uniformly with no per-unit exception |
| WDPA | `WCMC/WDPA/YYYYMM/polygons`, `STATUS_YR <= 2000` including `0`, designated/inscribed/established only | Protected-area subtraction, pre-window designations only. `Proposed`, `Not Reported` and `Adopted` are not subtracted (V7, agreed with Viraj (C4), 2026-11-05) |

GAUL 2015 and Hansen 2023 v1.11 are both marked deprecated in the Earth Engine catalog.
ADR-011 pins them anyway: a frozen input is the point, and a removed asset raises an error
rather than being replaced by a newer edition.

**How the mask is built:** as a raster rebuilt from a recipe, not a stored polygon. See
[ADR-011 amendment 1](../decisions/ADR-011-amendment-1-raster-units.md). The open
parameters are in `cases/run_parameters/kariba-redd.yaml`, and the unit set refuses to
generate while any is undecided. The registered-projects snapshot it needs is described in
[`cases/carbon_projects/README.md`](../../cases/carbon_projects/README.md).

**`ECO_NAME` strings must be copied from the asset, not from ADR-011's prose** (V5, agreed
with Viraj (C4), 2026-11-05). They are required with no default, and come from the
names-only listing (`generate_unit_set.py --list`). Two known traps: the ladder says
"Zambezian-Mopane woodlands" but the RESOLVE string may be "Zambezian and Mopane
woodlands", and RESOLVE 2017 may have merged Southern and Eastern miombo into "Dry miombo
woodlands". Rung 3 is rung 2's ecoregions in more countries (MWI, TZA).

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

**WDPA is a monthly release.** The Earth Engine catalog offers dated snapshots, which we
pin instead of `current`. Pinning a release is necessary but not sufficient for a re-run a
year later if a snapshot stops being served, so the generated unit set is also materialised
as a committed artifact under `data/manifests/`. See ADR-009.

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

- `GEE_SERVICE_ACCOUNT_JSON` (a key file path, or the key JSON) and, unless the key
  names its project, `GOOGLE_CLOUD_PROJECT`
- `EARTH_ENGINE_SENSOR` — no default; only a sensor agreed under C3 (today `landsat7`)
- `SENTINEL_HUB_CLIENT_ID` / `SENTINEL_HUB_CLIENT_SECRET` (optional alternative)
- `GLOBAL_FOREST_WATCH_API_KEY` (optional)

`groundtruth doctor` reports what is configured. No credential is ever logged: the
key is held as a secret, read only when Earth Engine is first used, and redacted
from any external error text before it reaches a message or a log. A missing or
rejected key is a `ConfigurationError`, never a fallback to simulated data. See
[`docs/architecture/earth-observation.md`](../architecture/earth-observation.md),
"The Earth Engine client".

---

Previous: [3. Architecture](../architecture/system.md) · Next: [5. Causal inference](../science/causal-inference.md)
