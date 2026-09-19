# ADR-003: AnalysisRequest / AnalysisResult as the engine interface

**Status:** Accepted
**Date:** 2026-09-19
**Deciders:** Viraj, Bhumi

## Context

With the engine/platform boundary established (ADR-002), the interface across it
had to be specified. Requirements:

- the platform must be able to queue, cache, retry and replay an analysis;
- a result must be reproducible months later;
- a long-running analysis must survive a process boundary;
- the frontend must not depend on any Python implementation detail;
- domain failures must be persistable and renderable, not just catchable.

## Decision

One function:

```python
run_analysis(request: AnalysisRequest, data: DataAccess) -> AnalysisResult
```

**`AnalysisRequest` is self-contained.** The engine reads no YAML, no database,
no environment variable and no file. Everything needed to run — and to re-run
identically — is in the object. The platform translates a stored case into a
request via `CaseDefinition.to_request()`.

**`AnalysisResult` is returned for every domain outcome**, including failure,
and is validated so a `COMPLETED` result must carry a bundle and a non-completed
result must carry a structured error.

**A second direction: the DataAccess ports.** The engine declares what data it
needs (`ObservationAccess`, `CovariateAccess`, `DonorCandidateAccess`); the
platform decides where it comes from. This is the seam between methodology and
plumbing — *which* index and *which* covariates is engine; auth, retries,
caching and version pinning is platform.

**The API serves projections of the result over HTTP**, and the frontend
consumes TypeScript generated from the OpenAPI schema. The backend is the
contract layer; the UI never imports a Python shape.

## Alternatives considered

**Engine reads the case file directly.** Simplest to write, and what the code
originally did. Rejected: it makes the engine depend on the filesystem and on
the case-definition format, which puts case management — a platform concern —
inside the engine, and makes a replay depend on the file not having changed.

**Many small engine functions** (`fit()`, `estimate()`, `assemble()`) called by
the platform orchestrator. Rejected: the orchestration *is* methodology — the
order of stages, which robustness checks gate the verdict — so putting it in the
platform would move a scientific decision to the wrong owner.

**Raise exceptions for domain failures.** Conventional Python, and what the code
originally did. Rejected: "this project has no adequate donor pool" is
information the platform must persist, show in the UI, and distinguish from a
crash. An exception crossing a job boundary becomes a stringified message and
loses its structure. `ErrorCode.is_refusal` now separates a correct scientific
refusal from a malfunction, which matters because a refusal is the most valuable
thing this system does and must not be styled as an error.

Programming errors still raise. A bug should fail loudly rather than be recorded
as a scientific refusal.

## Consequences

**Easier:** caching by `spec_hash`; replaying an analysis; testing the engine
with fixture ports; moving execution to a worker without an interface change;
generating frontend types.

**Harder:** adding an engine input means a contract change and a version bump,
not a quick keyword argument.

**Accepted:** the request object is large. That is the cost of being
self-contained, and it is what makes it serialisable and replayable.

## Revisit when

An analysis needs to stream intermediate results (progress, partial evidence)
rather than return once. That would be an additive contract change — a callback
port — not a redesign.
