"""ASGI entrypoint for the GroundTruth API.

**Owner: Bhumi.**

Deliberately thin. All application logic lives in
``groundtruth.platform.api``; this file exists so the deployment target has a
stable import path that does not change when the package is reorganised.

It also does what only a deployed API process should (#50), which is why it is here and
not in the app module that tests import:

* JSON logs with credentials redacted, uvicorn's own lines included;
* Prometheus metrics, with the queue depth read from the database, on an internal port
  (``API_METRICS_PORT``, default 9464), never on the public API port.

Run locally::

    uvicorn apps.api.main:app --reload --port 8000
"""

import logging

from groundtruth.logging import configure_logging
from groundtruth.platform.api.app import app
from groundtruth.platform.config import get_settings
from groundtruth.platform.metrics import register_queue_collector, start_metrics_server
from groundtruth.platform.redaction import redact_secrets


def _configure_process() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=True, redact=redact_secrets)
    # uvicorn has configured its own handlers by the time it imports this module; send its
    # lines through the root handler so they are JSON and redacted like the rest.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    if settings.database_url:
        from groundtruth.platform.store.database import (
            create_db_engine,
            create_session_factory,
        )

        register_queue_collector(create_session_factory(create_db_engine(settings.database_url)))
    start_metrics_server(settings.api_metrics_port, settings.metrics_bind_address)


_configure_process()

__all__ = ["app"]
