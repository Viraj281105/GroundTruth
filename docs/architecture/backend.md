# Backend architecture

**Owner: Bhumi.** `packages/groundtruth/src/groundtruth/platform/`

The platform is everything that turns a computational module into an
application: serving it, persisting it, scheduling it, feeding it, and keeping
it up.

---

## Modules

| Module | Responsibility | Status |
| --- | --- | --- |
| `api/` | FastAPI app, request/response schemas, validation, error mapping | Implemented (synchronous) |
| `cases/` | Case registry, YAML loading, translation to `AnalysisRequest` | Implemented |
| `datasets/` | Dataset registry, version pinning, credentials, caching, `DataAccess` implementations | Synthetic only |
| `jobs/` | Analysis lifecycle: queue, claim, heartbeat, retry, cancel | Not built |
| `store/` | Evidence and provenance persistence, run history | Not built |
| `storage/` | Artifacts, exports, generated reports | Not built |
| `reports/` | Deterministic rendering, grounded GenAI narration | Renderer only |
| `config.py` | Environment-driven settings | Implemented |

## The one rule

The platform consumes the engine through the contract and nothing else:

```python
from groundtruth.contracts import AnalysisRequest, AnalysisResult
from groundtruth.engine import run_analysis
```

Four names total. Enforced by `tests/test_contract_boundary.py`. Importing
`groundtruth.engine.causal.synthetic_control` from here would couple deployment
code to an estimator internal, and is a build failure.

## Request lifecycle

```
HTTP request
  → validate                api/schemas.py, Pydantic at the boundary
  → load case               cases/registry.py
  → translate               case.to_request() — pins datasets, drops known_reference
  → resolve data access     datasets/access.py
  → [planned] enqueue       jobs/
  → run_analysis            the contract
  → [planned] persist       store/
  → generate report         reports/
  → project to response     api/schemas.py
```

Steps marked planned currently run inline. The response shape will not change
when they move behind a job, which is why `run_id` and `spec_hash` are already
in the response today.

## Error handling

Every `ErrorCode` maps to an HTTP status in `api/app.py::ERROR_STATUS`, and a
test asserts the mapping is total so a new code cannot silently become a 500.

The response body carries the structured error, not a message string:

```json
{ "code": "donor_pool_inadequate", "message": "...", "stage": "matching",
  "is_refusal": true, "remediation": "...", "run_id": "run_..." }
```

`is_refusal` is the field that matters to the UI. A refusal is the system
correctly declining to produce a fragile number, and must be rendered as a
legitimate outcome rather than an error.

## Configuration

All settings come from the environment through `Settings` (pydantic-settings).
Secrets are `SecretStr` and never logged. `groundtruth doctor` reports whether a
credential is present, never its value.

Repository-relative paths are discovered by walking up for a marker directory
rather than counting parents — a lesson from the monorepo move, which silently
broke a parent count.

## Persistence

**Status:** the schema, migrations and the evidence store are implemented
(`platform/store/`, needs the `db` extra). Nothing calls the store yet: the API
still runs analyses inline and saves nothing, and wiring it in belongs to the job
lifecycle (#24) and the result APIs (#35). No analysis of a real project has been
run.

| Table | Holds |
| --- | --- |
| `cases` | Project definitions, currently YAML |
| `analysis_runs` | run_id, case_id, spec_hash, status, engine version, timings |
| `evidence_bundles` | Bundle JSON + contract version + indexed projections |
| `datasets` | Pinned references and retrieval metadata |
| `jobs` | Queue state, attempts, heartbeat, cancellation |

Bundles are stored as documents with a few indexed projections for listing.
Fully normalising them would be premature; the object is already shaped for a
document column.

Bundles are **immutable** — a re-run is a new `run_id`, never an update. That is
what makes result history and monitoring diffs possible. A database trigger
rejects any `UPDATE` on `evidence_bundles`, so this holds for code that bypasses
the ORM too.

Choices worth knowing before building on the schema:

- `analysis_runs.status` is the **only** job status. `jobs` holds queue mechanics
  (attempts, lease, heartbeat, cancellation) and no status of its own, so the two
  cannot disagree.
- A refused run has no bundle. Its structured `AnalysisError` is stored on the run
  (`error`, `error_code`), because a refusal is a result to persist and show.
- `dataset_refs` on a run is a snapshot of the pinned datasets it used; the
  `datasets` table is the registry.
- `is_simulated` must equal `data_mode = 'simulated'`; the database refuses a row
  that says otherwise (R7).
- `status` and `data_mode` have `CHECK` constraints. `engine_status`,
  `verdict_label` and `error_code` deliberately do not: adding an enum member is a
  minor contract bump and must not force a database migration.
- `load_bundle` refuses a bundle written under a newer minor or a different major
  contract rather than rendering it under the wrong rules.
- Foreign keys have no ORM `relationship()`, so SQLAlchemy does not order inserts
  for you: write the case row, then the run, then the bundle, flushing between.
  `SqlEvidenceStore` does this.
- `analysis_runs.engine_contract_version` (revision 0002) is the contract the engine
  build targets, separate from the version the result is stamped with. It is
  nullable because no row existed before the store; the store always writes it and
  refuses to read a run without it.

### The evidence store

Callers depend on `store/interface.py` (`EvidenceStore`), which needs no database
library; `store/sql.py` (`SqlEvidenceStore`) is the implementation. The interface is
deliberately narrow so the backend can change:

| Method | Does |
| --- | --- |
| `save_result(result)` | Writes a finished result once, run and bundle in one transaction |
| `by_run_id(run_id)` | The exact `AnalysisResult` that was saved, or `None` |
| `by_spec_hash(hash, *, data_mode, engine_version)` | The most recent finished result for a specification |
| `list_for_case(case_id, ...)` | `RunSummary` rows, newest first, from indexed columns only |

Rules it enforces:

- **Written once.** A second `save_result` for a `run_id` raises `DuplicateRunError`
  and changes nothing; a re-run is a new `run_id`.
- **The case comes first.** `upsert_case(case)` mirrors a case file into `cases`.
  `save_result` raises `UnknownCaseError` rather than invent a case from a result,
  which carries no name or country. The stored case leaves out `known_reference`.
- **A refusal is a whole result.** It has no bundle row; its `AnalysisError` lives
  on the run and `by_run_id` rebuilds the full `AnalysisResult`. A refused run is a
  `succeeded` job. An engine `error` is stored as a `failed` job.
- **Most recent** means latest `created_at`, set by the store at microsecond
  precision (SQLite's own clock ticks once a second). A tie is broken by `run_id`,
  descending: arbitrary but stable, so the same query always answers the same way.
- **`data_mode` and `engine_version` are required keywords** on `by_spec_hash`, with
  no defaults. Without the first, a simulated result could answer an observed
  request (R7); without the second, an older engine's result could be served as the
  current one's (R8: the spec hash does not include the engine version).
- **Only finished runs are returned** (completed or refused). A refusal is
  deterministic, so it is a valid cached answer; an engine error is not.
- **Contract version is checked on read**, on the run row as well as the bundle
  (a refusal has none). An unreadable newest match raises
  `IncompatibleBundleError`; it never falls back to an older run.
- `started_at` and `finished_at` must be timezone-aware ISO-8601, as the engine
  writes them; anything else is refused rather than guessed.

The store writes *finished* results. Taking a queued run to a terminal state is the
job layer's operation (#24).

```bash
pip install -e "packages/groundtruth[db]"
export DATABASE_URL=postgresql+psycopg://user:password@host/dbname   # driver is a deployment choice
alembic -c packages/groundtruth/alembic.ini upgrade head
alembic -c packages/groundtruth/alembic.ini downgrade base
```

Never edit a migration that has been applied; add a new revision. A major contract
bump needs a data migration for stored bundles (see `OWNERSHIP.md`, C1).

## Planned: jobs

See [ADR-008](../decisions/ADR-008-analysis-jobs.md). A database-backed queue
first, a real broker only when volume justifies it. `spec_hash` gives
idempotency and caching; determinism makes retries safe.

## What stays simple

| Simple today | Until |
| --- | --- |
| No database | Results must survive a restart |
| Synchronous analysis | Real EO calls push a request past ~10s |
| No auth | Exposed beyond a demo |
| No caching layer | `spec_hash` lookups actually cost something |
| Single environment | There is a second one |

Each is a small change *because* the contract already carries what it needs.
