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
| Implemented | `/health`, `/cases`, `/cases/{id}`, `/cases/{id}/verify` (synchronous) |
| Planned | Async job submission, result listing, pagination, auth |
| Future | Registry-scale batch endpoints, webhooks, API keys |

See [`docs/architecture/api.md`](../../docs/architecture/api.md).
