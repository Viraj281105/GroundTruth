"""Replay stored runs and check they reproduce (#42).

**Owner: Bhumi.** ADR-006 promises that the same ``spec_hash``, seed and ``ENGINE_VERSION``
give the same numbers. This module checks the promise against stored runs, not against a
fixture: each run is replayed **from its own stored request** (proven to hash to its
``spec_hash``; never rebuilt from the case YAML), **through the contract only**
(``run_analysis``), and compared item by item with #35's ``diff_bundles``.

Each run ends in exactly one outcome:

* ``reproduced``: the replay matches.
* ``mismatch``: same engine version, different result. **A bug**; the command exits 1.
* ``expected_change``: a different engine version produced it. Reported separately, never a
  failure: a methodology change is meant to change the answer.
* ``skipped``: it cannot be replayed honestly, with the reason. An observed-data run whose data
  is unavailable is skipped, **never replayed against simulated data**; a run with no stored
  result (failed, cancelled) or no stored request (saved before #24) is skipped too.

What "the same" means: numbers within a relative ``1e-9`` (last-digit floating-point noise
between machines; ADR-006 does not promise bit-exactness across platforms), and the verdict
label, the outcome status and a refusal's code and stage exactly.

Sources: a database (``DATABASE_URL``), or a folder of golden stored runs
(``tests/golden/stored_runs``) made by the real simulated path, which CI replays on every push
and daily. Run it as ``python -m groundtruth.platform.replay`` or ``groundtruth-replay``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from groundtruth.contracts.errors import ConfigurationError, DataUnavailableError
from groundtruth.contracts.ports import DataAccess
from groundtruth.contracts.request import AnalysisRequest
from groundtruth.contracts.result import AnalysisResult
from groundtruth.engine import ENGINE_VERSION, run_analysis
from groundtruth.platform.compare.diff import diff_bundles
from groundtruth.platform.datasets.access import earth_engine_access, synthetic_access
from groundtruth.platform.datasets.synthetic import pinned_true_effect

REL_TOL = 1e-9
"""Two numbers within this relative tolerance are the same number (#35's diff default)."""

LEGACY_TRUE_EFFECT = 0.06
"""The effect a worker injected into a simulated run whose request does not pin one (submitted
before #42, or by the CLI): the worker's default. A replay that has to assume it says so."""

Outcome = Literal["reproduced", "mismatch", "expected_change", "skipped"]
RunEngine = Callable[[AnalysisRequest, DataAccess], AnalysisResult]


@dataclass(frozen=True)
class StoredRun:
    """One stored run, as a replay needs it."""

    run_id: str
    case_id: str
    spec_hash: str
    status: str
    request: AnalysisRequest | None
    result: AnalysisResult | None
    source: str
    unreadable: str | None = None
    """Why the request or result could not be read, when it could not."""


@dataclass(frozen=True)
class ReplayOutcome:
    run_id: str
    case_id: str
    outcome: Outcome
    stored_engine_version: str | None
    replay_engine_version: str
    reason: str = ""
    differences: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "case_id": self.case_id,
            "outcome": self.outcome,
            "stored_engine_version": self.stored_engine_version,
            "replay_engine_version": self.replay_engine_version,
            "reason": self.reason,
            "differences": list(self.differences),
            "notes": list(self.notes),
        }


@dataclass
class ReplayReport:
    outcomes: list[ReplayOutcome] = field(default_factory=list)

    def of(self, outcome: Outcome) -> list[ReplayOutcome]:
        return [o for o in self.outcomes if o.outcome == outcome]

    @property
    def failed(self) -> bool:
        """True when any run failed to reproduce within its own engine version."""
        return bool(self.of("mismatch"))

    def as_dict(self) -> dict[str, Any]:
        return {
            "counts": {k: len(self.of(k)) for k in _OUTCOMES},
            "runs": [o.as_dict() for o in self.outcomes],
        }


_OUTCOMES: tuple[Outcome, ...] = ("reproduced", "mismatch", "expected_change", "skipped")


# --- one run -----------------------------------------------------------------------------------


def _data_access(request: AnalysisRequest) -> tuple[DataAccess, tuple[str, ...]]:
    """The data the run read. Raises ``DataUnavailableError`` for observed data not on hand."""
    if request.data_mode != "simulated":
        return earth_engine_access(request), ()  # raises when the data is unavailable
    if pinned_true_effect(request) is not None:
        return synthetic_access(request), ()
    note = (
        f"the request pins no simulation, so the worker's default true_effect "
        f"({LEGACY_TRUE_EFFECT}) was assumed"
    )
    return synthetic_access(request, true_effect=LEGACY_TRUE_EFFECT), (note,)


def _differences(stored: AnalysisResult, replayed: AnalysisResult, rel_tol: float) -> list[str]:
    found: list[str] = []
    if replayed.spec_hash != stored.spec_hash:
        found.append(f"spec_hash {stored.spec_hash} -> {replayed.spec_hash}")
    if replayed.status != stored.status:
        found.append(f"status {stored.status.value} -> {replayed.status.value}")
    if stored.error is not None or replayed.error is not None:
        before = (stored.error.code.value, stored.error.stage) if stored.error else None
        after = (replayed.error.code.value, replayed.error.stage) if replayed.error else None
        if before != after:
            found.append(f"error (code, stage) {before} -> {after}")
    if stored.bundle is not None and replayed.bundle is not None:
        diff = diff_bundles(stored.bundle, replayed.bundle, rel_tol=rel_tol)
        for item in diff.items:
            if item.status != "unchanged":
                fields = ", ".join(change.field for change in item.changes) or item.status
                found.append(f"{item.id}: {fields}")
        if diff.verdict.label_changed:
            found.append(f"verdict {diff.verdict.baseline_label} -> {diff.verdict.candidate_label}")
        if diff.verdict.divergence_ratio_changed:
            found.append("verdict divergence ratio")
        if diff.warnings.added or diff.warnings.removed:
            found.append("warnings")
    elif (stored.bundle is None) != (replayed.bundle is None):
        found.append("evidence bundle present in only one of the two")
    return found


def replay_one(
    run: StoredRun,
    *,
    engine: RunEngine = run_analysis,
    engine_version: str = ENGINE_VERSION,
    rel_tol: float = REL_TOL,
) -> ReplayOutcome:
    """Replay one stored run and classify the result. Never raises for a bad run."""
    stored_version = run.result.engine.engine_version if run.result is not None else None

    def outcome(kind: Outcome, reason: str = "", **extra: Any) -> ReplayOutcome:
        return ReplayOutcome(
            run_id=run.run_id,
            case_id=run.case_id,
            outcome=kind,
            stored_engine_version=stored_version,
            replay_engine_version=engine_version,
            reason=reason,
            **extra,
        )

    if run.unreadable is not None:
        return outcome("skipped", run.unreadable)
    if run.result is None:
        return outcome("skipped", f"no result stored (the job is {run.status})")
    if run.request is None:
        return outcome("skipped", "no stored request (saved before requests were stored, #24)")
    try:
        access, notes = _data_access(run.request)
    except (DataUnavailableError, ConfigurationError, NotImplementedError) as exc:
        return outcome(
            "skipped",
            f"{run.request.data_mode} data unavailable, so it is not replayed "
            f"(never against simulated data): {exc}",
        )
    try:
        replayed = engine(run.request, access)
    except Exception as exc:
        kind: Outcome = "mismatch" if stored_version == engine_version else "expected_change"
        return outcome(kind, f"the replay raised {type(exc).__name__}: {exc}", notes=notes)
    differences = _differences(run.result, replayed, rel_tol)
    if not differences:
        return outcome("reproduced", notes=notes)
    if stored_version == engine_version:
        return outcome(
            "mismatch",
            "same engine version, different result",
            differences=tuple(differences),
            notes=notes,
        )
    return outcome(
        "expected_change",
        f"engine {stored_version} -> {engine_version}",
        differences=tuple(differences),
        notes=notes,
    )


def replay(runs: Iterable[StoredRun], **options: Any) -> ReplayReport:
    """Replay every run. ``options`` go to :func:`replay_one`."""
    report = ReplayReport()
    for run in runs:
        report.outcomes.append(replay_one(run, **options))
    return report


# --- sources -------------------------------------------------------------------------------


def runs_from_database(url: str) -> Iterator[StoredRun]:
    """Every stored run in the database, oldest first. Reads only; writes nothing."""
    import sqlalchemy as sa

    from groundtruth.platform.jobs.queue import stored_request
    from groundtruth.platform.store.database import create_db_engine, create_session_factory
    from groundtruth.platform.store.interface import StoreError
    from groundtruth.platform.store.models import AnalysisRunRow
    from groundtruth.platform.store.sql import SqlEvidenceStore

    db = create_db_engine(url)
    try:
        sessions = create_session_factory(db)
        store = SqlEvidenceStore(sessions)
        with sessions() as session:
            rows = list(
                session.execute(
                    sa.select(AnalysisRunRow).order_by(
                        AnalysisRunRow.created_at, AnalysisRunRow.run_id
                    )
                ).scalars()
            )
            for row in rows:
                session.expunge(row)
        for row in rows:
            unreadable = None
            request: AnalysisRequest | None = None
            result: AnalysisResult | None = None
            try:
                if row.request is not None:
                    request = stored_request(row)
                result = store.by_run_id(row.run_id)
            except StoreError as exc:
                unreadable = f"cannot be read: {exc}"
            yield StoredRun(
                run_id=row.run_id,
                case_id=row.case_id,
                spec_hash=row.spec_hash,
                status=row.status,
                request=request,
                result=result,
                source="database",
                unreadable=unreadable,
            )
    finally:
        db.dispose()


def write_golden(run: StoredRun, path: Path) -> None:
    """Save a stored run as a golden file, exactly as a database replay would read it."""
    assert run.request is not None and run.result is not None
    document = {
        "run_id": run.run_id,
        "case_id": run.case_id,
        "spec_hash": run.spec_hash,
        "status": run.status,
        "request": run.request.model_dump(mode="json"),
        "result": run.result.model_dump(mode="json"),
    }
    path.write_text(json.dumps(document, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def runs_from_golden(folder: Path) -> Iterator[StoredRun]:
    """The golden stored runs in ``folder``, by file name."""
    for path in sorted(folder.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        request = AnalysisRequest.model_validate(document["request"])
        unreadable = None
        if request.spec_hash != document["spec_hash"]:
            unreadable = (
                f"the golden request hashes to {request.spec_hash}, not {document['spec_hash']}"
            )
        yield StoredRun(
            run_id=document["run_id"],
            case_id=document["case_id"],
            spec_hash=document["spec_hash"],
            status=document["status"],
            request=request,
            result=AnalysisResult.model_validate(document["result"]),
            source=str(path),
            unreadable=unreadable,
        )


# --- reporting -------------------------------------------------------------------------------


def markdown(report: ReplayReport, *, title: str) -> str:
    counts = report.as_dict()["counts"]
    lines = [
        f"### {title}",
        "",
        " · ".join(f"{k.replace('_', ' ')}: **{v}**" for k, v in counts.items()),
        "",
    ]
    sections: list[tuple[Outcome, str]] = [
        ("mismatch", "Mismatches within an engine version (bugs)"),
        ("expected_change", "Expected changes across engine versions (not failures)"),
        ("skipped", "Skipped"),
    ]
    for kind, heading in sections:
        rows = report.of(kind)
        if not rows:
            continue
        lines += [f"**{heading}**", "", "| Run | Case | Engine | Why |", "|---|---|---|---|"]
        for o in rows:
            why = o.reason + (f" ({'; '.join(o.differences[:5])})" if o.differences else "")
            lines.append(
                f"| `{o.run_id}` | {o.case_id} | {o.stored_engine_version} → "
                f"{o.replay_engine_version} | {why} |"
            )
        lines.append("")
    noted = [o for o in report.outcomes if o.notes]
    if noted:
        lines += ["**Notes**", ""] + [f"* `{o.run_id}`: {'; '.join(o.notes)}" for o in noted]
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="groundtruth-replay",
        description="Replay stored runs and check they reproduce (#42). Exits 1 only when a "
        "run differs from its replay under the same engine version.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--golden", type=Path, help="Replay the golden stored runs in this folder.")
    source.add_argument(
        "--database-url", help="Replay this database (default: the DATABASE_URL setting)."
    )
    parser.add_argument("--rel-tol", type=float, default=REL_TOL, help="Relative tolerance.")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.golden is not None:
        runs: Iterable[StoredRun] = runs_from_golden(args.golden)
        title = f"Replay of golden stored runs ({args.golden})"
    else:
        from groundtruth.platform.config import get_settings
        from groundtruth.platform.redaction import redact_secrets

        url = args.database_url or get_settings().database_url
        if not url:
            print("groundtruth-replay: set DATABASE_URL, or pass --golden FOLDER", file=sys.stderr)
            return 2
        runs = runs_from_database(str(url))
        title = f"Replay of stored runs ({redact_secrets(str(url))})"
    report = replay(runs, rel_tol=args.rel_tol)
    text = markdown(report, title=title)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(text + "\n")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "LEGACY_TRUE_EFFECT",
    "REL_TOL",
    "ReplayOutcome",
    "ReplayReport",
    "StoredRun",
    "main",
    "markdown",
    "replay",
    "replay_one",
    "runs_from_database",
    "runs_from_golden",
    "write_golden",
]
