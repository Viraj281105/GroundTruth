# ADR-001: Monorepo with one Python distribution

**Status:** Accepted
**Date:** 2026-09-19
**Deciders:** Viraj, Bhumi

## Context

GroundTruth spans a Python analytical engine, a Python backend, a TypeScript
frontend, deployment infrastructure, scientific documentation and experiment
harnesses. Two people own different halves of it, and the long-term intent is a
platform that keeps growing for years.

The repository needed a shape that:

- gives the frontend, backend and worker separate deployable surfaces,
- makes the ownership boundary visible in the directory tree,
- does not impose packaging ceremony on a two-person pre-MVP team,
- can absorb new packages later without restructuring.

## Decision

A monorepo with `apps/` and `packages/`, but **one Python distribution**.

```
apps/api      thin ASGI entrypoint
apps/worker   background job runner
apps/web      Next.js frontend
packages/groundtruth/
  pyproject.toml          the distribution
  src/groundtruth/
    contracts/  engine/  platform/
```

Root `pyproject.toml` holds shared tooling configuration (ruff, mypy, pytest)
and is **not** a distribution, so any package added to `packages/` later is
linted and typed under identical rules.

Module boundaries are enforced by `tests/test_contract_boundary.py`, which
parses the AST of every module and fails the build on a cross-boundary import —
not by packaging.

## Alternatives considered

**Three Python distributions** (`groundtruth-contracts`, `-engine`,
`-platform`). Physically enforces the boundary and would let the engine be
installed standalone by researchers. Rejected for now: three distributions all
providing `groundtruth.*` requires PEP 420 namespace packages, which means no
`groundtruth/__init__.py` anywhere and therefore no top-level convenience API.
The alternative — `groundtruth_engine` as a separate top-level module — produces
ugly imports. Either way it is three `pyproject.toml` files, a more complex
editable install and more CI surface, in exchange for enforcement we already get
from a 40-line test.

**Flat `src/groundtruth/` with no `apps/` or `packages/`.** Where the repository
started. Simplest, but gives the frontend and the deployable entrypoints nowhere
natural to live, and offers no seam for a second package later.

**Separate repositories per component.** Rejected outright. Two people, a shared
contract that changes often, and a need for atomic cross-cutting changes. Split
repositories would mean version-skew coordination overhead for no benefit at
this size.

## Consequences

**Easier:** one install command; one test run; atomic changes across the
contract, engine and platform; the tree communicates ownership; adding
`packages/<name>` later is additive.

**Harder:** the engine cannot yet be `pip install`ed independently, which is a
real cost against the stated goal of it being a reusable computational module.
Accepted for now because there is no external consumer.

**Accepted:** boundary enforcement depends on a test rather than the import
system. If that test is weakened, the boundary is gone — which is why
`AGENTS.md` lists it as a file that must not be changed to make an import pass.

## Revisit when

The engine needs an independent release cadence, an external consumer wants it
without FastAPI in the dependency tree, or a second Python package is added to
`packages/`. Splitting at that point is mechanical, because the module
boundaries are already clean.
