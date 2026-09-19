# ADR-002: Split engine and platform by an enforced contract

**Status:** Accepted
**Date:** 2026-09-19
**Deciders:** Viraj, Bhumi

## Context

Two people build GroundTruth with an intentional ~60/40 split: Viraj owns the
analytical engine and the user-facing experience, Bhumi owns the platform that
makes it a deployable application.

The original layout was organised by technical concern — `causal/`, `api/`,
`reporting/`, `ingestion/` — which left no seam where one person's work ended
and the other's began. The API reached directly into the pipeline module and
constructed engine providers itself. Under that structure the ownership split
was a social convention, and social conventions do not survive a deadline.

A second, independent motivation: the engine should behave as a reproducible
computational module. Anything that reads a config file, opens a socket or
touches a database is not reproducible in the sense that matters for a
scientific claim.

## Decision

Three top-level packages with a one-directional dependency graph:

| Package | Owner | Rule |
| --- | --- | --- |
| `contracts/` | shared | Imports neither side. Versioned. Changes need both owners. |
| `engine/` | Viraj | Pure computation. No filesystem, network, credentials or database. |
| `platform/` | Bhumi | May import exactly four names from the engine: `run_analysis`, `describe_engine`, `engine_ref`, `ENGINE_VERSION`. |

Enforced by `tests/test_contract_boundary.py`, which walks the AST of every
module and fails on:

- `contracts/` importing either side,
- `engine/` importing the platform, or importing `os`, `pathlib`, `httpx`,
  `requests`, `socket`, a database driver or `ee`,
- `platform/` importing any engine submodule or any name outside the four.

## Alternatives considered

**Convention plus code review.** Free, and works until the first deadline.
Rejected because the failure is silent and cumulative: one `from
groundtruth.engine.causal.synthetic_control import ...` in the API, merged on a
busy day, and the engine can no longer be refactored without breaking the app.

**Dependency-injection framework.** Heavier than needed. The engine takes one
extra argument (`DataAccess`); a container adds indirection without adding
enforcement.

**Split by topic instead of ownership** (`geospatial/`, `causal/`, `evidence/`,
`genai/` as the top level, roughly the shape a reader might first expect). This
groups code by what it is *about* rather than who owns it. Rejected because the
boundary that matters operationally for this team is the ownership one: a
topic-based split still leaves the API importing an estimator directly. Topics
remain as subpackages inside `engine/`, which is the right level for them.

**Separate repositories.** See ADR-001.

## Consequences

**Easier:** the two workstreams move independently; the engine is unit-testable
with fixtures and has no environment; the platform can swap providers, add
caching or move to a worker without touching methodology; a new contributor can
be pointed at one package.

**Harder:** the engine cannot read configuration or log to a shared sink, so
everything it needs must arrive in the request or through a port. That is the
point, but it does mean a new engine input is a contract change rather than an
environment variable.

**Accepted:** the boundary is enforced by a test, not by the import system. See
ADR-001 consequences.

## Revisit when

A third workstream appears, or the four-name public API of the engine proves too
narrow in a way that cannot be solved by extending the contract.
