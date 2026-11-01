"""The evidence store's public interface: what callers may ask, and how it can fail.

**Owner: Bhumi.**

Callers (the job layer, the API, the report pipeline) depend on this module and
never on SQLAlchemy. That is the point of keeping it narrow: ``save_result`` plus
three retrievals. The database behind it can change to another backend without a
caller noticing.

Nothing here imports SQLAlchemy, so this module is usable without the ``db`` extra.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from groundtruth.contracts.errors import GroundTruthError
from groundtruth.contracts.result import AnalysisResult

DataMode = Literal["observed", "simulated"]
"""Whether a result came from real observations. Mirrors ``AnalysisResult.data_mode``."""


class StoreError(GroundTruthError):
    """Base class for evidence store failures.

    Defined here rather than in ``contracts/errors.py``: these describe how the
    platform's storage can fail, which is not part of the engine/platform contract.
    """


class DuplicateRunError(StoreError):
    """A result with this ``run_id`` is already stored.

    A run is written once. A re-run is a new ``run_id``; overwriting history would
    destroy exactly what the store exists to keep.
    """


class UnknownCaseError(StoreError):
    """The result's case has no row in the store. Call ``upsert_case`` first.

    The store never invents a case from a result alone, because a result does not
    carry the case's name or country and guessing them would fabricate data (R6).
    """


class IncompatibleBundleError(StoreError):
    """Raised when a stored run or bundle cannot be read under the running contract."""


class RunSummary(BaseModel):
    """One stored run, as a listing shows it.

    Built from indexed columns only, so listing never opens an evidence document.
    ``is_simulated`` is always present so a listing cannot present a simulated run
    as observed (R7).
    """

    model_config = ConfigDict(frozen=True)

    run_id: str
    case_id: str
    spec_hash: str
    status: str
    """Platform lifecycle (``AnalysisStatus``): a refused run is still ``succeeded``."""
    engine_status: str | None
    error_code: str | None
    verdict_label: str | None
    data_mode: str
    is_simulated: bool
    engine_version: str | None
    contract_version: str
    created_at: datetime
    """When the store wrote the run (UTC). The ordering key for "most recent"."""
    failure_reason: str | None = None
    """Why a failed run failed, when no engine error was stored for it.

    Taken from the job's last error and cut to ``MAX_FAILURE_REASON`` characters. Set
    only for a failed run without a stored ``error``; a run that failed *in* the engine
    is explained by that error instead.
    """

    @property
    def result_state(self) -> ResultState:
        """What happened to this run, in the vocabulary the UI already uses.

        Distinct from ``status`` (the job) and from the verdict (the science): a
        refused run is a *successful job* whose state is ``refused``. The UI's
        existing ``ResultState`` values are kept as they are; ``queued`` and
        ``cancelled`` are additions (``queued`` is a kind of "running" to a display).
        """
        if self.status == "queued":
            return "queued"
        if self.status == "running":
            return "running"
        if self.status == "cancelled":
            return "cancelled"
        if self.status == "succeeded" and self.engine_status == "completed":
            return "measured"
        if self.status == "succeeded" and self.engine_status == "refused":
            return "refused"
        return "failed"


ResultState = Literal["queued", "running", "measured", "refused", "failed", "cancelled"]
"""See :attr:`RunSummary.result_state`."""

MAX_FAILURE_REASON = 300
"""Longest ``failure_reason`` returned. Job errors can carry exception text."""


class RunFilter(BaseModel):
    """Which runs to list. Every field narrows the result; unset means no restriction."""

    model_config = ConfigDict(frozen=True)

    case_id: str | None = None
    statuses: tuple[str, ...] = ()
    """Job statuses to include (``AnalysisStatus`` values). Empty means any."""
    engine_version: str | None = None
    data_mode: DataMode | None = None
    created_after: datetime | None = None
    """Inclusive lower bound on ``created_at``. Must be timezone-aware."""
    created_before: datetime | None = None
    """Exclusive upper bound on ``created_at``. Must be timezone-aware."""


class RunCursor(BaseModel):
    """A position in the run listing: the last run a page ended on.

    The listing is ordered by ``(created_at, run_id)`` descending and both parts are
    fixed when a run is created, so a position stays valid however many runs are
    written, or change status, afterwards.
    """

    model_config = ConfigDict(frozen=True)

    created_at: datetime
    run_id: str


class RunPage(BaseModel):
    """One page of the run listing."""

    model_config = ConfigDict(frozen=True)

    items: tuple[RunSummary, ...]
    next_cursor: RunCursor | None
    """Where the next page starts, or ``None`` when this page is the last."""


class EvidenceStore(Protocol):
    """Persist and retrieve analysis results by run, by specification, and by case."""

    def save_result(self, result: AnalysisResult, *, requested_by: str | None = None) -> None:
        """Store a finished result, atomically, exactly once.

        Raises:
            DuplicateRunError: if ``result.run_id`` is already stored.
            UnknownCaseError: if the result's case has not been stored.
            StoreError: if the database refuses the result, for example a simulated
                run labelled as observed (R7).
        """
        ...

    def by_run_id(self, run_id: str) -> AnalysisResult | None:
        """The stored result for ``run_id``, or ``None``.

        Raises:
            IncompatibleBundleError: if it was written under a contract this code
                cannot read.
        """
        ...

    def by_spec_hash(
        self, spec_hash: str, *, data_mode: DataMode, engine_version: str
    ) -> AnalysisResult | None:
        """The most recent usable result for a specification, or ``None``.

        Both keywords are required and have no default. Without ``data_mode`` a
        simulated result could answer an observed-data request (R7); without
        ``engine_version`` a result from an older engine could be served as if the
        current one had produced it (R8: identical numbers need the same hash, seed
        *and* engine version).

        Only runs that finished (completed or refused) are candidates. A refusal is
        deterministic, so it is a valid answer; an engine error is not.
        """
        ...

    def summary_for(self, run_id: str) -> RunSummary | None:
        """The run's summary, or ``None`` if there is no such run.

        Unlike :meth:`by_run_id`, this distinguishes "unknown run" from "known run with
        no engine result yet" (queued, running, cancelled, or failed before the engine).
        """
        ...

    def list_runs(
        self, filters: RunFilter, *, limit: int = 25, after: RunCursor | None = None
    ) -> RunPage:
        """A page of runs matching ``filters``, newest first, after the cursor.

        Keyset pagination: ordered by ``(created_at, run_id)`` descending, each page
        starting strictly after ``after``. Runs written while a caller pages never move
        or repeat a run it has yet to read.

        Raises:
            ValueError: if ``limit`` is below 1.
        """
        ...

    def list_for_case(
        self,
        case_id: str,
        *,
        data_mode: DataMode | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RunSummary]:
        """Runs for a case, newest first. Empty for an unknown case."""
        ...
