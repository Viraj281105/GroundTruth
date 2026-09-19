# apps/worker

Background analysis worker. **Owner: Bhumi.** **NOT IMPLEMENTED.**

Analyses are long-running, so they belong in a separate process from the API.
Today they run synchronously inside the API request; that is fine for one case
on simulated data and will not survive real Earth-observation calls.

| Status | |
| --- | --- |
| Implemented | Nothing. The entrypoint prints a not-implemented message and exits non-zero. |
| Planned | Queue consumer, job claim/heartbeat/complete, retry with backoff, cancellation |
| Future | Scheduled re-analysis, continuous monitoring, alert evaluation |

See [`docs/architecture/worker.md`](../../docs/architecture/worker.md).
