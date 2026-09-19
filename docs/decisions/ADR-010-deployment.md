# ADR-010: Containerised API and worker, deferred until MVP

**Status:** Proposed
**Date:** 2026-09-19
**Deciders:** Viraj, Bhumi

## Context

GroundTruth needs to be reachable for the competition demo and, later, by
people who are not us. It has three deployable surfaces: an HTTP API, a
background worker, and a static-ish frontend.

It also has an unusual runtime profile for a web application. An analysis is a
CPU-bound numerical workload of seconds to minutes, not a millisecond request.
That rules out several defaults — serverless functions with short timeouts, and
any model where the request handler does the work.

The pressure to pick a host now is real, and mostly premature. The decision
worth making now is the *shape*; the target can wait.

## Decision — shape

**Two containers from one image.**

```
apps/api      uvicorn, N workers, short request timeouts
apps/worker   queue consumer, long timeouts, CPU headroom
```

One image with two entrypoints rather than two images: the dependency set is
identical, and divergence between them is a class of bug worth designing out.

**The frontend deploys separately** as a static/SSR build, talking to the API
over HTTPS. It shares nothing with the Python runtime.

**Configuration is entirely environment variables**, read through
`platform.config.Settings`. No config files baked into an image, no secrets in
the repository. `configs/` holds non-secret per-environment overrides when there
is more than one environment.

**Stateless containers.** All state lives in the database and object storage, so
a container can be replaced at any moment. This is what makes the worker
retry-safe, and it is cheap to hold to because runs are deterministic (ADR-006).

**Health endpoints already report capability honestly** — `/health` states what
is genuinely implemented, which doubles as a readiness probe and as a deployment
smoke test.

## Decision — deferral

**Nothing is built yet.** `infrastructure/` contains a README explaining the
shape and no manifests. Placeholder Dockerfiles and deployment YAML that nobody
runs would rot within weeks and mislead the next reader about what works.

The trigger to build it is the MVP: the first real Kariba run, which needs the
worker anyway.

## Alternatives considered

**Deploy now, iterate.** Tempting for demo safety. Rejected: there is nothing to
deploy that a local `uvicorn` does not already do, and the API surface will
change substantially when jobs land. Building the pipeline twice is worse than
building it once at the right moment.

**Serverless functions.** Attractive operationally. Rejected on runtime profile:
analyses exceed typical timeouts, cold starts on a numpy-heavy image are poor,
and the worker is inherently long-lived.

**A single container running API and worker.** Fewer moving parts. Rejected: a
CPU-saturating analysis would starve request handling, and the two scale on
different axes.

**Kubernetes.** Disproportionate for two people. Two containers and a managed
database is the correct size, and the container shape means moving to
Kubernetes later is a manifest, not a rewrite.

## Consequences

**Easier:** local development stays `uvicorn` and a venv, with no container
required to contribute; the deployment decision is reversible because nothing
depends on it yet.

**Harder:** there is no staging environment, so integration problems surface
later than they would otherwise.

**Accepted:** the demo runs locally until the MVP. Given the pipeline runs fully
offline with no credentials, that is a low-risk position — see
`docs/competition/demo-flow.md`.

## Revisit when

The worker lands, or someone outside the team needs access. Both arrive at the
MVP, and this ADR should move to Accepted with a named target at that point.
