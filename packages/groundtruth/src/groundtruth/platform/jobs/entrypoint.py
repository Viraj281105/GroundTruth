"""Start a worker process: check the environment, then run the loop until stopped.

**Owner: Bhumi.** ``apps/worker/main.py`` is a thin wrapper around :func:`main`.

Startup refuses to run rather than run wrongly:

* no ``DATABASE_URL`` -> exit 2. There is no default database; a local file would
  quietly hold results nobody else can see.
* a database behind the code's migrations -> exit 2, naming the command that fixes it.
  ``--migrate`` applies them first; it is opt-in because several workers starting at
  once must not all migrate.
* no ``GIT_SHA`` -> a warning, and results record the commit as null. Never a
  placeholder: an invented commit would be a fabricated provenance value (R6).

Shutdown is graceful on the first signal (finish the current job, claim no more) and
immediate on the second. Ctrl+C and Ctrl+Break work on Windows; SIGTERM on Linux and
in containers. A process killed outright runs no handler; it leaves no partial result,
and its job is retried when the lease expires.
"""

from __future__ import annotations

import argparse
import os
import signal
from collections.abc import Callable
from types import FrameType
from typing import Any

import sqlalchemy as sa

from groundtruth.contracts.errors import ConfigurationError
from groundtruth.engine import ENGINE_VERSION
from groundtruth.logging import configure_logging, get_logger
from groundtruth.platform.config import get_settings
from groundtruth.platform.jobs.queue import JobQueue
from groundtruth.platform.jobs.worker import (
    DEFAULT_POLL_SECONDS,
    DEFAULT_TRUE_EFFECT,
    Worker,
    default_resolve_access,
    engine_runner,
)
from groundtruth.platform.metrics import start_metrics_server
from groundtruth.platform.redaction import redact_secrets
from groundtruth.platform.store import migrate
from groundtruth.platform.store.database import (
    create_db_engine,
    create_session_factory,
    resolve_database_url,
)

logger = get_logger("worker")

EXIT_OK = 0
EXIT_STARTUP_REFUSED = 2
EXIT_INTERRUPTED = 130

_SHUTDOWN_SIGNALS = ("SIGINT", "SIGTERM", "SIGBREAK")  # SIGBREAK is Ctrl+Break on Windows


def safe_database_url(url: str) -> str:
    """The URL with any password masked, for logs."""
    return sa.engine.make_url(url).render_as_string(hide_password=True)


class ShutdownHandler:
    """First signal: finish the current job, then stop. Second: stop now."""

    def __init__(self, worker: Worker) -> None:
        self._worker = worker
        self.received = 0

    def __call__(self, signum: int, frame: FrameType | None) -> None:
        self.received += 1
        if self.received == 1:
            logger.warning(
                "shutdown requested (signal %s): finishing the current job, then stopping. "
                "Signal again to stop immediately.",
                signum,
            )
            self._worker.request_stop()
            return
        raise KeyboardInterrupt


def install_signal_handlers(handler: Callable[[int, FrameType | None], Any]) -> dict[int, Any]:
    """Route shutdown signals to ``handler``. Returns the previous handlers to restore."""
    previous: dict[int, Any] = {}
    for name in _SHUTDOWN_SIGNALS:
        number = getattr(signal, name, None)
        if number is not None:
            previous[number] = signal.signal(number, handler)
    return previous


def restore_signal_handlers(previous: dict[int, Any]) -> None:
    for number, handler in previous.items():
        signal.signal(number, handler)


def seed_demo(extra: dict[str, str]) -> None:
    """Import the Reference projects and the demo orgs/users (``SEED_DEMO=true``; dev only).

    Idempotent: existing users keep their passwords. Credentials, when created, go to
    ``SEED_DEMO_PASSWORDS_FILE`` (never the log). Opt-in: a real deployment must not ship
    well-known demo accounts.
    """
    from groundtruth.cli import main as cli_main

    argv = ["seed", "--demo"]
    passwords_file = os.environ.get("SEED_DEMO_PASSWORDS_FILE")
    if passwords_file:
        argv += ["--passwords-file", passwords_file]
    else:
        logger.warning(
            "SEED_DEMO=true without SEED_DEMO_PASSWORDS_FILE: credentials are printed once",
            extra=extra,
        )
    code = cli_main(argv)
    if code != 0:
        raise ConfigurationError(f"demo seed failed (exit {code})")
    logger.info("demo seed complete", extra=extra)


def _env_int(name: str) -> int | None:
    """An integer from the environment, or ``None`` when unset or blank."""
    value = os.environ.get(name, "").strip()
    return int(value) if value else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m apps.worker.main",
        description="Run the GroundTruth analysis worker: claim queued jobs and run them.",
    )
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Apply database migrations before starting (off by default).",
    )
    parser.add_argument(
        "--exit-when-idle",
        action="store_true",
        help="Stop once the queue is empty instead of waiting for more work.",
    )
    parser.add_argument("--max-jobs", type=int, default=None, help="Stop after this many jobs.")
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=DEFAULT_POLL_SECONDS,
        help=f"Wait this long when the queue is empty (default {DEFAULT_POLL_SECONDS}).",
    )
    parser.add_argument(
        "--true-effect",
        type=float,
        default=DEFAULT_TRUE_EFFECT,
        help="Effect injected into SIMULATED runs only (default %(default)s).",
    )
    parser.add_argument("--log-level", default=None, help="Override the configured log level.")
    parser.add_argument(
        "--batch-max-running",
        type=int,
        default=_env_int("WORKER_BATCH_MAX_RUNNING"),
        help="Run at most this many batch jobs at once across all workers, keeping the rest "
        "free for interactive work (env WORKER_BATCH_MAX_RUNNING; default: no limit). "
        "Interactive jobs are always taken first.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run a worker. Returns the process exit code."""
    args = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(args.log_level or settings.log_level, json_output=True, redact=redact_secrets)
    startup = {"stage": "startup"}

    try:
        url = resolve_database_url()
    except ConfigurationError as exc:
        logger.error("cannot start: %s", exc, extra=startup)
        return EXIT_STARTUP_REFUSED

    if args.migrate:
        migrate.upgrade(url)
        logger.info("database migrated to %s", migrate.head_revision(), extra=startup)
        if os.environ.get("SEED_DEMO", "").strip().lower() in ("1", "true", "yes"):
            seed_demo(startup)
    elif not migrate.is_at_head(url):
        logger.error(
            "cannot start: the database is at migration %s but this code needs %s. "
            "Run `python -m apps.worker.main --migrate`, or "
            "`alembic -c packages/groundtruth/alembic.ini upgrade head`.",
            migrate.current_revision(url) or "none",
            migrate.head_revision(),
            extra=startup,
        )
        return EXIT_STARTUP_REFUSED

    if settings.git_sha is None:
        logger.warning(
            "GIT_SHA is not set: results from this worker will record git_sha as null",
            extra=startup,
        )
    logger.warning(
        "SIMULATED DATA: only the simulated-data path is implemented. Simulated jobs run on "
        "the synthetic fixture and are labelled is_simulated=true; observed-data jobs fail "
        "because Earth Engine access is not implemented (#22).",
        extra=startup,
    )

    db = create_db_engine(url)
    queue = JobQueue(create_session_factory(db), batch_max_running=args.batch_max_running)
    worker = Worker(
        queue,
        resolve_access=default_resolve_access(args.true_effect),
        run=engine_runner(settings.git_sha),
        poll_interval=args.poll_seconds,
    )
    # Stage durations, outcomes and cache hits for Prometheus, on an internal port (#50).
    start_metrics_server(settings.worker_metrics_port, settings.metrics_bind_address)
    previous = install_signal_handlers(ShutdownHandler(worker))
    logger.info(
        "worker %s started on %s (engine %s, lease %ss)",
        worker.worker_id,
        safe_database_url(url),
        ENGINE_VERSION,
        int(queue.lease.total_seconds()),
        extra=startup,
    )
    try:
        processed = worker.run(exit_when_idle=args.exit_when_idle, max_jobs=args.max_jobs)
    except KeyboardInterrupt:
        logger.warning(
            "stopped immediately; a job in progress was not recorded and is retried after "
            "its lease expires",
            extra={"stage": "shutdown"},
        )
        return EXIT_INTERRUPTED
    finally:
        restore_signal_handlers(previous)
        db.dispose()
    logger.info("worker stopped after %d job(s)", processed, extra={"stage": "shutdown"})
    return EXIT_OK
