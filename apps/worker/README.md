# apps/worker

Background analysis worker. **Owner: Bhumi.** **Implemented on simulated data only.**

Analyses are long-running, so they belong in a separate process from the API. This
entrypoint is deliberately thin; the worker itself is
`groundtruth.platform.jobs.worker`.

From the repository root, with `DATABASE_URL` set (PowerShell shown):

```powershell
$env:DATABASE_URL = "sqlite:///data/interim/groundtruth.db"   # data/interim/ is gitignored
$env:GIT_SHA = (git rev-parse HEAD)                           # recorded on every result
python -m apps.worker.main --migrate --exit-when-idle         # once: create the tables
groundtruth submit kariba-redd --synthetic                    # queue a simulated run
python -m apps.worker.main                                    # run; Ctrl+C to stop
groundtruth job <run_id>                                      # status
```

| Flag | Meaning |
| --- | --- |
| `--migrate` | Apply migrations first. Without it, a database behind the code refuses to start. |
| `--exit-when-idle` | Stop when the queue is empty. |
| `--max-jobs N` | Stop after N jobs. |
| `--poll-seconds S` | Idle wait between looks at the queue (default 2). |
| `--true-effect X` | Effect injected into simulated runs (default 0.06, as the API). |

Ctrl+C (or Ctrl+Break, or SIGTERM) finishes the current job and stops; a second press
stops at once, and the interrupted job is retried after its lease expires.

| Status | |
| --- | --- |
| Implemented | Claim with lease, heartbeat thread, retries, cooperative cancellation, graceful shutdown, JSON logs |
| Not yet | Observed data (#22), submission from the API (#35, #37), containers (#44) |
| Future | Scheduled re-analysis, continuous monitoring, alert evaluation |

See [`docs/architecture/worker.md`](../../docs/architecture/worker.md).
