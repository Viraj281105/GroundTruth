# GitHub conventions

How work is tracked. The aim is that anyone can tell, from the issue list alone,
what is being worked on, by whom, and why it matters.

---

## Labels

### Ownership — exactly one

| Label | Meaning |
| --- | --- |
| `owner:viraj` | Analytical engine or user-facing product |
| `owner:bhumi` | Platform, data services, infrastructure, operations |
| `owner:shared` | Requires both — usually a contract change |

### Priority — exactly one

| Label | Meaning |
| --- | --- |
| `P0` | Blocking a real result. Nothing else matters more. |
| `P1` | Completes the story. Needed for the stage to be credible. |
| `P2` | Productisation. Valuable, not load-bearing. |

### Feature area — one or more

`frontend` · `backend` · `data` · `geospatial` · `causal` · `evidence` ·
`genai` · `infrastructure` · `research` · `testing` · `docs`

### Type — one

`feature` · `bug` · `architecture` · `research` · `documentation` · `chore`

### Special

| Label | Meaning |
| --- | --- |
| `contract` | Touches `contracts/`. **Requires both owners on the PR and a version bump.** |
| `scientific-integrity` | Touches a guard that must not regress |
| `blocked` | Waiting on another issue or an external dependency |
| `coordination` | One of the eight named coordination points in `OWNERSHIP.md` |

## Milestones

| Milestone | Exit criterion |
| --- | --- |
| **M1 Foundation** | Structure, contract, docs, database, UI skeleton, CI |
| **M2 Core pipeline** | Real Earth-observation data flowing through the engine |
| **M3 Product** | End to end from UI click to rendered evidence |
| **M4 Validation** | Kariba run, reviewed and published whatever it says |
| **M5 Demo & production** | Deployed, monitored, hardened, rehearsed |

A milestone closes when its exit criterion is met, not when its issues happen to
be finished.

## Issue anatomy

Every issue states:

1. **What** — the deliverable, concretely
2. **Why** — what it unblocks, or what breaks without it
3. **Acceptance criteria** — checkboxes someone else could verify
4. **Dependencies** — issues that must land first
5. **Parallel** — whether it can run alongside its peers

Issues touching the scientific engine additionally state **what must remain
true**: the guard, invariant or test the change must not break.

## Pull requests

- Reference the issue
- Fill in the scientific-integrity checklist in the template
- CI green
- A `contract` PR needs both owners and a `CONTRACT_VERSION` bump

## Commits

Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `build:`,
`ci:`, `chore:`. Explain *why* in the body, especially for estimator or
grounding changes. A commit that changes what a number would be should say so
explicitly, and bump `ENGINE_VERSION`.

## Research issues

Research is tracked like code. A research issue states the question, what a
useful answer looks like, and what would change in the implementation depending
on the outcome.

A research issue that cannot say what it would change is a bookmark, and belongs
in `docs/research/` instead.
