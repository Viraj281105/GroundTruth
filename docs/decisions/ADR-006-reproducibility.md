# ADR-006: Reproducibility via spec_hash and declared seeds

**Status:** Accepted
**Date:** 2026-09-19
**Deciders:** Viraj, Bhumi

## Context

A published analysis of a real project must be reproducible. If a number cannot
be regenerated, it cannot be defended, and the validation plan — comparing an
independent estimate against a published correction — is meaningless without it.

This became concrete during development. The synthetic data provider seeded its
RNG from Python's builtin `hash()`, which is salted per process. Two runs of the
same test produced different numbers, and it surfaced only as an intermittent
test failure. That bug is exactly the class of problem reproducibility
discipline exists to prevent.

## Decision

**Every stochastic step is seeded from the request.** `AnalysisRequest.seed` is
declared by the platform, carried into `AnalysisResult`, and used by every
component that draws randomness.

**Never seed from `hash()`.** Use `contracts.identifiers.spec_hash` or
`blake2b`. Called out explicitly in `AGENTS.md`.

**`spec_hash` is the reproducibility key.** A deterministic `blake2b` digest of
the request, excluding `requested_by` and `notes` (who asked does not change what
is computed) and excluding `retrieved_at` on dataset references.

> Same `spec_hash` + same `seed` + same `ENGINE_VERSION` + same pinned datasets
> yields identical numeric output.

**Datasets are pinned by the platform**, not chosen by the engine, so a re-run
months later uses the same imagery rather than whatever the provider currently
serves.

**`ENGINE_VERSION` is bumped whenever results could change**, independently of
`CONTRACT_VERSION`. A methodology fix that alters an estimate is an engine bump
even if the interface is untouched.

**Results carry the provenance of their own execution:** run id, spec hash,
engine version, contract version, dataset refs, seed, timestamps and per-stage
timings.

## Alternatives considered

**Record a seed in a config file.** Rejected: config is not carried with the
result, so a replay months later cannot know what was used.

**Hash the whole request including metadata.** Rejected: `requested_by` and a
re-run note would change the hash without changing the computation, which
destroys its usefulness as a cache key.

**Content-hash the input data instead of pinning dataset versions.** A stronger
guarantee. Rejected for now as impractical — hashing a Sentinel-2 archive slice
is not something we can do through Earth Engine. Version pinning is the
achievable approximation, and the gap is documented rather than hidden.

## Consequences

**Easier:** the platform caches on `spec_hash`; validation asserts a replay
reproduces its original numbers; continuous monitoring becomes "re-run the
stored spec and diff the bundles"; a disagreement between two runs is
unambiguously a bug rather than noise.

**Harder:** every new stochastic component must accept a seed. Any dependency
whose RNG cannot be controlled is disqualified.

**Accepted:** reproducibility is guaranteed against the *same* engine version.
Across versions it is not, and should not be — a methodology fix is supposed to
change the answer. That is why the version travels with the result.

## Revisit when

An external reviewer needs bit-exact reproduction across machines and BLAS
implementations. Floating-point associativity makes that a stronger claim than
the one made here.
