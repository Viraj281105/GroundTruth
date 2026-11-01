"""Background worker entrypoint.

**Owner: Bhumi.**

Deliberately thin, like ``apps/api/main.py``. All worker logic lives in
``groundtruth.platform.jobs`` (where it is linted, type-checked and tested); this file
gives the deployment a stable command that does not change when the package is
reorganised.

The worker is a separate process from the API because analyses are long-running: a
Kariba-scale placebo suite is seconds to minutes of CPU, and registry-scale batch
screening is hours. Blocking an HTTP worker on that would be a design error.

Run locally, from the repository root::

    python -m apps.worker.main --migrate      # first run: create the tables
    python -m apps.worker.main                # then: run until Ctrl+C

See ``apps/worker/README.md`` and ``docs/architecture/worker.md``.
"""

from __future__ import annotations

from groundtruth.platform.jobs.entrypoint import main

if __name__ == "__main__":
    raise SystemExit(main())
