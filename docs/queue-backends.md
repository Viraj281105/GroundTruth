# Queue backends

GroundTruth ships three ways to run analysis jobs. The default is unchanged.

| Backend | Select by | Module | Extra packages |
|---|---|---|---|
| SQL (default) | nothing | `platform/jobs/queue.py`, `service.py` | none beyond `db` extra |
| Redis + arq | `REDIS_URL` set | `platform/jobs/redis_queue.py` | `redis`, `arq` |
| Temporal (durable execution over the SQL queue) | run a Temporal worker | `platform/jobs/temporal_workflow.py` | `temporalio` |

All heavy packages are imported lazily; a missing one raises an `ImportError` naming the
`pip install` to run. Without them, nothing else in the package is affected.

## Redis + arq

`RedisJobQueue` implements `JobControl` (`submit`, `cancel`, `status`) with the same
semantics as the SQL queue: dedup of identical in-flight requests, result cache
(`from_cache`), immediate cancel of queued jobs, flag-and-checkpoint cancel of running
ones, `LIVE_STAGES` progress (`claim, data, engine, record`) in `stage` and `stage_log`,
and a refusal counted as `succeeded`. Known limits: no lease fencing and read-modify-write
transitions (see the module docstring). The Redis path does not write the case to the SQL
case store.

Wiring a maintainer must add (API composition root, where `SqlJobService` is built):

```python
jobs = select_job_control(lambda: SqlJobService(store, queue))  # from groundtruth.platform.jobs.redis_queue
```

With `REDIS_URL` unset this returns the SQL service unchanged. Worker process (new file,
e.g. `worker_arq.py`), started with `arq worker_arq.WorkerSettings`:

```python
from groundtruth.platform.jobs.redis_queue import redis_url_from_env, worker_settings
WorkerSettings = worker_settings(redis_url_from_env() or "", my_resolve_access)
```

`my_resolve_access` is the same `ResolveAccess` callable the SQL worker uses.

## Temporal

Jobs are still submitted to the SQL queue. After `queue.submit(...)`, start the workflow:

```python
from groundtruth.platform.jobs.temporal_workflow import build_worker, start_analysis
worker = await build_worker(client, queue, resolve_access)   # then: await worker.run()
await start_analysis(client, run_id)
```

The single activity claims the next job and runs the existing `process`, heartbeating. If
the worker dies, Temporal retries the activity and the SQL queue reaps the expired lease
and hands the job back; the retry is safe because nothing is written before the
single-transaction `record` stage. The one-line API wiring is the `start_analysis` call
after submit; nothing else changes.
