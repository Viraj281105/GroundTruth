"""When two runs may be compared, and the comparison itself.

A bundle diff is only honest between analyses that measured the same thing the same way.
Across engine versions, or between a simulated and an observed run, a difference in a
number might be a change in the project or only a change in the instrument. Presenting
it as a change would put a measurement artefact in front of a due-diligence team, so
such a pair is reported as NOT COMPARABLE, with every reason, and **no diff is returned
at all**. There is no override.

A different ``spec_hash`` does *not* make runs incomparable: re-running the same method
on updated data is exactly the comparison monitoring wants. It is reported as
``same_specification: false`` so a reader knows the inputs differ.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from groundtruth.contracts.result import AnalysisResult
from groundtruth.contracts.version import parse_version
from groundtruth.platform.compare.diff import DEFAULT_REL_TOL, BundleDiff, diff_bundles
from groundtruth.platform.store.interface import RunSummary

Side = Literal["baseline", "candidate", "both"]
ReasonCode = Literal[
    "different_case",
    "different_data_mode",
    "different_engine_version",
    "different_contract_major",
    "contract_unreadable",
    "no_bundle",
]


class NotComparable(BaseModel):
    """One reason two runs cannot be compared."""

    model_config = ConfigDict(frozen=True)

    code: ReasonCode
    side: Side
    message: str


@dataclass(frozen=True)
class RunSide:
    """One run as the comparison sees it."""

    summary: RunSummary
    result: AnalysisResult | None = None
    """The stored result, when the run has one and it could be read."""
    unreadable: str | None = None
    """Why the stored result could not be read (an incompatible contract version)."""


class Comparison(BaseModel):
    """The outcome of comparing two runs."""

    model_config = ConfigDict(frozen=True)

    comparable: bool
    not_comparable: tuple[NotComparable, ...]
    same_specification: bool
    diff: BundleDiff | None
    """``None`` whenever ``comparable`` is false. Never a partial or advisory diff."""


def _major(version: str) -> int:
    return parse_version(version)[0]


def _no_bundle_message(side: str, run: RunSide) -> str:
    summary = run.summary
    state = summary.result_state
    if state in ("queued", "running"):
        return f"The {side} run is still {state}, so it has no evidence yet."
    if state == "cancelled":
        return f"The {side} run was cancelled before it produced evidence."
    if state == "refused":
        error = run.result.error if run.result else None
        detail = f" ({error.code.value}): {error.message}" if error else ""
        return (
            f"The {side} run was refused by the engine{detail}. A refusal is a legitimate "
            "outcome with no evidence to compare."
        )
    if run.result and run.result.error:
        return (
            f"The {side} run ended in an engine error ({run.result.error.code.value}) and "
            "produced no evidence."
        )
    reason = f": {summary.failure_reason}" if summary.failure_reason else ""
    return f"The {side} run failed before producing evidence{reason}."


def compare_runs(
    baseline: RunSide,
    candidate: RunSide,
    *,
    include_unchanged: bool = False,
    rel_tol: float = DEFAULT_REL_TOL,
) -> Comparison:
    """Compare two runs, or say precisely why they cannot be compared.

    Every reason that applies is reported, not just the first, so a reader fixes the
    whole problem in one go. When none applies, the bundles are diffed; with
    ``include_unchanged`` false the unchanged ids are counted in the summary but left
    out of ``items``.
    """
    a, b = baseline.summary, candidate.summary
    reasons: list[NotComparable] = []

    if a.case_id != b.case_id:
        reasons.append(
            NotComparable(
                code="different_case",
                side="both",
                message=f"The runs are for different cases ({a.case_id} and {b.case_id}).",
            )
        )
    if a.data_mode != b.data_mode:
        reasons.append(
            NotComparable(
                code="different_data_mode",
                side="both",
                message=(
                    f"One run used {a.data_mode} data and the other {b.data_mode} data. "
                    "Simulated numbers describe a test fixture and must never be set "
                    "against observations."
                ),
            )
        )
    if a.engine_version and b.engine_version and a.engine_version != b.engine_version:
        reasons.append(
            NotComparable(
                code="different_engine_version",
                side="both",
                message=(
                    f"The runs came from different engine versions ({a.engine_version} and "
                    f"{b.engine_version}). The same specification can produce different "
                    "numbers across versions by design, so a difference here may reflect "
                    "the method rather than the project."
                ),
            )
        )
    if _major(a.contract_version) != _major(b.contract_version):
        reasons.append(
            NotComparable(
                code="different_contract_major",
                side="both",
                message=(
                    f"The runs were written under incompatible contract versions "
                    f"({a.contract_version} and {b.contract_version})."
                ),
            )
        )
    for name, run in (("baseline", baseline), ("candidate", candidate)):
        if run.unreadable is not None:
            reasons.append(
                NotComparable(
                    code="contract_unreadable",
                    side=name,  # type: ignore[arg-type]
                    message=f"The {name} run cannot be read: {run.unreadable}",
                )
            )
        elif run.result is None or run.result.bundle is None:
            reasons.append(
                NotComparable(
                    code="no_bundle",
                    side=name,  # type: ignore[arg-type]
                    message=_no_bundle_message(name, run),
                )
            )

    diff: BundleDiff | None = None
    if not reasons:
        assert baseline.result is not None and candidate.result is not None
        assert baseline.result.bundle is not None and candidate.result.bundle is not None
        diff = diff_bundles(baseline.result.bundle, candidate.result.bundle, rel_tol=rel_tol)
        if not include_unchanged:
            diff = diff.model_copy(
                update={"items": tuple(i for i in diff.items if i.status != "unchanged")}
            )

    return Comparison(
        comparable=not reasons,
        not_comparable=tuple(reasons),
        same_specification=a.spec_hash == b.spec_hash,
        diff=diff,
    )
