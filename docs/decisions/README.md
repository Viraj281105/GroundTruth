# Architecture decision records

An ADR records a decision that was expensive to make and would be expensive to
reverse. It captures the context and the alternatives, so that a year from now
nobody has to reconstruct the reasoning from the code.

## What gets an ADR

Write one when a decision:

- constrains how future work must be structured,
- would be costly to reverse,
- was genuinely contested, or
- will otherwise be re-litigated every few months.

Do **not** write one for a library choice with no downstream consequence, a
naming convention, or anything already settled by an existing ADR.

## Status values

| Status | Meaning |
| --- | --- |
| Proposed | Under discussion, not yet binding |
| Accepted | In force. Code should comply. |
| Superseded | Replaced by a later ADR, which must be named |
| Deprecated | No longer applies; nothing replaced it |

An accepted ADR is never edited to change the decision. Write a new one that
supersedes it, so the history of reasoning stays intact.

## Index

| ADR | Decision | Status |
| --- | --- | --- |
| [001](ADR-001-monorepo-structure.md) | Monorepo with one Python distribution | Accepted |
| [002](ADR-002-engine-platform-boundary.md) | Split engine and platform by an enforced contract | Accepted |
| [003](ADR-003-analysis-contract.md) | `AnalysisRequest` / `AnalysisResult` as the interface | Accepted |
| [004](ADR-004-evidence-object.md) | Evidence bundle as the unit of scientific output | Accepted |
| [005](ADR-005-provenance-model.md) | Mandatory provenance on every value | Accepted |
| [006](ADR-006-reproducibility.md) | Reproducibility via `spec_hash` and declared seeds | Accepted |
| [007](ADR-007-genai-boundary.md) | GenAI strictly downstream, grounding enforced in code | Accepted |
| [008](ADR-008-analysis-jobs.md) | Analyses as asynchronous jobs, typed results not exceptions | Accepted |
| [009](ADR-009-data-management.md) | Pinned dataset references, data out of git | Accepted |
| [010](ADR-010-deployment.md) | Containerised API and worker, deferred until MVP | Proposed |

## Template

```markdown
# ADR-NNN: Title

**Status:** Proposed | Accepted | Superseded by ADR-XXX
**Date:** YYYY-MM-DD
**Deciders:** Viraj, Bhumi

## Context
What situation forced a decision. Include constraints that were real at the time.

## Decision
What we chose, stated so someone can comply with it.

## Alternatives considered
What else was on the table and why it lost. This is the most useful section a
year later.

## Consequences
What becomes easy, what becomes hard, what we accept.

## Revisit when
The concrete trigger that should reopen this.
```
