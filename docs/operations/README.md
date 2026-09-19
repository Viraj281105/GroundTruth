# Operations

**Status: nothing is deployed.** GroundTruth runs locally. This directory holds
the operational design, so that when deployment happens it is executed rather
than invented under time pressure.

---

## Deployment

See [ADR-010](../decisions/ADR-010-deployment.md). Shape: two containers from
one image (API, worker), a managed database, object storage, and the frontend
deployed separately. Deferred until the MVP, when the worker exists and there is
something worth deploying.

## Observability — planned

| Signal | Approach |
| --- | --- |
| Logs | Structured JSON carrying `run_id`, `case_id` and `stage` |
| Metrics | Analysis duration by stage, queue depth, refusal rate, cache hit rate |
| Traces | Request → job → engine, once the worker lands |
| Alerts | Job failure rate, queue backlog, upstream provider errors |

`JsonFormatter` in `groundtruth.logging` already emits the structured fields.

**The metric worth watching most closely is the refusal rate.** A sudden change
means either the data changed or the method did, and both deserve investigation.
A refusal rate of zero is more suspicious than a high one.

## Runbooks — planned

| Scenario | Response |
| --- | --- |
| Earth Engine quota exhausted | Jobs fail with `data_unavailable`; back off and resume. No partial results are persisted. |
| Worker crash loop | Jobs return to the queue on lease expiry. Determinism makes retries safe. |
| A published result found to be wrong | Mark the run superseded, publish a correction, never silently amend. Bundles are immutable by design. |
| Provider reprocesses a dataset | Pinned `DatasetRef` means old results stay attributable. Re-run under a new pin and compare. |
| Contract version mismatch | The engine returns `contract_version_mismatch`; deploy the matching pair. |

## Incident principles

**Correct the record publicly.** A wrong published result is corrected with a
visible correction, not an edit. The evidence bundle is immutable and a re-run
is a new `run_id` precisely so this is possible.

**A refusal is not an incident.** The system declining to produce a fragile
number is it working correctly. Do not page on it, and do not tune the gates to
reduce it.

## Backup and recovery — planned

Evidence bundles are the irreplaceable artefact: they carry provenance that
cannot be reconstructed if the source data has since changed. Database backups
plus object-storage versioning.

Analyses themselves are reproducible from a stored spec, so compute loss is
recoverable. Provenance loss is not.
