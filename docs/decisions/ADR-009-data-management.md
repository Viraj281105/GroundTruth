# ADR-009: Pinned dataset references, data out of git

**Status:** Accepted
**Date:** 2026-09-19
**Deciders:** Viraj, Bhumi

## Context

GroundTruth depends on external Earth-observation products that change. Earth
Engine collections are reprocessed; Hansen Global Forest Change ships a new
version annually; CHIRPS backfills. An analysis that says "Sentinel-2" without
saying *which* Sentinel-2 cannot be reproduced.

Separately, the data itself is large and mostly not redistributable. Annual
composites for one project and eighty donors over twenty years is gigabytes of
raster, and several products are licensed for research use but not
redistribution.

## Decision

**Datasets are pinned by reference, not by name.**

```python
DatasetRef(
    dataset_id="sentinel2-l2a",
    version="2024.1",
    provider="google-earth-engine",
    asset="COPERNICUS/S2_SR_HARMONIZED",
    source_uri=..., retrieved_at=...,
)
```

**The platform pins; the engine never chooses.** Dataset selection is a
plumbing decision with licensing, cost and availability constraints the engine
has no business knowing about. The refs are resolved into the request and
carried through to the result.

**`is_synthetic` propagates automatically.** A ref whose provider is `synthetic`
makes `AnalysisResult.is_simulated` true, which flows to the bundle warnings,
the verdict caveats, the API response and the UI banner. Nobody has to remember
to set a flag, and `AnalysisRequest` refuses to label a synthetic dataset as
observed.

**Data stays out of git.** `data/raw`, `data/interim`, `data/processed` and
`data/external` are gitignored with README placeholders explaining how to
populate them. Rasters, shapefiles and archives are gitignored by extension.

**Cached products are addressed by dataset ref plus spatial and temporal
extent**, so a cache hit is provably the same data rather than the same name.

**Failure raises; it never falls back.** `earth_engine_access` raises
`DataUnavailableError` rather than returning fixtures, because a silent fallback
would let simulated numbers be served under a real-data label.

## Alternatives considered

**Reference datasets by name only** ("Sentinel-2"). Simplest, and what most
published remote-sensing work does. Rejected: it makes reproduction
unverifiable, which is the one thing this project cannot compromise on.

**Vendor the data into the repository.** Guarantees reproduction. Rejected:
gigabytes in git, and several products cannot be redistributed. Fixtures are the
committed data, and they are labelled as simulated.

**DVC or git-lfs.** A reasonable answer for a data-heavy project. Deferred:
there is no committed data to version yet, and adding the tooling before there
is a problem would be exactly the premature infrastructure this foundation pass
is meant to avoid. The `data/manifests` concept is the migration path.

**Content-hash the inputs instead of pinning versions.** Stronger. Impractical
through Earth Engine, where the data is never local. See ADR-006.

## Consequences

**Easier:** a result names exactly what produced it; caching is safe; the
simulated flag cannot be bypassed; the repository stays small and cloneable
without credentials.

**Harder:** every provider must expose a meaningful version, and some do not.
Where a provider has no version concept, the ref records a retrieval snapshot
date and the weakness is visible rather than implied away.

**Accepted:** pinning a version is weaker than hashing the bytes. The gap is
documented in ADR-006 rather than papered over.

## Revisit when

Committed datasets appear (a validated boundary set, a curated donor pool), at
which point `data/manifests/` plus DVC or git-lfs becomes worth its weight.
