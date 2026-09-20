# ADR-011: The unit of analysis is a masked administrative district

**Status:** Proposed
**Date:** 2026-09-20
**Deciders:** Viraj, Bhumi

## Context

Nothing in this repository defines what *one unit* is. `UnitRef` carries an
optional geometry, an optional centroid and an optional area. The only donor
source that exists returns the strings `donor-000 … donor-N` from a fixture
generator. `DonorSpec.leakage_belt_km` is carried into every request and read by
nothing, because `excluded_unit_ids` is empty and no code populates it.

That gap blocks three P0 issues at once. #3 asks for "candidate region
generation over an ecoregion-constrained search area" and #23 asks for "real
covariates for a Kariba donor pool of 80+ candidates". Neither can start
without an answer, and if they start independently they will invent two
different answers.

The forcing case is Kariba REDD+ (VCS 902): ~785,000 ha of miombo woodland in
Zimbabwe, pre-period 2001–2010, post-period 2011–2022, NDVI, a 10 km leakage
belt, and a target pool of 80 candidates. A donor must be a comparable,
unprotected, uncredited area of miombo in Zimbabwe, Zambia or Mozambique. What,
concretely, is one candidate polygon?

The choice is not neutral with respect to the estimate. It determines how many
candidates exist at all and therefore whether `min_donors` is reachable; what
within-unit averaging destroys; whether the leakage belt can be expressed;
whether protected areas can be excluded spatially; and — through the number of
donors J relative to the pre-period length T₀ — whether the donor weights are
identified and how small a placebo p-value the design can even produce.

Two constraints are fixed and cannot be traded against:

1. **The Kariba specification is pre-registered** (`experiments/kariba_benchmark/PLAN.md`).
   Whatever is decided here must be decided *before* any real data is seen, and
   must contain no step whose outcome a later analyst could tune.
2. **Reproducibility is the product** (ADR-006, ADR-009). The unit set must be a
   deterministic function of pinned, publicly obtainable inputs.

## Decision

**A unit of analysis is one administrative district polygon, intersected with a
pre-treatment eligibility mask, observed as a single zonal series.**

Formally, for candidate district *d*:

```
unit(d) = d
        ∩ target_ecoregions
        ∩ baseline_forest            (Hansen treecover2000 ≥ 30%)
        ∖ permanent_water            (JRC GSW occurrence ≥ 90%)
        ∖ protected_areas            (WDPA, status_year ≤ 2000)
        ∖ registered_carbon_projects
        ⊖ inward_buffer(300 m)
```

The treated unit is constructed by **exactly the same rule**, substituting the
registry boundary for *d*:

```
unit(project) = registry_boundary(VCS 902) ∩ … ⊖ inward_buffer(300 m)
```

Applying the same mask to both sides is the point. A treated unit that includes
its reservoir shoreline and protected-area overlap while donors exclude theirs
is not comparable to them, and no amount of covariate matching repairs that.

### Administrative source: FAO GAUL 2015 level 2

`FAO/GAUL/2015/level2`, available directly as an Earth Engine asset.

Districts across Zimbabwe, Zambia and Mozambique are of the order of
5,000–10,000 km², which is the same order as Kariba's ~7,850 km². This is the
single strongest reason to prefer them: no other readily available partition of
the region produces units naturally near project scale.

GAUL 2015 is chosen over GADM 4.1 for two reasons. It is already an Earth Engine
asset, so no upload step sits between the pinned input and the computation. And
it is **frozen** — the 2015 edition is not updated — which for reproducibility is
a feature, not staleness. A unit set is a spatial partition, not a claim about
present-day governance; a partition that cannot drift is worth more here than one
that is current.

### Eligibility and exclusion rules

Each rule is an *eligibility* rule, applied before any distance is computed, and
each records a human-readable reason on the resulting `DonorMatch`.

| Rule | Threshold | Why |
| --- | --- | --- |
| **Ecoregion** | ≥ 50% of the district's baseline-forest area falls in a target miombo ecoregion | A donor from a different biome is not a counterfactual for miombo |
| **Protected areas** | Any WDPA polygon with `status_year ≤ 2000` is subtracted | A protected area is itself a conservation intervention; a control drawn from one estimates the project effect *relative to another intervention* |
| **Registered carbon projects** | Subtracted where geometry exists; district excluded where a project is known to be present but its geometry is not | Another credited project is a treated unit in disguise |
| **Leakage belt** | District excluded entirely if it intersects the 10 km belt around the project boundary | Displaced deforestation makes a neighbour a treated unit in disguise |
| **Permanent water** | JRC GSW occurrence ≥ 90% subtracted | Water pixels carry no vegetation signal and would swamp a zonal NDVI mean |
| **Area band** | Eligible area within [⅓×, 3×] the project's **eligible** area | See "Why area comparability matters" below |
| **Minimum absolute area** | Eligible area ≥ 500 km² | Below this the zonal mean is dominated by composition rather than condition |

Protected status and carbon-project status are **exclusions, not covariates**,
restating the rule already in #3, #23 and `docs/data/sources.md`.

### Why the mask must be pre-treatment

The baseline forest mask is Hansen `treecover2000`, and the protected-area filter
is `status_year ≤ 2000`. Both are deliberately drawn from before the pre-period
begins in 2001.

Masking with a contemporary land-cover product instead — ESA WorldCover, which
exists only for 2020–2021 — would condition on a **post-treatment outcome**. It
would remove precisely the pixels that were deforested during the study window,
which is the signal the analysis exists to measure, and it would do so
asymmetrically between a protected project and unprotected donors. The bias runs
in the direction of manufacturing a project effect.

Conditioning on a *pre-treatment* covariate is legitimate and is what matching
already does. Conditioning on anything dated after 2000 is not. This distinction
is the reason ESA WorldCover appears in `docs/data/sources.md` for stratification
but must not be used to build units.

The same logic applies to WDPA: a park gazetted in 2015 must not be subtracted,
because its land was ordinary woodland throughout the pre-period and possibly
protected in response to the same pressures the project responded to.

Permanent water is the one defensible exception to a strict pre-2001 rule. The
Kariba reservoir was impounded decades before the window, so a full-record
occurrence mask and a pre-2001 mask agree. Where a water body could plausibly
have changed within the window, the pre-period epoch must be used instead.

### Why area comparability matters — and how much

The naive argument for equal-area units is that an effect measured over
7,850 km² is not comparable to one measured over 500 km². For a **mean** index
that argument is weaker than it looks: a zonal mean is an intensive quantity, so
area does not bias its level.

The real reason is **inference**, not estimation. The placebo test statistic is
the post/pre RMSPE *ratio*, and the permutation p-value compares the treated
unit's ratio against the donors'. That comparison is only meaningful if donor
outcome series have comparable noise characteristics to the treated unit's. A
much smaller unit has a noisier annual mean and a more composition-driven series;
retained in the reference distribution, it inflates the tail and makes the
p-value conservative in an uncontrolled way.

That is why the decision is an area *band* rather than exact matching. Units need
to be of the same order, not the same size.

A second-order point worth recording: the project's activity is spatially
concentrated within its boundary, so a boundary-wide mean NDVI effect is diluted
by the treated fraction. This dilution affects the *magnitude* of the estimate
but not its sign or its placebo ranking, and it applies to the treated unit only.
It is a reason the estimate must not be read as an intensity of local change, and
it belongs in the report caveats — not a reason to change the unit design.

### Identifier and attribute scheme

```
unit_id = f"gaul2015:{ADM2_CODE}"      # e.g. "gaul2015:40765"
```

The treated unit keeps `unit_id = case_id` (`"kariba-redd"`), because it is not a
GAUL unit — it is the registry boundary under the same mask.

`UnitRef.area_ha` carries the **eligible** area after masking, not the
administrative or registered area. `UnitRef.geometry` carries the masked
multipolygon.

**Contract limitation found while writing this.** `UnitRef.attributes` is typed
`dict[str, float]`, so it cannot carry the country code, the ecoregion name, the
GAUL name or the exclusion provenance — all of which a reviewer needs to read a
donor table. The prototype encodes the source and code in `unit_id` and accepts
the loss. Carrying string attributes is a contract change requiring both owners
and a version bump; it is out of scope here and should be filed separately.

### Search-region ladder

The candidate count is not knowable before the data is pulled, and "widen the
search until enough donors appear" is exactly the kind of post-hoc freedom the
pre-registration forbids. The expansion is therefore fixed in advance as an
ordered ladder. Take the first rung yielding ≥ 80 candidates; record which rung
was used in the evidence bundle.

| Rung | Search region |
| --- | --- |
| 1 | Southern Miombo + Central Zambezian Miombo woodlands, in ZWE, ZMB, MOZ |
| 2 | Rung 1 + Eastern Miombo woodlands + Zambezian–Mopane woodlands |
| 3 | Rung 2 + the same ecoregions in MWI and TZA |

If rung 3 still yields fewer than `min_donors` admissible units, `match_donors`
raises `DonorPoolError` and the case is refused. That is the correct outcome, not
a problem to engineer around.

### Exact inputs required

Everything below must be pinned as a `DatasetRef` per ADR-009 before the pool is
generated.

| Input | Source | Asset / identifier | Owner | Status |
| --- | --- | --- | --- | --- |
| Project boundary | Verra VCS 902 registry documents | `cases/boundaries/kariba-redd.geojson` | Bhumi | **Missing — #2** |
| Administrative units | FAO GAUL 2015 | `FAO/GAUL/2015/level2` | Bhumi | Available |
| Ecoregions | RESOLVE / Dinerstein et al. 2017 | `RESOLVE/ECOREGIONS/2017` | Bhumi | Available |
| Baseline forest | Hansen GFC | `UMD/hansen/global_forest_change_2023_v1_11`, band `treecover2000` | Bhumi | Available, already in `COLLECTIONS` |
| Permanent water | JRC Global Surface Water | `JRC/GSW1_4/GlobalSurfaceWater`, band `occurrence` | Bhumi | Available |
| Protected areas | WDPA | `WCMC/WDPA/current/polygons`, filtered `STATUS_YR ≤ 2000` | Bhumi | Available — **release must be pinned**, see below |
| Registered carbon projects | Berkeley Carbon Trading Project | public download | Bhumi | **Geometry largely unavailable — limitation below** |

Three quantities must be **measured and recorded before the pre-registered run**,
because the design's viability depends on them and none can be asserted from a
desk:

1. The project's eligible area after masking, which sets the area band.
2. The candidate count at each rung of the ladder.
3. The number of districts lost to the leakage belt.

**WDPA is a monthly release and is not archived publicly for long.** Pinning
`version` to a release string is necessary but not sufficient for a re-run a year
later. The mitigation is to materialise the generated unit set — ids, geometries
and a geometry hash — as a committed artifact under `data/manifests/`, so the
donor pool itself becomes a versioned, reviewable data product. This is the
trigger ADR-009 names in its "Revisit when".

## Alternatives considered

| | **A. Equal-area hex (H3)** | **B. Masked admin district** *(chosen)* | **C. Ecoregion ∩ admin** | **D. Area-matched sampled regions** |
| --- | --- | --- | --- | --- |
| **Project-area comparability** | Best. Exact by construction, though no H3 resolution lands near 7,850 km² — res 3 is ~12,400 km², res 4 ~1,770 km², so cells must be aggregated | Good. Same order of magnitude; band enforces it | Poor. Fragments into very unequal slivers | Best. Exact by construction |
| **Ecoregion / habitat similarity** | Poor. Cells straddle ecoregion and biome boundaries arbitrarily | Good after masking and the ≥50% rule | Best. Ecoregion is a defining edge | Good, if sampling is ecoregion-constrained |
| **Administrative boundaries** | Ignored. A cell can span three countries with different forest law | Aligned. Land tenure, allocation and forestry enforcement genuinely vary at district level, so units differ on the dimension policy actually operates on | Aligned | Ignored |
| **Leakage exclusion** | Clean. Belt intersection is a simple geometric test on regular cells | Workable but blunt. A district is large, so belt intersection excludes the whole unit | Workable | Clean |
| **Donor count** | High and tunable by resolution — which is itself a researcher degree of freedom | Adequate; ladder makes expansion mechanical | Unpredictable after a minimum-area filter | Unlimited, which is a warning sign not a feature |
| **Satellite aggregation** | Uniform pixel counts per unit; attractive for variance comparability | Acceptable; area band bounds the variance spread | Poor. Sliver units have few pixels | Uniform |
| **Covariate availability** | All five covariates are raster-derived, so any polygon works | Same, plus census-based population attaches natively | Same | Same |
| **Synthetic-control assumptions** | Neutral on SUTVA; no substantive meaning to a "place" | Better on SUTVA — administrative units are closer to the level at which interference and policy act | Neutral | Weakest. Overlapping samples violate independence of donors |
| **Reproducibility** | Deterministic given a resolution and an origin | Deterministic from a frozen pinned asset | Deterministic but sensitive to the minimum-area cut | **Poor.** Depends on a sampling seed and a packing algorithm; the sampling design becomes load-bearing |
| **Computational cost** | Highest. Many small units multiply `reduceRegion` calls | Moderate. ~80 candidates × 22 periods ≈ 1,800 reductions | Moderate | Moderate |

**A — equal-area hexagonal tessellation.** The strongest option on the narrow
criterion of area comparability, and genuinely attractive for variance
comparability in the placebo distribution. Rejected on three counts. No standard
resolution lands near project scale, so cells must be aggregated and the
aggregation rule becomes a free parameter. Cells are arbitrary with respect to
ecoregion, country and land tenure, so a cell that is 40% reservoir or spans two
forest-law regimes is admitted by construction and must then be filtered back
out by ad-hoc homogeneity rules — reintroducing exactly the discretion the
tessellation was supposed to remove. And a hexagon is not a place: the report
would name comparison regions no reviewer can check against local knowledge,
which undercuts the arguability the simplex constraint exists to protect.

**C — ecoregion ∩ administrative intersection.** Ecologically the most coherent
edge definition, and the first instinct. Rejected because in practice it
shatters districts along ecoregion margins into slivers, and any minimum-area
filter applied afterwards is a tuning knob that materially changes the pool. The
chosen design captures most of the benefit through the ≥50% ecoregion rule
without the fragmentation.

**D — area-matched sampled compact regions.** Perfect area comparability and
superficially the most "scientific". Rejected outright for the prototype: the
sampling seed and the region-growing algorithm become load-bearing scientific
choices, sampled regions can overlap and therefore violate donor independence in
the placebo distribution, and the result is not reproducible by a third party
without reimplementing the packing. For a pre-registered benchmark this is the
worst available property.

**Using the project's own four constituent districts' neighbours only.** Kariba
is reported to span several Zimbabwean districts, which would make the treated
unit a natural union of administrative units and is part of what recommends
option B. Restricting donors to nearby districts was considered and rejected:
the near neighbours are exactly the units most likely to receive displaced
deforestation, so the leakage belt removes them, and a pool drawn only from
Zimbabwe is too small and too exposed to a single national policy shock.

## Consequences

**Easier.** The donor pool becomes a deterministic function of six pinned public
datasets plus one registry boundary. #3 and #23 now have a specification to build
against rather than a question to answer. The leakage belt and the protected-area
exclusion both become expressible as geometric tests that populate
`excluded_unit_ids`, which is currently dead. Donor tables name real districts
that a reviewer with regional knowledge can challenge.

**Harder.** Districts are unequal in size, so the area band will reject
candidates that are otherwise good matches, and the count is not knowable in
advance. Belt exclusion removes the nearest and therefore best-matched
neighbours, which will worsen covariate balance against the 0.25 SMD guideline —
a tension between two rules that both point the right way, with no resolution
beyond reporting both.

**Accepted — administrative endogeneity.** District boundaries are drawn along
rivers, roads and settlement patterns, which correlate with deforestation
pressure. Units are therefore not exchangeable in the way a randomised design
would require. This is mitigated, not solved, by matching on road distance and
population density, and the residual is a limitation to state in the report. The
alternative designs do not eliminate this confounding; they redistribute it into
units that are harder to reason about.

**Accepted — carbon-project contamination.** Other registered REDD+ projects in
the search region are treated units, but public geometry for them is largely
unavailable. Where a project is known to be present in a district without
geometry, the district is excluded whole, which is conservative and lossy. Where
a project is unknown to the Berkeley database, it contaminates the pool
undetected. This is a real and unquantified limitation of the prototype.

**Accepted — J versus T₀.** The pre-period is 10 years and fixed by
pre-registration. A pool sized for placebo resolution (40–50 donors gives a
smallest attainable p-value of 0.024–0.020) guarantees J > T₀, so the donor
weights are not uniquely identified. The counterfactual path and the effect
estimate remain well determined; `fit.weights_identified` already reports this
and the assembler already warns. The trade is deliberate: inference resolution is
worth more here than weight attribution, because the headline claim is about
divergence, not about naming comparison regions. Shrinking the pool to restore
identification would push the smallest attainable p-value to 0.09 against a 0.10
gate, which is worse. See #56.

**Accepted — dilution.** The estimate is a boundary-wide mean effect, diluted by
the treated fraction of the project area. It must not be reported as a local
intensity of change.

**Cost.** Roughly 80 candidates plus the project over 22 annual periods is on the
order of 1,800 zonal reductions over large polygons, plus five covariate
reductions per unit. This does not fit in an HTTP request and confirms the
worker and job lifecycle (#24, #25) as prerequisites for the Kariba run, not
optional infrastructure. Caching by dataset ref plus extent (ADR-009) makes
re-runs cheap.

## Revisit when

- The measured candidate count at rung 1 falls below 80, or admitted donors fall
  below 30 — the area band and the ≥50% ecoregion rule are the first parameters
  to re-examine, and any change must be recorded as a specification-curve point
  rather than a replacement headline.
- A second case with a different ecosystem reaches this stage. Mikoko Pamoja is
  ~117 ha of mangrove; administrative districts are absurd at that scale and it
  will need its own unit rule. This ADR is explicitly scoped to
  landscape-scale terrestrial cases.
- Project boundaries with per-activity geometry become available, making a
  treated-fraction correction possible and the dilution caveat unnecessary.
- `UnitRef.attributes` gains string support, at which point the exclusion
  provenance should move out of `unit_id` and into the unit itself.
