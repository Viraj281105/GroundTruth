"""Background worker entrypoint. NOT IMPLEMENTED.

**Owner: Bhumi.**

The worker will consume analysis jobs from a queue, invoke the engine through
the contract, persist the resulting evidence bundle, and transition job status.

It is a separate process from the API because analyses are long-running: a
Kariba-scale placebo suite is tens of seconds of CPU, and registry-scale batch
screening is hours. Blocking an HTTP worker on that would be a design error.

Shape it will take::

    while True:
        job = queue.claim()                       # platform.jobs
        request = job.to_request()                # platform.cases
        data = resolve_access(request)            # platform.datasets
        result = run_analysis(request, data)      # groundtruth.engine
        store.persist(result)                     # platform.store
        job.complete(result)

Nothing here runs yet. See docs/architecture/worker.md and issue for the
analysis job lifecycle.
"""

from __future__ import annotations

import sys


def main() -> int:
    """Entry point. Not implemented."""
    print(
        "The GroundTruth worker is not implemented yet.\n"
        "Analyses currently run synchronously inside the API process.\n"
        "See docs/architecture/worker.md.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
