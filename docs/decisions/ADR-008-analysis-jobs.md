# ADR-008: Analyses as asynchronous jobs with typed results

**Status:** Accepted
**Date:** 2026-09-19
**Deciders:** Viraj, Bhumi

## Context

Analyses are slow. A placebo suite refits the estimator once per donor, so a
50-donor pool is 51 fits. On simulated data that is under a second; against real
Earth Engine reductions it will be tens of seconds to minutes, and registry-scale
batch screening is hours.

Today an analysis runs synchronously inside the HTTP request. That is fine for a
demo on fixtures and will not survive real data: the request times out, the
worker is blocked, and a failure loses everything computed so far.

The design needed to be settled now even though the implementation is deferred,
because the *result shape* has to support it. Retrofitting job semantics onto an
interface that raises exceptions would mean changing the contract.

## Decision

**Two status vocabularies, defined in the contract, because the job and the
science succeed or fail independently.**

```
AnalysisStatus   queued → running → succeeded | failed | cancelled   (platform)
EngineStatus     completed | refused | error                         (engine)
```

A job can be `succeeded` while its engine status is `refused`. That is the
normal, correct outcome for a project the data cannot support, and it must not
be surfaced as a failed job.

**Domain failures are typed results, not exceptions.** The engine returns an
`AnalysisResult` carrying a structured `AnalysisError` with a machine-readable
`ErrorCode`, a plain-language message, the stage, structured detail and a
remediation hint. Programming errors still raise.

**`ErrorCode.is_refusal` separates science from malfunction.** A refusal is the
system correctly declining to produce a fragile number — the most valuable thing
it does — and the UI renders it as a legitimate outcome with its explanation.
A malfunction is a problem to fix. Conflating them would teach users to dismiss
refusals.

**The worker is a separate process** (`apps/worker/`), consuming jobs from a
queue, invoking the engine through the contract, persisting the bundle and
transitioning status.

**`spec_hash` is the idempotency and cache key.** A job whose spec hash already
has a stored result returns it rather than recomputing.

## Alternatives considered

**Keep everything synchronous.** Simplest. Rejected: it does not survive real
data, and the interface change needed later would be breaking.

**Background tasks inside the API process** (FastAPI `BackgroundTasks`). Cheap,
no queue, no extra deployment. Rejected: state is lost on restart, there is no
cancellation, no retry, no visibility, and a long analysis still competes with
request handling for the same process. Acceptable as a stopgap between now and
the real worker, and documented as such.

**A full workflow engine** (Celery, Temporal, Airflow). Powerful and
disproportionate for two people pre-MVP. The job model here is deliberately
small enough to be backed by a database table first, and to be swapped for a
real broker later without changing the contract.

**Exceptions across the job boundary.** Conventional. Rejected: an exception
becomes a stringified message and loses its structure precisely where structure
is needed — persisting it, rendering it, and distinguishing a refusal from a
crash.

## Consequences

**Easier:** the worker can be built later without an interface change, because
the result shape already supports it; refusals are persistable and renderable;
caching by spec hash is mechanical; retries are safe because runs are
deterministic.

**Harder:** the engine must catch its own domain errors and convert them, which
is explicit code in `run_analysis` rather than exception propagation.

**Accepted:** until the worker lands, analyses run inline and do not survive a
restart. This is a known, documented gap with a 501 on the observed-data path so
nothing misleading is served in the meantime.

## Revisit when

Job volume justifies a real broker, or analyses need to stream progress rather
than report once. Both are additive.
