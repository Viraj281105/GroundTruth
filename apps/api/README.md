# apps/api

The HTTP service. **Owner: Bhumi.**

A thin ASGI entrypoint over `groundtruth.platform.api`. Keeping the deployable
surface separate from the library means the container image, the process model
and the health checks can change without touching application code.

```bash
uvicorn apps.api.main:app --reload --port 8000   # http://localhost:8000/docs
```

| Status | |
| --- | --- |
| Implemented | `/health`, `/cases`, `/cases/{id}`, `/cases/{id}/verify` (synchronous); `GET /runs`, `/runs/{run_id}`, `/runs/compare` (stored runs: cursor pagination, filters, comparison; need `DATABASE_URL`) |
| Also implemented | `POST /jobs` (queue a simulated analysis), `GET /jobs/{run_id}` (status and per-stage progress, poll it), `POST /jobs/{run_id}/cancel`. **No authentication yet: do not expose publicly.** |
| Planned | Case management (#36), authentication |
| Future | Registry-scale batch endpoints, webhooks, API keys |

See [`docs/architecture/backend.md`](../../docs/architecture/backend.md).
