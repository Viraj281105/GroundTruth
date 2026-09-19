# Worker architecture

**Owner: Bhumi.** `apps/worker/`

**Status: NOT BUILT.** The entrypoint prints a not-implemented message and exits
non-zero. Analyses currently run synchronously inside the API process.

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
while True:
    job = queue.claim()                    # platform.jobs
    request = job.to_request()             # platform.cases
    data = resolve_access(request)         # platform.datasets
    result = run_analysis(request, data)   # the contract, unchanged
    store.persist(result)                  # platform.store
    job.complete(result)
```

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
| Cancellation | Cooperative: the worker checks a cancel flag between stages |
| Failure | A crash is `AnalysisStatus.FAILED`; a refusal is `SUCCEEDED` with `EngineStatus.REFUSED` |
| Observability | Structured logs carrying run id, case id and stage |

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
