# 8. Limitations and assumptions

This document exists because a verification system that does not publish its own
limitations is asking for exactly the trust it claims to be replacing.

## What has not been built

| Component | Status |
| --- | --- |
| Earth Engine observation calls | Not implemented — raises `DataUnavailableError` |
| Real covariate extraction (CHIRPS, SRTM, OSM, WorldPop) | Not implemented |
| Project boundary geometry | Not obtained for any case |
| Biomass / carbon conversion | Not implemented, deliberately |
| GenAI narration providers | Not implemented |
| Any analysis of a real project | **Not run** |
| Validation against the Kariba reference | **Not run** |
| Nugen vs baseline hallucination evaluation | **Not run** |

Everything the pipeline currently produces comes from the synthetic fixture
provider and is marked as simulated in its provenance, its warnings and its
verdict caveats.

## Methodological limitations

### The estimate is on an index, not on carbon

The single largest gap. The pipeline estimates an effect on NDVI or EVI. Claims
are in tCO2e. These are not commensurable, so the verdict correctly returns
`INCONCLUSIVE` rather than manufacturing a comparison. See
[5. Causal inference](causal-inference.md).

### Resolution floor

Annual composites at 10–30 m cannot resolve effects in projects below roughly
1,000 ha, and cannot resolve selective logging or degradation at any scale. The
Mikoko Pamoja case (~117 ha) is included specifically to make this floor visible
rather than letting it be discovered by a user.

### The donor pool determines the answer

Every estimate is conditional on which regions were admitted. A different
plausible candidate region can produce a different estimate. This is why the
pool, its exclusions and its balance statistics are part of the evidence bundle
rather than an implementation detail.

### The unit of analysis is an administrative district

Donors are administrative districts under a pre-treatment eligibility mask
([ADR-011](../decisions/ADR-011-unit-of-analysis.md)). District boundaries are
drawn along rivers, roads and settlement patterns, which correlate with
deforestation pressure, so units are not exchangeable in the way a randomised
design would require. Matching on road distance and population density mitigates
this; it does not remove it.

Two further costs are accepted rather than solved. Excluding every district that
touches the leakage belt removes the nearest and therefore best-matched
neighbours, which works against covariate balance — two rules that both point the
right way, pulling against each other. And the estimate is a boundary-wide mean,
diluted by whatever fraction of the project area actually received activity, so
it must not be read as a local intensity of change.

### The donor pool is not a set of independent units

Adjacent districts share weather, markets, roads and a national government. The
permutation p-value needs the treated unit to be exchangeable with its donors
under the null, not independence, so correlation does not invalidate it — but a
reference distribution built from correlated units carries fewer effective units
than its count suggests, and a country-level shock moves many donors at once.
Related: the treated unit is a registry polygon while every donor is an
administrative district. They are masked identically and banded on area, but a
boundary drawn around an intended intervention is not the same kind of object as
a district boundary. The placebo p-value should be read as a screening statistic,
not as a test with a calibrated size.

### The eligibility mask is not uniformly pre-2001

The mask is built to avoid conditioning on *outcomes*, which is not the same as
every layer predating the window. Two layers do not:

- **Permanent water** is JRC GSW occurrence over 1984–2021. A 90% threshold over
  38 years is close to a "permanent throughout" test, so little post-2000 water
  survives it, but where a body did become permanent inside the window the mask
  removes a genuine decline — on a donor, that biases the counterfactual upward.
- **Protected areas** are filtered to designations dated 2000 or earlier, but
  subtracted at their *current* boundaries, so a post-2000 extension of a
  pre-2000 park is also removed. WDPA records with an unknown designation year
  are subtracted too, which costs eligible area in exchange for not admitting an
  unrecognised intervention as a control.

Both are applied identically to the project and to every donor. Symmetry limits
the damage; it does not make either one neutral.

### Other credited projects may contaminate the donor pool

Another registered carbon project inside a candidate district is a treated unit
in disguise. Public geometry for registered projects is largely unavailable, so
a district known to contain one is excluded whole — conservative but lossy — and
a project absent from the consolidated registry databases contaminates the pool
undetected. This is unquantified.

### Leakage is only partially addressable

If a project displaces deforestation beyond the monitored leakage belt, the
method will not see it and will overstate the project's benefit. Belt exclusion
handles the local case only.

### Anticipation

Project activity often begins during validation, years before the crediting
period. Treating the crediting start as the treatment date then contaminates the
pre-period and biases the estimate toward zero.

### Single treated unit

Permutation inference with $J$ donors has a minimum attainable p-value of
$1/(J+1)$. With 40 donors that is 0.024. The system reports this rather than
implying more precision than the design allows.

### Weight non-identification

With more donors than pre-treatment periods, individual donor weights are not
unique, though the counterfactual path and the effect are. Surfaced as
`fit.weights_identified`.

### Parallel trends is untestable

The DiD cross-check rests on an assumption that cannot be verified, only made
more or less plausible by its pre-period analogue.

## Measurement limitations

| Issue | Effect |
| --- | --- |
| NDVI saturation | Loses sensitivity over closed canopy — real gains invisible |
| Cloud cover | Sparse years in tropical evergreen regions |
| Sensor transitions | Landsat→Sentinel steps mimic land-cover change |
| Tidal state | Mangrove reflectance varies with water level at acquisition |
| Phenology | Different growing seasons make composites non-comparable across units |
| Fire | Burn scars are large index drops that are not land-use change |
| Boundary accuracy | Registry boundaries can be coarse or inconsistent |

## Assumptions the estimates depend on

1. **No interference.** Donors are unaffected by the project.
2. **Convex hull.** The project is spanned by its donor pool.
3. **No anticipation.** Behaviour did not change before the treatment date.
4. **Stable relationship.** Pre-period co-movement persists absent treatment.
5. **Measurement comparability.** The indicator means the same thing across
   units and time.

Each has a mitigation in the pipeline. None has a guarantee.

## What the system must never be used for

- **Alleging fraud.** Divergence is a trigger for review, not a finding.
- **Legal or regulatory decisions.** It is not accredited and not designed for
  evidentiary use.
- **Replacing field measurement.** Ground plots measure pools no satellite sees.
- **Carbon accounting.** It does not issue, retire or price credits.
- **Automated de-listing.** No project should lose status on this output alone.

## Conflicts and independence

GroundTruth has no relationship with any project developer, registry, buyer or
rating agency, and receives no funding contingent on its findings. It is a
student research project built for the PCCOE International Grand Challenge 2026.

The `known_reference` blocks in case definitions record published third-party
findings for post-hoc validation. The pipeline never reads them; a test asserts
that no case claims an analysed status without a reviewed run.

## Where we could be wrong

The honest summary: this method could produce a confident estimate that is
simply incorrect, because the donor pool was inadequate in a way the balance
statistics did not reveal, or because a sensor transition introduced a step that
the pre-period fit absorbed. The mitigations are the placebo suite, the
specification curve and the refusal to report past a failed gate. They reduce
the risk; they do not eliminate it.

That is why the output is a screening signal that recommends accredited review,
and not a verdict.

---

Previous: [7. GenAI grounding](../architecture/genai.md) · Next: [9. Competition strategy](../competition/strategy.md)
