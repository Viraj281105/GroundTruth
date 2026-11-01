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
