# Data conventions

Shared conventions so that two analyses mean the same thing. Most of these are
boring; the boring ones are where silent errors come from.

---

## Spatial

| Convention | Value | Why |
| --- | --- | --- |
| Storage CRS | EPSG:4326 (WGS84) | Interchange standard; what registries publish |
| Analysis CRS | Local equal-area, per region | Area and distance computations in degrees are wrong |
| Geometry format | GeoJSON-like mappings in the contract | The core package must not require GEOS or GDAL |
| Boundary source | Registry record only | A hand-redrawn boundary changes the estimate and cannot be audited |
| Edge handling | Inward buffer, recorded as a caveat | Boundaries follow roads and rivers, so edge pixels mix land-cover classes |
| Leakage belt | 10 km ring, excluded from donors | Displaced deforestation makes a region a treated unit in disguise |
| Reduction scale | 30 m default | Matches Landsat; Sentinel-2 resampled for cross-sensor comparability |

**The buffer changes what the estimate is *of*.** It is reported rather than
silently applied, because a reader comparing our hectares against the registered
hectares deserves to know why they differ.

## Temporal

| Convention | Value | Why |
| --- | --- | --- |
| Period | Calendar year | Matches crediting periods and annual forest products |
| Composite | Annual median | Residual cloud is a heavy positive outlier a mean would absorb |
| Pre-period | Ends the year before the treatment date | No contamination from the intervention |
| Treatment date | Crediting period start | With the validation date as an anticipation sensitivity check |
| Minimum pre-periods | 5, configurable | A short pre-period cannot distinguish a good fit from an overfit one |
| Timestamps | ISO 8601, UTC | No ambiguity |

**Phenology matters.** A calendar year assumes comparable growing seasons across
units. Where a donor pool spans hemispheres or monsoon regimes that assumption
breaks, and the window must be defined against the growing season instead.

## Units

Declared in `contracts/units.py`. Unknown units are **rejected, not guessed**.

| Family | Units |
| --- | --- |
| Index | `ndvi`, `evi`, `nbr` |
| Area | `ha`, `km2` |
| Fraction | `fraction`, `percent` |
| Biomass | `t/ha` |
| Carbon | `tC`, `tCO2e` |
| Count | `credits` |

**Index to carbon conversion is forbidden** without an explicit,
provenance-carrying biomass step. Enforced by `assert_not_index_to_carbon`.

## Quality control

| Rule | Implementation |
| --- | --- |
| Cloud and shadow masked before compositing | SCL class rejection |
| Clear-observation count carried per period | `TimeSeries.n_valid_observations` |
| Sparse periods flagged, never interpolated | `audit_masking` |
| Non-finite values rejected at the estimator | `EstimationError`, not imputation |
| Sensor transitions detected and recorded | Calibration transform in provenance |

**Nothing is silently imputed.** If data is missing the pipeline says so, and
either excludes the period explicitly or refuses. An interpolated value
presented as an observation is precisely the kind of error this system exists to
catch in other people's work.

## Identifiers

| Kind | Format | Example |
| --- | --- | --- |
| Case | lowercase kebab | `kariba-redd` |
| Dataset | lowercase kebab + version | `sentinel2-l2a@2024.1` |
| Evidence | lowercase dotted | `effect.point_estimate` |
| Run | `run_` + 16 hex | `run_a3f9c21b8e0d4f76` |
| Unit | lowercase kebab | `donor-031` |

## Versioning

| Artefact | Scheme | Bumped when |
| --- | --- | --- |
| Contract | semver | Schema shape changes (ADR-003) |
| Engine | semver | **Results could change** |
| Dataset | provider version or snapshot date | The provider reprocesses |
| Evidence bundle | `schema_version` | The bundle shape changes |

An engine bump for a methodology fix is expected and correct. The version
travels with every result, so a number can always be attributed to the code that
produced it.

## Storage

Contents of `data/` are gitignored. See
[ADR-009](../decisions/ADR-009-data-management.md).

| Directory | Holds |
| --- | --- |
| `raw/` | Unmodified provider downloads |
| `interim/` | Intermediate processing |
| `processed/` | Analysis-ready series and covariates |
| `external/` | Third-party reference data |
