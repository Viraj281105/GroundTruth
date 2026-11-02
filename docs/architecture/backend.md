# Backend architecture

**Owner: Bhumi.** `packages/groundtruth/src/groundtruth/platform/`

The platform is everything that turns a computational module into an
application: serving it, persisting it, scheduling it, feeding it, and keeping
it up.

---

## Modules

| Module | Responsibility | Status |
| --- | --- | --- |
| `api/` | FastAPI app, request/response schemas, validation, error mapping | Implemented. `/verify` is synchronous; `/runs` reads stored runs; `/jobs` submits, polls and cancels |
| `cases/` | Case registry, YAML loading, translation to `AnalysisRequest` | Implemented |
| `datasets/` | Dataset registry, version pinning, credentials, caching, `DataAccess` implementations | Synthetic only |
| `jobs/` | Analysis lifecycle: queue, claim, heartbeat, retry, cancel | Implemented; used by `/jobs` and the worker |
| `store/` | Evidence and provenance persistence, run history | Implemented; read by `/runs`, not yet written by the API |
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
  → [POST /jobs only] enqueue  jobs/   (#24, #37)
  → run_analysis            the contract
  → [via the worker] persist   store/  (#15)
  → generate report         reports/
  → project to response     api/schemas.py
```

`/verify` still runs everything inline and stores nothing. `POST /jobs` queues the same analysis for the worker, which persists it (#37); `/runs` reads it back (#35). The `/verify` response shape will not change
when they move behind a job, which is why `run_id` and `spec_hash` are already
in the response today.

## The API schema is the frontend's contract

The frontend's TypeScript types are generated from the OpenAPI schema (#17). The
served `/openapi.json` and the committed snapshot `apps/web/src/lib/generated/openapi.json`
are built by one function, `platform/api/openapi_schema.py`, so they are always the same.

**After changing any response model, request model or route: run `make api-types` and
commit the two generated files.** CI fails otherwise: `tests/test_openapi_snapshot.py`
catches a stale schema, and the web job's `npm run check:api-types` a stale TypeScript.

One adjustment is made to FastAPI's output: every property of a schema used only in
responses is marked required, because FastAPI always sends every field of a response
model. Request schemas and FastAPI's own validation-error schemas are left exactly as
generated. Error responses are documented too (`MessageErrorBody`, `EngineFailureBody`),
including `/verify`'s 422, which is either a validation error or an engine refusal.

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
(`platform/store/`, needs the `db` extra). The stored-run endpoints (#35) read from
it; the API does not write to it yet: `/verify` still runs analyses inline and saves
nothing; `POST /jobs` (#37) queues work for the worker, which writes. No analysis of a real project has been run.

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

## Stored-run endpoints

**Status:** implemented (#35), read-only, on simulated data only. They read what the
worker and the evidence store recorded. They run nothing and write nothing; submitting
and polling jobs is `/jobs` (#37), and `/cases/{id}/verify` is unchanged (it still runs
inline and stores nothing).

| Endpoint | Does |
| --- | --- |
| `GET /runs` | List runs, newest first, in pages. Filters: `case_id`, `status` (repeatable), `engine_version`, `data_mode`, `created_after` (inclusive), `created_before` (exclusive). `limit` 1 to 100, default 25. |
| `GET /runs/{run_id}` | One run: lifecycle, outcome, error, and the evidence bundle (`include_bundle=false` leaves it out). |
| `GET /runs/compare?baseline=&candidate=` | A per-evidence-id diff of two runs, or the reasons they cannot be compared. `include_unchanged=true` lists unchanged ids too. |

Browse them at `/docs` while the API is running. Dates must carry a timezone; write UTC
with a trailing `Z`. A `+` in an offset must be URL-encoded (`%2B`), or use `Z`.

### Pagination

By cursor, not offset. The listing is ordered by `(created_at, run_id)` descending, and
both values are fixed when a run is created, so a cursor stays valid however many runs
are written, or change status, afterwards. New runs sort above the cursor and never shift
or repeat a later page. The query is `WHERE (created_at, run_id) < (:t, :r) LIMIT n+1`:
the extra row says whether another page exists, so there is no `COUNT` (it would be slow,
and stale as soon as it was read).

- **The cursor** is an opaque token holding the last position and a fingerprint of the
  filters it was issued for. Reusing it with different filters is `400 invalid_cursor`.
  It is not signed: forging one only moves where the page starts.
- **One honest limit:** a run whose transaction commits late can carry a `created_at`
  older than a position a reader already passed. It is missing from that scroll and
  appears in the next. It can never cause a duplicate or a reordering.
- **Indexes** (migration 0004) end in `run_id`, so each page is an index range scan with
  no sort: `(case_id | status | engine_version | -, created_at, run_id)`. A filter on
  several statuses still uses the status index but has to sort.

### What a run looks like

`status` is the job; `result_state` is what happened to the analysis, in the UI's
`ResultState` vocabulary:

| `result_state` | When |
| --- | --- |
| `queued`, `running` | The job has not finished. No bundle yet. |
| `measured` | The engine completed. |
| `refused` | The engine declined to estimate. **A successful job**: `status` is `succeeded`, the response is `200`, and `error` carries the code, stage, message, remediation and detail with `is_refusal: true`. |
| `failed` | An engine error (`error` is set), or a failure before the engine ran (`failure_reason` says why, cut to 300 characters). |
| `cancelled` | Cancelled before it produced evidence. |

**C5 note for the frontend:** the UI's `ResultState` has five values (`not_started`,
`running`, `measured`, `refused`, `failed`). The API adds two: `queued` (a kind of
"running" to a display) and `cancelled`. See [frontend.md](frontend.md). A stored
refusal's `error.detail` is returned here, which `/verify` does not do.

Every run object carries `data_mode` and `is_simulated` (never optional), and a simulated
run carries a `notice`. Pages and comparisons carry `contains_simulated`. A listing or
comparison therefore cannot present a simulated run as observed (R7).

### Comparing

Each evidence id is `added`, `removed`, `changed` or `unchanged`. A change lists the fields
that moved, each with before and after: `value`, `unit`, `confidence` (bounds, level and
kind), `qualifiers`, and the provenance fingerprint (so the same number derived a
different way is flagged). Rewording a `label` is not a change. Numbers compare with a
relative tolerance of 1e-9, because ADR-006 guarantees identical results for the same
engine, spec and seed but not bit-exact floating point across machines. The response also
carries a neutral verdict diff (the two labels, and whether they differ; nothing is
ranked) and the warnings that appeared or disappeared.

**NOT COMPARABLE.** `comparable: false`, every reason listed, and **no diff at all**.
There is no override. A difference across engine versions might be the method and not the
project, and presenting it as a change would be a measurement artefact in front of a
due-diligence team.

| Reason | When |
| --- | --- |
| `different_case` | the runs are for different cases |
| `different_data_mode` | one simulated, one observed |
| `different_engine_version` | the engine versions differ (R8) |
| `different_contract_major` | incompatible contract versions |
| `contract_unreadable` | a run was written under a contract this code cannot read |
| `no_bundle` | a run has no evidence: refused, failed, queued or cancelled. The message says which, and for a refusal, why. |

A different `spec_hash` is **not** a reason: re-running the same method on updated data is
what monitoring compares. It sets `same_specification: false`. The diff logic is
`platform/compare/` (pure, no database), reusable by monitoring.

### Errors and when there is no database

Errors use `detail: {code, message, hint}`, the shape `/verify` already uses for engine
failures. They are `ApiErrorCode` in `platform/api/errors.py`, not the contract's
`ErrorCode`, because they describe retrieval and not analysis.

| Code | HTTP |
| --- | --- |
| `run_not_found` | 404 |
| `invalid_cursor` | 400 |
| `invalid_filter` (a date without a timezone, or an empty range) | 422 |
| `contract_version_mismatch` (fetching one run the code cannot read; the comparison endpoint reports it as a reason instead) | 409 |
| `store_not_configured` (no `DATABASE_URL`, the `db` extra not installed, or a schema behind the migrations) | 503 |
| `store_unavailable` (the database is not answering) | 503 |
| `store_error` (stored data is inconsistent) | 500 |

The store is built lazily by `get_store()` on the first `/runs` request and kept. A failed
attempt is not remembered, so fixing the configuration needs no restart. `/health`,
`/cases` and `/verify` never touch it and keep working with no database. Tests inject a
store with `app.dependency_overrides[get_store]`.

## Job endpoints

**Status:** implemented (#37), on simulated data only.

> **No authentication yet.** None of these endpoints, nor any other endpoint of this
> API, is authenticated. Anyone who can reach the API can queue, poll and cancel jobs, and
> every job is a database row and CPU time for the worker. That is acceptable on a laptop
> and **must not be exposed publicly until authentication, authorisation and rate limiting
> are added.** Treat it as a blocker for any public deployment.

| Endpoint | Does |
| --- | --- |
| `POST /jobs` | Queue a simulated analysis for a case and return at once. Body: `case_id`, `synthetic` (default true), `min_donors` (default 10). |
| `GET /jobs/{run_id}` | A job's status and progress, cheap enough to poll. `Cache-Control: no-store`. |
| `POST /jobs/{run_id}/cancel` | Stop a job. |

Results and history are `/runs`; `/jobs` is the lightweight thing a UI polls. Try them at
`/docs`.

### Polling, not streaming

The state lives in the database, so a client asks for it. About once a second is plenty (a
Kariba run is seconds), it works through any proxy without long-held connections, and the
response says when to stop: `terminal` is true. Server-sent events would hold a server
thread per viewer on this synchronous app, need proxy buffering switched off, and are
the usual source of flaky stream tests; they can be added later without changing anything
here.

### Submitting

- **`202`**: a new job was queued. **`200`**: nothing new was queued, because a stored
  result already answers this exact request (`from_cache`) or an identical job is already
  in flight (`deduplicated`); `run_id` is that existing run. This is the `spec_hash` cache
  and de-duplication from #24, unchanged.
- The case is stored first (as `groundtruth submit` does), the request is built exactly as
  `/verify` builds it, with the configured seed, and `data_mode` is `simulated`.
- `synthetic: false` is `501`. It is never quietly simulated.
- **There is no `true_effect` field, and sending one is a `422`.** It is not part of the
  specification hash, so accepting it would let two different simulations share one cached
  answer. (The worker has its own `--true-effect`.)
- The response embeds the full `JobView`, labelled `is_simulated` with the simulated
  `notice`, including on a cache hit.
- **Engine-version assumption.** The cache lookup uses the engine version of the *API*
  process, while the job runs on whichever *worker* picks it up. They are the same while
  both deploy from one image (ADR-010). If they ever differ, a submit could be answered
  from, or queued for, a different engine version than the worker runs.

### What progress can honestly show

`run_analysis` is one uninterruptible call that reports its own timings only when it
returns. So there are two kinds of information, labelled by where they come from, and
**no percentage anywhere**. A test fails if a field is named like one.

| Kind | What | When |
| --- | --- | --- |
| `stages` (observed live) | `claim`, `data`, `engine`, `record`, each `done`, `active`, `pending`, `skipped`, `failed` or `unknown`, with start and finish times | As they happen. The active stage has `elapsed_ms`, time spent so far, never a fraction of the total. `record` is one database transaction, so it claims no duration. |
| `engine_metrics` (from `RunMetrics`) | The engine's own total time, unit, donor and fit counts, and where it stopped | Only after the engine returns. Before then `available` is false and nothing is estimated. |

- **The engine reports its internal stage timings** (`observation`, `matching`,
  `alignment`, `estimation`, `robustness`, `assembly`) **only for a completed analysis.**
  A refusal or error gets the total time, the counts and `stopped_at`, with an empty
  `stages` list and a note saying why. None are invented. Having the engine report timings
  on a refusal too would be an engine change.
- `stages` come from `jobs.stage` and `jobs.stage_log` (migration 0005), written by the
  worker in the same transaction as its lease renewal at each checkpoint, and in
  `complete()` for `record`. A worker that lost its lease cannot write them. A retry clears
  them, so a job waiting to run again does not show the failed attempt's progress. A job
  with no recorded stages (an older row, or a result saved directly) shows `unknown`, not
  a guess.
- `last_heartbeat_at` and `lease_expires_at` show the worker is alive. The heartbeat is
  coarse (a third of the lease, about 100 seconds by default).
- The worker's identity is not exposed.

### A refusal is a completed job

`status` is `succeeded`, `result_state` is `refused`, `terminal` is true, `error.is_refusal`
is true, and every stage is `done`. It is never `failed`. `result_state` comes from the one
function that `/runs` uses, so the two endpoints cannot disagree. `queued` and `cancelled`
extend the UI's `ResultState` (see [frontend.md](frontend.md)).

### Cancelling

| Job is | Response | What happens |
| --- | --- | --- |
| queued | `200`, `cancelled` | Cancelled at once; no worker will start it. |
| running | `202`, still `running`, `cancel_requested: true` | The worker's heartbeat sees the request. It stops at its next checkpoint, or the result is discarded when the engine returns, and the job ends `cancelled`. The engine itself cannot be interrupted. |
| already cancelled, or cancel already requested | the same answer again | Idempotent. |
| succeeded or failed | `409 job_already_finished` | Nothing changes. |
| unknown | `404 run_not_found` | |

### Errors and when there is no database

New codes, in the `detail: {code, message, hint}` shape: `job_already_finished` 409,
`case_not_found` 404, and `not_implemented` 501 (the contract's code and status, as
`/verify` uses). With no database every job endpoint answers `503`
(`store_not_configured` or `store_unavailable`), exactly as `/runs` does; `/health`,
`/cases` and `/verify` are unaffected.

## Jobs

**Status:** the job lifecycle library is implemented (`platform/jobs/`, #24). `POST
/jobs` and `groundtruth submit` queue a job and the worker (`apps/worker`, #25) runs it;
see [Job endpoints](#job-endpoints).

See [ADR-008](../decisions/ADR-008-analysis-jobs.md). A database-backed queue, no
broker: a job is its `analysis_runs` row (the one status) plus a `jobs` row (attempts,
lease, cancellation), so jobs survive a restart.

| Call | Does |
| --- | --- |
| `JobQueue.submit(request)` | Returns a stored result (`from_cache`), an identical job in flight (`deduplicated`), or a new QUEUED job |
| `claim(worker_id)` | Reaps expired leases, then takes the oldest available job |
| `heartbeat(job)` | Renews the lease; reports a pending cancel |
| `checkpoint(job, stage)` | Honours a pending cancel between stages |
| `complete(job, result)` / `fail(job, reason, retryable=)` | Records the outcome |
| `cancel(run_id)` / `status(run_id)` | Cancel; poll |
| `process(queue, job, resolve_access)` / `process_next(...)` | One data, engine, record step for a claimed job; the worker's loop body |

```
QUEUED  → RUNNING | CANCELLED
RUNNING → SUCCEEDED | FAILED | QUEUED (retry) | CANCELLED
SUCCEEDED, FAILED, CANCELLED are terminal
```

Rules it enforces:

- **A refusal is a SUCCEEDED job** with engine status `refused`, never FAILED.
- **Every status change is a conditional write** (`WHERE status = <expected>`), so a
  lost race is reported, not silently doubled.
- **Claiming is one statement that writes first.** SQLite takes its write lock before
  reading; PostgreSQL picks the job `FOR UPDATE SKIP LOCKED` and re-checks the status
  under the row lock. Only the SQLite path is exercised in tests; the PostgreSQL
  statement is rendered and checked, not run.
- **Leases are stored** (`jobs.lease_expires_at`, default 5 minutes) and fenced by
  worker id *and* attempt number: a worker whose job was reclaimed gets
  `LeaseLostError` and cannot write. Workers should heartbeat every lease/3, from a
  thread, because `run_analysis` blocks.
- **Retries** only for `DATA_UNAVAILABLE`, `DataUnavailableError` and expired leases;
  everything else is deterministic and fails at once. Backoff is
  `min(30 s × 2^(attempt−1), 15 min)`, three attempts by default, measured from the
  failure. Only the final attempt's result is stored.
- **Cancellation is cooperative.** A queued job cancels at once; a running one at its
  next checkpoint: before data access, before the engine, or after it (the result is
  then discarded). `run_analysis` itself cannot be interrupted.
- **The engine's `run_id` is replaced** by the job's, which callers already hold.
  Nothing else in a result refers to it.
- **The request is stored with the run** (`analysis_runs.request`) and its `spec_hash`
  re-checked on claim, so a job runs exactly what was submitted even if the case file
  changed. A job whose stored request is unusable fails for good.
- **A cached answer is the existing run.** No new run is created for a cache hit.

## What stays simple

| Simple today | Until |
| --- | --- |
| No database | Results must survive a restart |
| Synchronous analysis | Real EO calls push a request past ~10s |
| No auth | Exposed beyond a demo |
| No caching layer | `spec_hash` lookups actually cost something |
| Single environment | There is a second one |

Each is a small change *because* the contract already carries what it needs.
