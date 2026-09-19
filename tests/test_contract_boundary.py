"""Tests that make the ownership boundary architectural rather than a convention.

GroundTruth is built by two people with a 60/40 split of the work. That split
only means something if the code actually has a seam at the agreed place. These
tests are that seam.

If they fail, someone has reached across the boundary, and the two workstreams
can no longer move independently.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from groundtruth.contracts import CONTRACT_VERSION, AnalysisRequest, AnalysisResult
from groundtruth.contracts.identifiers import spec_hash
from groundtruth.contracts.request import AnalysisWindow, ClaimUnderTest, UnitRef
from groundtruth.contracts.result import EngineStatus, ErrorCode
from groundtruth.contracts.types import Indicator
from groundtruth.contracts.version import is_compatible, parse_version

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "groundtruth"

# The only engine names the platform is allowed to import.
ENGINE_PUBLIC_API = {"run_analysis", "describe_engine", "engine_ref", "ENGINE_VERSION"}


def imported_modules(path: pathlib.Path) -> list[tuple[str, list[str]]]:
    """Return (module, imported_names) for every import in a Python file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[str, list[str]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.module, [a.name for a in node.names]))
        elif isinstance(node, ast.Import):
            found.extend((a.name, []) for a in node.names)
    return found


def python_files(package: str) -> list[pathlib.Path]:
    """Every Python file in one top-level package."""
    return sorted((SRC / package).rglob("*.py"))


class TestPackageBoundaries:
    """The three packages may only depend inward, toward the contract."""

    def test_contracts_depend_on_neither_side(self):
        """The contract is shared, so it cannot know about either implementation."""
        offenders = []
        for path in python_files("contracts"):
            for module, _ in imported_modules(path):
                if module.startswith(("groundtruth.engine", "groundtruth.platform")):
                    offenders.append(f"{path.name} imports {module}")
        assert not offenders, (
            f"groundtruth.contracts must not depend on either side of the boundary: {offenders}"
        )

    def test_engine_never_imports_the_platform(self):
        """The engine is a pure computational module.

        If it needs data, it asks a port. An import of the platform here would
        mean the engine could not be run, tested or replayed independently.
        """
        offenders = []
        for path in python_files("engine"):
            for module, _ in imported_modules(path):
                if module.startswith("groundtruth.platform"):
                    offenders.append(f"{path.relative_to(SRC)} imports {module}")
        assert not offenders, f"groundtruth.engine must not import the platform: {offenders}"

    def test_platform_uses_only_the_engine_public_api(self):
        """The platform may call the engine, but not reach into it.

        Importing ``groundtruth.engine.causal.synthetic_control`` from the
        platform would couple deployment code to an estimator's internals, and
        the engine could no longer be refactored without breaking the app.
        """
        offenders = []
        for path in python_files("platform"):
            for module, names in imported_modules(path):
                if not module.startswith("groundtruth.engine"):
                    continue
                if module != "groundtruth.engine":
                    offenders.append(f"{path.relative_to(SRC)} imports submodule {module}")
                    continue
                for name in names:
                    if name not in ENGINE_PUBLIC_API:
                        offenders.append(f"{path.relative_to(SRC)} imports engine.{name}")
        assert not offenders, (
            f"the platform may only import {sorted(ENGINE_PUBLIC_API)} from groundtruth.engine: "
            f"{offenders}"
        )

    def test_engine_performs_no_io(self):
        """The engine opens no sockets, reads no credentials, touches no files."""
        forbidden = {"requests", "httpx", "urllib", "socket", "sqlite3", "psycopg", "boto3", "ee"}
        offenders = []
        for path in python_files("engine"):
            for module, _ in imported_modules(path):
                root = module.split(".")[0]
                if root in forbidden:
                    offenders.append(f"{path.relative_to(SRC)} imports {module}")
                if root == "os" or module == "pathlib":
                    offenders.append(f"{path.relative_to(SRC)} imports {module}")
        assert not offenders, f"the engine must not perform I/O: {offenders}"


class TestContractVersioning:
    def test_version_is_semver(self):
        assert parse_version(CONTRACT_VERSION)

    def test_same_version_is_compatible(self):
        assert is_compatible(CONTRACT_VERSION)

    def test_a_major_bump_breaks_compatibility(self):
        assert not is_compatible("2.0.0", "1.4.0")
        assert not is_compatible("1.0.0", "2.0.0")

    def test_a_consumer_can_read_an_older_minor(self):
        """Minor changes are additive, so newer consumers read older bundles."""
        assert is_compatible("1.0.0", "1.3.0")

    def test_a_consumer_cannot_read_a_newer_minor(self):
        assert not is_compatible("1.3.0", "1.0.0")

    def test_malformed_versions_are_rejected(self):
        with pytest.raises(ValueError):
            parse_version("1.0")


def _request(**overrides) -> AnalysisRequest:
    payload = {
        "case_id": "test-case",
        "project": UnitRef(unit_id="test-case"),
        "claim": ClaimUnderTest(name="Test Project"),
        "indicator": Indicator.NDVI,
        "window": AnalysisWindow(pre_start=2001, pre_end=2010, post_start=2011, post_end=2020),
    }
    payload.update(overrides)
    return AnalysisRequest(**payload)


class TestAnalysisRequest:
    def test_spec_hash_is_deterministic_across_processes(self):
        """Reproducibility requires a stable hash, not Python's salted hash()."""
        assert _request().spec_hash == _request().spec_hash

    def test_spec_hash_changes_with_the_specification(self):
        assert _request().spec_hash != _request(seed=99).spec_hash

    def test_spec_hash_ignores_non_analytical_fields(self):
        """Who asked for a run does not change what the run computes."""
        assert _request().spec_hash == _request(requested_by="bhumi", notes="rerun").spec_hash

    def test_window_must_be_ordered(self):
        with pytest.raises(ValueError):
            AnalysisWindow(pre_start=2010, pre_end=2005, post_start=2011, post_end=2020)

    def test_a_short_window_is_rejected_against_the_estimation_spec(self):
        with pytest.raises(ValueError, match="pre-treatment periods"):
            _request(
                window=AnalysisWindow(pre_start=2008, pre_end=2010, post_start=2011, post_end=2020)
            )

    def test_simulated_datasets_cannot_be_labelled_observed(self):
        """The one failure mode this system must not have."""
        from groundtruth.contracts.identifiers import DatasetRef

        with pytest.raises(ValueError, match="never be labelled as observed"):
            _request(
                data_mode="observed",
                datasets=(DatasetRef(dataset_id="synthetic-x", version="1", provider="synthetic"),),
            )

    def test_min_donors_cannot_exceed_max_donors(self):
        from groundtruth.contracts.request import DonorSpec

        with pytest.raises(ValueError, match="min_donors cannot exceed"):
            DonorSpec(min_donors=60, max_donors=50)

    def test_request_round_trips_through_json(self):
        request = _request()
        restored = AnalysisRequest.model_validate_json(request.model_dump_json())
        assert restored.spec_hash == request.spec_hash


class TestAnalysisResult:
    def test_a_completed_result_must_carry_a_bundle(self):
        from groundtruth.contracts.identifiers import EngineRef

        with pytest.raises(ValueError, match="must carry an evidence bundle"):
            AnalysisResult(
                run_id="run_0000000000000000",
                case_id="c",
                spec_hash=spec_hash({}),
                status=EngineStatus.COMPLETED,
                engine=EngineRef(engine_version="0", contract_version=CONTRACT_VERSION),
            )

    def test_a_failed_result_must_carry_an_error(self):
        from groundtruth.contracts.identifiers import EngineRef

        with pytest.raises(ValueError, match="must carry an error"):
            AnalysisResult(
                run_id="run_0000000000000000",
                case_id="c",
                spec_hash=spec_hash({}),
                status=EngineStatus.REFUSED,
                engine=EngineRef(engine_version="0", contract_version=CONTRACT_VERSION),
            )


class TestErrorSemantics:
    def test_scientific_refusals_are_distinguished_from_malfunctions(self):
        """A refusal is a legitimate outcome; the UI must not style it as an error."""
        assert ErrorCode.INSUFFICIENT_DATA.is_refusal
        assert ErrorCode.DONOR_POOL_INADEQUATE.is_refusal
        assert not ErrorCode.ESTIMATION_FAILED.is_refusal
        assert not ErrorCode.INTERNAL_ERROR.is_refusal

    def test_every_error_code_is_mapped_to_an_http_status(self):
        """A code with no mapping would silently become a 500 in the API."""
        from groundtruth.platform.api.app import ERROR_STATUS

        unmapped = [c for c in ErrorCode if c not in ERROR_STATUS]
        assert not unmapped, f"unmapped error codes: {unmapped}"

    def test_terminal_statuses_are_identified(self):
        from groundtruth.contracts.result import AnalysisStatus

        assert AnalysisStatus.SUCCEEDED.is_terminal
        assert AnalysisStatus.FAILED.is_terminal
        assert not AnalysisStatus.RUNNING.is_terminal
