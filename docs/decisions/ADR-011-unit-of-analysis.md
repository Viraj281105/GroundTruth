# ADR-011: The unit of analysis is a masked administrative district

**Status:** Proposed
**Date:** 2026-09-20
**Deciders:** Viraj, Bhumi

## Context

Nothing in this repository defines what *one unit* is. `UnitRef` carries an
optional geometry, an optional centroid and an optional area. The only donor
source that exists returns the strings `donor-000 … donor-N` from a fixture
generator. `DonorSpec.leakage_belt_km` is carried into every request and read by
no code at all. `excluded_unit_ids` is the other half of the same rule and is the
opposite case: `match_donors` reads it and records a spillover reason for every
id in it, but nothing ever puts an id there — the case registry copies
`excluded_donor_ids` from the case YAML, where it is an empty list with a comment
saying to populate it with districts inside the leakage belt. The consumer exists
and the producer does not, because the producer needs a definition of a district.

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

The treated unit is constructed by the **same mask**, substituting the registry
boundary for *d*:

```
unit(project) = registry_boundary(VCS 902)
        ∩ target_ecoregions
        ∩ baseline_forest
        ∖ permanent_water
        ∖ protected_areas
        ∖ registered_carbon_projects ∖ {this case}
        ⊖ inward_buffer(300 m)
```

Applying the same mask to both sides is the point. A treated unit that includes
its reservoir shoreline and protected-area overlap while donors exclude theirs
is not comparable to them, and no amount of covariate matching repairs that.

**Masking is symmetric; admission is not.** These are two different things and
conflating them produces an empty treated unit. Precisely:

| Operation | Applied to donors | Applied to the project |
| --- | --- | --- |
| Ecoregion, baseline-forest, water, protected-area, buffer geometry | Yes | Yes, identically |
| Subtraction of registered carbon projects | Yes | Yes, **excluding the case under test itself** |
| Leakage-belt exclusion | Yes — a candidate intersecting the belt is dropped | No — the project is the origin of its own belt |
| ≥50% ecoregion rule, area band, 500 km² floor | Yes | No — these decide *which candidates are admitted*, and the treated unit is not a candidate |

The carve-out in row two is not a convenience. Without it the project is
subtracted from itself and `unit(project)` is empty. The layer subtracted from a
unit is *other* registered projects: for the treated unit, every registered
project except VCS 902; for a candidate district, every registered project
without exception.

**A district split by the mask stays one unit.** The mask will cut most
districts into several disconnected pieces. All pieces are retained as a single
multipolygon carrying one `unit_id`, one zonal series and one eligible area.
There is no minimum fragment size, no dropping of slivers and no splitting of a
district into several donors — each of which would be a post-hoc knob, and the
last of which would put two dependent polygons in a placebo distribution that
assumes they are distinct units.

**Order of operations is fixed as written.** The intersections and subtractions
are applied first, in any order (they commute), and the inward buffer is applied
**last, to the masked geometry** — so edges introduced by the mask (a reservoir
margin, a park boundary) are eroded exactly as the outer boundary is. This is
deliberate: a mixed pixel at a water edge is the same measurement problem as a
mixed pixel at a district edge. It is also the more aggressive of the two
readings, and it means eligible area depends on how fragmented the mask is, so
it must be stated rather than left to the implementer.

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

That argument is in tension with the one made for districts over hexagons, and
the tension is not resolved, only priced. Districts are preferred partly because
policy, tenure and enforcement operate at district level — but the 2015 geography
is not the geography of the 2001–2010 pre-period, and in Zambia in particular the
district map was substantially subdivided after 2011. So the claim that survives
is the weaker one: district boundaries follow the rivers, roads, settlement
patterns and administrative history that *also* shape forest-law enforcement, and
are therefore a better-motivated partition than an arbitrary tessellation — not
that each unit corresponds to one governing authority throughout the window.

### Eligibility and exclusion rules

Each rule is an *eligibility* rule, applied before any distance is computed, and
each records a human-readable reason — in the unit-set manifest for rules that
fire before covariates are computed, on `DonorMatch.exclusion_reason` for rules
that fire inside `match_donors`. See "Where exclusions are recorded" below.

| Rule | Threshold | Why |
| --- | --- | --- |
| **Ecoregion** | ≥ 50% of the district's baseline-forest area falls in a target miombo ecoregion | A donor from a different biome is not a counterfactual for miombo |
| **Protected areas** | Any WDPA polygon with `STATUS_YR ≤ 2000`, **including `STATUS_YR = 0`**, and with `STATUS` in the designated/inscribed/established set, is subtracted. `STATUS = "Proposed"` and `"Not Reported"` are not subtracted | A protected area is itself a conservation intervention; a control drawn from one estimates the project effect *relative to another intervention*. A proposal is not an intervention |
| **Registered carbon projects** | Subtracted where geometry exists. Where a registry record places a project inside a candidate district but no geometry exists, the district is excluded whole. "Inside" means the registry's own point location falls in the district — not a judgement about where a project probably is | Another credited project is a treated unit in disguise |
| **Leakage belt** | District excluded entirely if it intersects the 10 km belt. The belt is a 10 km outward buffer of the **unmasked** registry boundary, computed before any mask is applied | Displaced deforestation makes a neighbour a treated unit in disguise. Buffering the masked geometry instead would grow the belt into the mask's holes and exclude districts for the wrong reason |
| **Permanent water** | JRC GSW occurrence ≥ 90% over the full record, subtracted uniformly with no per-unit exception | Water pixels carry no vegetation signal and would swamp a zonal NDVI mean |
| **Area band** | Eligible area within [⅓×, 3×] the project's **eligible** area | See "Why area comparability matters" below |
| **Minimum absolute area** | Eligible area ≥ 500 km² | Below this the zonal mean is dominated by composition rather than condition |

Protected status and carbon-project status are **exclusions, not covariates**,
restating the rule already in #3, #23 and `docs/data/sources.md`.

Two of those rows were ambiguous in the first draft and are pinned here because
each of them silently changes how much land is subtracted.

**`STATUS_YR = 0` means unknown, not year zero.** A non-trivial share of WDPA
records carry it. Both available treatments are lossy: subtracting an
unknown-year area may remove land that was ordinary woodland throughout the
pre-period, while keeping it may admit a post-2000 intervention as a control.
The rule chosen is to subtract, because contaminating the pool with another
intervention biases the estimate while losing eligible area only costs
precision, and because the same rule applies to the project. The cost is
recorded in `docs/science/limitations.md`.

**Which registered projects are known is a pinned fact, not a search.** The
consolidated registry snapshot, its download date and the resulting list of
excluded districts are committed before the pool is generated. Deciding after
the fact that a particular district "probably contains a project" is exactly the
discretion this ADR exists to remove, in either direction.

### Why the mask must not condition on outcomes

The baseline forest mask is Hansen `treecover2000`, and the protected-area filter
is `STATUS_YR ≤ 2000`. Both are deliberately drawn from before the pre-period
begins in 2001. That is the strictest case; the general rule, and the two layers
that do not meet it, are set out at the end of this section.

Masking with a contemporary land-cover product instead — ESA WorldCover, which
exists only for 2020–2021 — would condition on a **post-treatment outcome**. It
would remove precisely the pixels that were deforested during the study window,
which is the signal the analysis exists to measure, and it would do so
asymmetrically between a protected project and unprotected donors. The bias runs
in the direction of manufacturing a project effect.

Conditioning on a *pre-treatment* covariate is legitimate and is what matching
already does. Conditioning on a post-treatment **outcome** is not. The
distinction that matters is not the date on the file but whether the variable
could have been affected by the treatment: a post-2000 land-cover product is an
outcome and is disqualified, while a post-2000 record of *other interventions*
is not, and is used deliberately below. This is the reason ESA WorldCover
appears in `docs/data/sources.md` for stratification but must not be used to
build units. The input-by-input audit is in "Exact inputs required"; two of the
seven layers are not dated before 2001 and each is admitted for a stated reason.

The same discipline applies to the matching covariates, which this ADR does not
own: a present-day road network or population raster used to match on
"pre-treatment" access is the same error one stage later. That is #23's to
resolve, and it is named here so it is not lost between the two.

The same logic applies to WDPA: a park gazetted in 2015 must not be subtracted,
because its land was ordinary woodland throughout the pre-period and possibly
protected in response to the same pressures the project responded to.

Permanent water is the one place where the strict pre-2001 rule is not met, and
the first draft resolved it with a clause — *use the pre-period epoch where a
water body could plausibly have changed* — that was itself a researcher degree
of freedom. "Plausibly" is a judgement made per unit, after looking, and it
changes eligible area and therefore the area band.

**The rule is therefore uniform and unconditional: JRC GSW `occurrence ≥ 90%`
over the collection's full record, applied identically to every unit, project
and candidate alike, with no per-unit exception.** The occurrence band spans
1984–2021 and so does extend past the treatment date. Two things bound the
damage. A 90% occurrence threshold over a 38-year record is close to a
"permanent water throughout" test: a body that appeared in 2015 reaches at most
about 18% occurrence and is not subtracted. And the Kariba reservoir, the one
large water body that matters for this case, was impounded in 1958, decades
before the window.

The residual is real and is recorded rather than assumed away: where a water
body did become permanent inside the window, this mask removes pixels whose NDVI
fell for a reason unrelated to the project, which is post-treatment conditioning.
It applies symmetrically, but symmetry is not neutrality — it removes a genuine
decline from whichever side it occurs on, and on a donor that biases the
counterfactual path upward. Computing occurrence over a 1984–2000 epoch from the
same collection's yearly history would remove the residual entirely and is the
first change to make if this rule is ever revisited.

### Geometry operation parameters

Every rule above is a geometric or raster operation, and each one has parameters
that change the resulting eligible area — and therefore the area band, the 500
km² floor, and which districts are admitted. A rule whose parameters are left to
the implementer is not pre-registered, however precisely its threshold is
written. They are split here into what this ADR fixes and what must be fixed,
and committed, before the pool is generated.

**Fixed here.**

| Parameter | Value |
| --- | --- |
| Order of operations | Intersections and subtractions first, inward buffer last, applied to the masked geometry |
| Inward buffer | 300 m, applied to every edge of the masked geometry including mask-induced edges |
| Fragmentation | All fragments retained as one multipolygon; no minimum fragment size |
| Leakage belt | 10 km outward buffer of the unmasked registry boundary |
| Baseline forest | Hansen `treecover2000 ≥ 30%` |
| Permanent water | JRC GSW `occurrence ≥ 90%`, full record |
| Protected areas | WDPA `STATUS_YR ≤ 2000` including `0`, designated/inscribed/established only |
| Ecoregion admission | ≥ 50% of the district's baseline-forest area in a target ecoregion, evaluated on the district before any subtraction |
| Area band | `[⅓×, 3×]` the project's eligible area, measured after the full mask |
| Absolute floor | Eligible area ≥ 500 km² |

**Must be fixed and committed before the run — and before any candidate count is
seen.** None of these is a scientific choice, which is exactly why they are easy
to set late and after looking. Setting any of them after a count is known is a
protocol violation, not a tuning step.

| Open parameter | Why it changes the pool |
| --- | --- |
| The projection used for every buffer and area computation | A 300 m buffer and a 500 km² threshold are meaningless without one, and a geographic-CRS buffer distorts with latitude across three countries |
| Raster scale and reducer used to turn `treecover2000`, GSW and the ecoregion layer into a mask, and the pixel/vector convention at boundaries | Sub-pixel handling at edges moves eligible area by a few percent, which moves borderline districts across the band and the floor |
| Geometry simplification tolerance (`maxError` in Earth Engine) | Silently changes computed areas and can change topology on a fragmented mask |
| Exact `ECO_NAME` strings for the target ecoregions at each rung | The ladder is only auditable if the rung contents are literal values, not prose names |
| The pinned WDPA release string and the registry-snapshot date | Both layers move month to month |
| `min_donors` and `max_donors` for this run | See the ladder below |

This table is a gate. While it has entries, the unit set is not reproducible from
the ADR alone, and the pre-registered run may not start. Resolving it is
implementation work belonging to #3 and #23; the values land in the unit-set
manifest described under "Reproducibility requirements", not in this ADR.

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

**Contract limitation found while writing this — filed as #60.**
`UnitRef.attributes` is typed `dict[str, float]`, so it cannot carry the country
code, the ecoregion name, the GAUL name or the construction rule — all of which
a reviewer needs to read a donor table. The prototype encodes the source and
code in `unit_id` and accepts the loss. Carrying string descriptors is a contract
change requiring both owners and a version bump, so it is out of scope here;
#60 holds the decision, including whether descriptors enter `spec_hash`. This
ADR depends on that issue only for *legibility* — a donor table that says
`gaul2015:40765` instead of `Binga, Zimbabwe` is harder to challenge but is not
a different pool — so #60 does not block the Kariba run, and the `unit_id`
encoding above becomes a compatibility note once #60 lands.

**Where exclusions are recorded.** The rules above say each exclusion carries a
human-readable reason, and the obvious home for it is
`DonorMatch.exclusion_reason`, which already exists. It cannot hold all of them.
`match_donors` only ever sees candidates that reached it, so it can record the
leakage-belt, caliper and coverage exclusions but never the eligibility ones: a
district failing the ecoregion, area-band or floor rule is dropped during
candidate generation, before covariates are computed, and `DonorCandidateAccess`
returns bare `UnitRef`s with nowhere to put a reason. Computing covariates for
ineligible districts purely to give them a `DonorMatch` row would be wasteful
and would still not be the same thing.

The eligibility-stage exclusions therefore belong in the **unit-set manifest**
below, not in the `DonorPool`. Both records are part of the evidence bundle and
a reader needs both: the manifest says why a district never became a candidate,
`DonorPool.excluded` says why a candidate was not admitted.

**Within-unit dispersion is not carried, deliberately.** #57 asked this ADR to
take a position. A unit is observed as a single zonal series — one mean per unit
per period — and the estimator needs nothing else. `ZonalStats` already computes
`std`, `p10` and `p90`, and `TimeSeries` has nowhere to put them; it carries
`n_valid_observations` per period, which is what the coverage rule needs. The
position here is that dispersion is a **diagnostic** and not an input: a large
within-unit spread means the zonal mean summarises a heterogeneous unit, which is
worth reporting next to a donor and is the reason the 500 km² floor exists, but
adding a channel for it is a contract change with no estimator behind it yet.
Deferred to #60's discussion of what travels with a unit; not decided here.

### Search-region ladder

The candidate count is not knowable before the data is pulled, and "widen the
search until enough donors appear" is exactly the kind of post-hoc freedom the
pre-registration forbids. The expansion is therefore fixed in advance as an
ordered ladder.

| Rung | Search region |
| --- | --- |
| 1 | Southern Miombo + Central Zambezian Miombo woodlands, in ZWE, ZMB, MOZ |
| 2 | Rung 1 + Eastern Miombo woodlands + Zambezian–Mopane woodlands |
| 3 | Rung 2 + the same ecoregions in MWI and TZA |

**The stopping rule.** The first draft said "take the first rung yielding ≥ 80
candidates" and, separately, that a shortfall of *admissible* units at rung 3
refuses the case. Those are two different counts, and leaving both in the text
leaves the escalation decision open: an analyst who finds 84 eligible candidates
at rung 1 but only 14 admitted donors could argue either that the ladder stopped
at rung 1 or that it should continue. That is a post-hoc choice that changes the
donor pool, so it is closed here.

The ladder is climbed on a **single criterion, evaluated in order, with no
discretion at any rung**:

> Advance to the next rung if and only if the current rung yields fewer than
> `pool_size` eligible candidates **or** fewer than `min_donors` admitted
> donors. Stop at the first rung that satisfies both. Use that rung's pool.

Both conditions are mechanical. Eligible candidates are districts surviving the
eligibility rules above; admitted donors are what `match_donors` returns after
the caliper, coverage and leakage rules, which requires covariates to have been
computed at that rung. Climbing therefore costs a covariate pass per rung, which
is the price of a rule with no judgement in it.

Two things must be recorded in the evidence bundle regardless of where the
ladder stops: **both counts at every rung climbed, including rungs that were
passed**, and the rung finally used. A reader who can see that rung 1 gave 84
candidates and 14 donors while rung 2 gave 120 and 46 can check that the rule was
followed; a reader shown only the final pool cannot.

`pool_size`, `min_donors` and `max_donors` are the numbers this rule turns on,
and they are not set here. `DonorSpec` defaults to `pool_size = 60`,
`min_donors = 10`, `max_donors = 50`; the Kariba case sets `donor_pool_size: 80`
and the pre-registered plan says "up to 50 admitted from 80+ candidates". The
effective `min_donors` for this run is therefore the contract default of 10
unless the case definition overrides it — and 10 donors puts the smallest
attainable permutation p-value at 1/11 ≈ 0.091 against a 0.10 gate, which is a
design that can only ever just barely clear its own threshold. **All three
values must be written into `cases/kariba-redd.yaml` before the run**, with the
consequence for attainable p-values stated alongside them. Deciding the refusal
threshold after seeing how many donors survived would make the refusal rule
decorative.

If the ladder reaches rung 3 and still fails either condition, `match_donors`
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

**Release date is not reference year.** A dataset published before the analysis
was run tells you nothing about whether the variable it encodes is
pre-treatment. Each input is audited on the date that actually matters:

| Input | Release / version | Reference period of the variable | Pre-treatment for a 2011 treatment date? |
| --- | --- | --- | --- |
| GAUL level 2 | 2015 edition, frozen | Administrative geography as of 2014–15 | **Not by date.** Admissible because a partition is not an outcome: it is not caused by the project and is not on the causal path. The cost is boundary drift, recorded under Consequences |
| RESOLVE Ecoregions | 2017 publication | Biogeographic classification, effectively time-invariant over the window | Yes, in substance |
| Hansen `treecover2000` | 2023 release, v1.11 | Canopy cover in the year **2000** | Yes. The band is a year-2000 state re-processed in a later release; the release changes precision, not the reference year |
| JRC GSW `occurrence` | GSW 1.4 | **1984–2021**, spanning the window | **No.** Handled explicitly under permanent water above |
| WDPA | Monthly release | Designation years filtered to ≤ 2000, but **boundaries as currently held** | Partly. A park designated in 1975 whose boundary was extended in 2018 is subtracted at its current extent, so a slice of the subtraction is post-treatment. Small, symmetric, and recorded |
| Registered carbon projects | Snapshot date, pinned | Projects registered up to the snapshot, i.e. mostly post-2011 | **Deliberately not pre-treatment.** This layer excludes units that became treated *during or after* the window, which is the point: a unit credited in 2016 is not a clean control for 2011–2022. Excluding on a post-treatment fact is correct when the fact is *other treatment*, not outcome |

Only two rows are clean by date alone. The rest are admissible for a stated
reason, and the ADR is weaker than its first draft claimed: the mask is
**pre-treatment in the ways that matter for outcome conditioning**, not
uniformly dated before 2001.

Three quantities must be **measured and recorded before the pre-registered run**,
because the design's viability depends on them and none can be asserted from a
desk:

1. The project's eligible area after masking, which sets the area band.
2. The candidate count at each rung of the ladder.
3. The number of districts lost to the leakage belt.

**WDPA is a monthly release and is not archived publicly for long.** Pinning
`version` to a release string is necessary but not sufficient for a re-run a year
later. The mitigation is the unit-set manifest below.

### Reproducibility requirements

ADR-006 states the guarantee: same `spec_hash`, same seed, same engine version
and same pinned datasets yields identical output. **That guarantee does not
currently cover the unit set**, and this is the one gap in this design that is
not a limitation to accept but a requirement to implement.

`spec_hash` is a digest of `AnalysisRequest`. When the platform embeds resolved
candidates in `donors.candidates`, their geometries are hashed and the guarantee
holds. When `donors.candidates` is empty, the engine asks
`DonorCandidateAccess` for them, and **nothing about how those units were built
enters the request or the hash** — not the eligibility thresholds, not the
buffer, not the projection, not which rung was used. Two runs that constructed
different units from the same rules would share a `spec_hash` and appear to have
reproduced each other. That is worse than an unreproducible number, because it
is an unreproducible number wearing a reproducibility check.

The fix is a **unit-set manifest**: the generated unit set is materialised as a
committed artifact under `data/manifests/`, pinned as a `DatasetRef` like any
other input so it enters the request and therefore the hash. A result is then
reconstructable from the manifest plus the request, and the manifest is itself a
reviewable data product — the trigger ADR-009 names in its "Revisit when".

The manifest must carry, at minimum:

| Field | Why |
| --- | --- |
| Registry boundary: path, source URI, retrieval date, geometry hash | The treated unit's origin (#2) |
| Every input `DatasetRef`: id, **version**, provider, asset, and the **reference year or epoch of the variable**, distinct from the release date | Release date and observation date are different facts, and only the second one decides whether the input is pre-treatment |
| Every eligibility threshold and every parameter from the tables above, including the resolved open parameters | The rules, as executed rather than as documented |
| Leakage-belt radius and the belt geometry hash | The exclusion that removes the best-matched neighbours |
| Rung reached, and candidate and admitted counts at every rung climbed | The one place the ladder could have been gamed |
| `pool_size`, `min_donors`, `max_donors` as used | The refusal rule's own parameters |
| Per unit: `unit_id`, geometry hash, eligible area, fragment count, and for excluded districts the rule that excluded them | The eligibility-stage exclusions that cannot live on `DonorMatch` |
| Engine version, contract version, git SHA, generation timestamp | ADR-006 |

A reviewer holding the manifest, the pinned refs and the git SHA can rebuild the
unit set without asking anyone a question. A reviewer holding only the evidence
bundle cannot, which is why the manifest is a prerequisite for the pre-registered
run and not a follow-up.

## Alternatives considered

| | **A. Equal-area hex (H3)** | **B. Masked admin district** *(chosen)* | **C. Ecoregion ∩ admin** | **D. Area-matched sampled regions** |
| --- | --- | --- | --- | --- |
| **Project-area comparability** | Best. Exact by construction, though no H3 resolution lands near 7,850 km² — res 3 is ~12,400 km², res 4 ~1,770 km², so cells must be aggregated | Good. Same order of magnitude; band enforces it | Poor. Fragments into very unequal slivers | Best. Exact by construction |
| **Ecoregion / habitat similarity** | Poor. Cells straddle ecoregion and biome boundaries arbitrarily | Good after masking and the ≥50% rule | Best. Ecoregion is a defining edge | Good, if sampling is ecoregion-constrained |
| **Administrative boundaries** | Ignored. A cell can span three countries with different forest law | Aligned, with a caveat. Land tenure, allocation and forestry enforcement genuinely vary at district level, so units differ on the dimension policy operates on — but on the *2015* geography, which had already drifted from the 2001–2010 pre-period and has drifted further since | Aligned | Ignored |
| **Leakage exclusion** | Clean. Belt intersection is a simple geometric test on regular cells | Workable but blunt. A district is large, so belt intersection excludes the whole unit | Workable | Clean |
| **Donor count** | High and tunable by resolution — which is itself a researcher degree of freedom | Adequate; ladder makes expansion mechanical | Unpredictable after a minimum-area filter | Unlimited, which is a warning sign not a feature |
| **Satellite aggregation** | Uniform pixel counts per unit; attractive for variance comparability | Acceptable; area band bounds the variance spread | Poor. Sliver units have few pixels | Uniform |
| **Covariate availability** | All five covariates are raster-derived, so any polygon works | Same. Census-derived covariates would attach more naturally than to a hexagon, but only where the census geography still matches GAUL 2015 — the five covariates in use are raster-derived anyway, so this is not a live advantage | Same | Same |
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
`excluded_unit_ids`, which currently has a reader and no writer. Donor tables name real districts
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

**Accepted — the treated unit is not drawn from the donor population.** Donors
are administrative districts; the treated unit is a registry polygon. They are
masked identically and banded on area, but they are not the same kind of object:
a project boundary is drawn around an intended intervention, a district boundary
is not. The in-space placebo assumes the treated unit is exchangeable with the
donors under the null, and that assumption is weaker here than the area band
alone suggests. Building the treated unit from the union of the districts it
spans would fix the object mismatch and break something more important — the
estimate would no longer be *of the project* — so the mismatch is accepted and
reported. It is a reason to read the placebo p-value as a screening statistic
rather than a test with a calibrated size.

**Accepted — donors are spatially autocorrelated and share national shocks.**
Adjacent districts share weather, markets, roads and a government. The
permutation p-value needs exchangeability rather than independence, so this does
not invalidate it, but a reference distribution built from correlated units has
fewer effective units than its count suggests, and a country-level shock in the
post-period moves many donors together. The ladder makes this worse before it
makes it better: rung 1 is the most ecologically comparable and the most
spatially concentrated. Reporting the country composition of the admitted pool
is the minimum mitigation, and is one of the descriptors #60 exists to carry.

**Accepted — a 9× spread inside the area band.** `[⅓×, 3×]` admits units
differing by nearly an order of magnitude, so pixel counts and therefore the
noise in an annual zonal mean still vary substantially across the pool. The
RMSPE *ratio* normalises each unit against its own pre-period fit, which absorbs
much but not all of this. The band is a bound on the problem, not a solution to
it; eligible area and valid-pixel count per donor are recorded so a reviewer can
see the spread rather than infer it.

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
- `UnitRef.attributes` gains string support (#60), at which point the descriptors
  should move out of `unit_id` and into the unit itself.
- The permanent-water rule is revisited, at which point occurrence over a
  1984–2000 epoch replaces the full-record mask and removes the one post-treatment
  layer in the mask.
- A reviewer challenges the placebo p-value's calibration. The treated unit is
  not the same kind of object as its donors, and if that becomes load-bearing
  the answer is a different inference procedure, not a different unit rule.
