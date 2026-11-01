# Worker architecture

**Owner: Bhumi.** `apps/worker/`

**Status: IMPLEMENTED, simulated data only** (#25). The worker consumes jobs, runs
`run_analysis` and records the outcome. Only simulated jobs can succeed: observed-data
jobs fail because Earth Engine access is not implemented (#22). Nothing submits jobs
from the API yet (#35, #37); `groundtruth submit` queues one from the command line.

```powershell
python -m apps.worker.main --migrate --exit-when-idle   # once: create the tables
groundtruth submit kariba-redd --synthetic             # queue a simulated Kariba run
python -m apps.worker.main                             # run until Ctrl+C
groundtruth job <run_id>                               # status, from any terminal
```

`DATABASE_URL` must be set (there is no default database), and `GIT_SHA` should be,
so results record the commit; unset, it is recorded as null.

---

## Why a separate process

An analysis is a CPU-bound numerical workload. A placebo suite refits the
estimator once per donor — a 50-donor pool is 51 fits. On fixtures that is under
a second; against real Earth Engine reductions it will be tens of seconds to
minutes, and registry-scale batch screening is hours.

Blocking an HTTP worker on that is a design error: the request times out, the
process is unavailable for other work, and a crash loses everything computed.

The API and the worker also scale on different axes — request concurrency versus
CPU throughput — so they belong in separate containers from the same image
(ADR-010).

## Shape

```python
while not stopping:
    job = queue.claim(worker_id)           # reaps expired leases first
    if job is None:
        stop.wait(poll_seconds)            # idle: no busy loop; a stop wakes it at once
        continue
    with Heartbeat(queue, job, lease / 3): # keeps the lease alive while the engine runs
        process(queue, job, resolve_access, run=run_analysis)  # data -> engine -> record
```

The code is `groundtruth.platform.jobs.worker` (loop and heartbeat) and
`groundtruth.platform.jobs.entrypoint` (startup, signals); `apps/worker/main.py` only
calls it, as `apps/api/main.py` does for the API.

The worker calls exactly the same `run_analysis` the API calls today. Moving
execution here requires **no engine change and no contract change** — which was
the point of returning typed results rather than raising (ADR-008).

## Responsibilities

| Concern | Approach |
| --- | --- |
| Claiming | Atomic claim with a lease, so two workers cannot take the same job |
| Heartbeat | Periodic touch; an expired lease returns the job to the queue |
| Retry | Exponential backoff, bounded attempts. Safe because runs are deterministic. |
| Idempotency | `spec_hash` — a job whose spec already has a result returns it |
| Cancellation | Cooperative. Before data access and before the engine, the job is cancelled without running it. During the engine, the heartbeat sees the request and the result is discarded when the engine returns; `run_analysis` itself cannot be interrupted. |
| Failure | A refusal is `SUCCEEDED` with `EngineStatus.REFUSED`. A bug fails that job (`FAILED`, traceback logged) and the worker carries on. A crash leaves the job claimed with nothing written; its lease expires and it is retried, `FAILED` only once attempts run out. |
| Observability | One JSON object per line on stderr, each job line carrying `run_id`, `case_id`, `stage`, `worker_id`, `attempt` and `data_mode` (the engine's own lines too). The database URL is logged with its password masked. |

**The refusal distinction is the thing most likely to be implemented wrongly.** A
project the data cannot support is a *successful job* with a refusal result. If
the worker marks it failed, the UI will show a system error for what is actually
the system working correctly.

## Future

| Capability | Notes |
| --- | --- |
| Scheduled re-analysis | The scheduling half of continuous monitoring |
| Batch screening | Registry-scale, with prioritisation |
| Cheap screening before expensive confirmation | A fast indicator pass to rank what deserves a full placebo suite |
| Alert evaluation | Threshold rules over bundle diffs |

## Prerequisites

The job store and evidence store must exist first — a worker with nowhere to
persist a result has no purpose. Both are Bhumi-owned and scheduled for the MVP.
