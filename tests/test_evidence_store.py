"""The evidence and provenance store (issue #15).

Runs on SQLite through the real migrations. The results are real engine output on
the synthetic fixture (so everything here is SIMULATED DATA), not hand-built objects,
because the point is that what the engine produces reloads exactly.
"""

from __future__ import annotations

import ast
import pathlib
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from groundtruth.contracts.identifiers import DatasetRef, EngineRef, new_run_id
from groundtruth.contracts.result import (
    AnalysisError,
    AnalysisResult,
    EngineStatus,
    ErrorCode,
)
from groundtruth.contracts.version import CONTRACT_VERSION
from groundtruth.engine import ENGINE_VERSION, run_analysis
from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.datasets.access import synthetic_access
from groundtruth.platform.store import migrate, sql
from groundtruth.platform.store.database import create_db_engine, create_session_factory
from groundtruth.platform.store.interface import (
    DuplicateRunError,
    IncompatibleBundleError,
    StoreError,
    UnknownCaseError,
)
from groundtruth.platform.store.models import AnalysisRunRow, CaseRow, EvidenceBundleRow
from groundtruth.platform.store.sql import SqlEvidenceStore

T0 = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)
STORE_DIR = (
    pathlib.Path(__file__).resolve().parents[1]
    / "packages"
    / "groundtruth"
    / "src"
    / "groundtruth"
    / "platform"
    / "store"
)


class FakeClock:
    """A settable clock, so tests control write order and force ties."""

    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def tick(self, seconds: float = 1.0) -> datetime:
        self.now += timedelta(seconds=seconds)
        return self.now


def _engine_run(*, min_donors: int = 10) -> AnalysisResult:
    case = get_case("kariba-redd")
    request = case.to_request(seed=20260101, min_donors=min_donors)
    return run_analysis(request, synthetic_access(request, true_effect=0.06))


@pytest.fixture(scope="module")
def completed() -> AnalysisResult:
    """A real completed run on SIMULATED DATA."""
    result = _engine_run()
    assert result.status is EngineStatus.COMPLETED and result.is_simulated
    return result


@pytest.fixture(scope="module")
def refused() -> AnalysisResult:
    """A real refusal: no donor pool of 500 exists, and the engine says so."""
    result = _engine_run(min_donors=500)
    assert result.status is EngineStatus.REFUSED and result.bundle is None
    return result


def _variant(result: AnalysisResult, run_id: str | None = None, **changes) -> AnalysisResult:
    """The same specification as ``result`` under a new run id (a re-run)."""
    return result.model_copy(update={"run_id": run_id or new_run_id(), **changes})


@pytest.fixture
def url(tmp_path: pathlib.Path) -> str:
    return f"sqlite:///{tmp_path / 'groundtruth.db'}"


@pytest.fixture
def sessions(url: str) -> sessionmaker[Session]:
    migrate.upgrade(url)
    return create_session_factory(create_db_engine(url))


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def store(sessions: sessionmaker[Session], clock: FakeClock) -> SqlEvidenceStore:
    store = SqlEvidenceStore(sessions, clock=clock)
    store.upsert_case(get_case("kariba-redd"))
    return store


def _find(store: SqlEvidenceStore, result: AnalysisResult) -> AnalysisResult | None:
    return store.by_spec_hash(
        result.spec_hash, data_mode=result.data_mode, engine_version=result.engine.engine_version
    )


# --- a stored result reloads identically ----------------------------------------


class TestRoundTrip:
    def test_a_completed_run_reloads_identically(
        self, store: SqlEvidenceStore, completed: AnalysisResult
    ):
        store.save_result(completed)
        loaded = store.by_run_id(completed.run_id)

        assert loaded == completed
        assert loaded.bundle.to_json() == completed.bundle.to_json()

    def test_provenance_fingerprints_survive(
        self, store: SqlEvidenceStore, completed: AnalysisResult
    ):
        store.save_result(completed)
        loaded = store.by_run_id(completed.run_id)

        before = {i.id: i.provenance.fingerprint() for i in completed.bundle}
        after = {i.id: i.provenance.fingerprint() for i in loaded.bundle}
        assert before == after
        assert len(before) > 10  # a real bundle, not a trivially empty comparison
        # The fingerprint ignores retrieved_at, so check the full records as well.
        assert [i.provenance for i in loaded.bundle] == [i.provenance for i in completed.bundle]

    def test_the_engine_timestamps_come_back_as_the_same_strings(
        self, store: SqlEvidenceStore, completed: AnalysisResult
    ):
        store.save_result(completed)
        loaded = store.by_run_id(completed.run_id)
        assert (loaded.started_at, loaded.finished_at) == (
            completed.started_at,
            completed.finished_at,
        )

    def test_a_refusal_reloads_as_a_full_result_without_a_bundle(
        self, store: SqlEvidenceStore, refused: AnalysisResult
    ):
        store.save_result(refused)
        loaded = store.by_run_id(refused.run_id)

        assert loaded == refused
        assert loaded.bundle is None
        assert loaded.error.is_refusal
        assert loaded.error.detail == refused.error.detail

    def test_a_refusal_is_a_succeeded_job_and_has_no_bundle_row(
        self, store: SqlEvidenceStore, sessions: sessionmaker[Session], refused: AnalysisResult
    ):
        """ADR-008: the job ran fine; the data could not support an estimate."""
        store.save_result(refused)
        with sessions() as session:
            assert session.get(AnalysisRunRow, refused.run_id).status == "succeeded"
            assert session.get(EvidenceBundleRow, refused.run_id) is None

    def test_an_unknown_run_is_none(self, store: SqlEvidenceStore):
        assert store.by_run_id("run_doesnotexist000") is None

    def test_requested_by_is_recorded(
        self, store: SqlEvidenceStore, sessions: sessionmaker[Session], completed: AnalysisResult
    ):
        store.save_result(completed, requested_by="bhumi")
        with sessions() as session:
            assert session.get(AnalysisRunRow, completed.run_id).requested_by == "bhumi"


# --- a run is written once, completely ------------------------------------------


class TestWriteOnce:
    def test_storing_the_same_run_twice_is_rejected(
        self, store: SqlEvidenceStore, completed: AnalysisResult
    ):
        store.save_result(completed)
        with pytest.raises(DuplicateRunError, match=completed.run_id):
            store.save_result(completed)

    def test_a_different_result_under_the_same_run_id_does_not_overwrite(
        self, store: SqlEvidenceStore, completed: AnalysisResult, refused: AnalysisResult
    ):
        store.save_result(completed)
        impostor = refused.model_copy(update={"run_id": completed.run_id})
        with pytest.raises(DuplicateRunError):
            store.save_result(impostor)
        assert store.by_run_id(completed.run_id) == completed

    def test_two_writers_racing_still_get_a_duplicate_error(
        self, store: SqlEvidenceStore, completed: AnalysisResult, monkeypatch
    ):
        """The up-front check can be beaten; the primary key must still stop it."""
        store.save_result(completed)
        real_get = Session.get
        blinded: list[bool] = []

        def get_once_blind(self, entity, ident, *args, **kwargs):
            if entity is AnalysisRunRow and not blinded:
                blinded.append(True)
                return None  # the writer "did not see" the other run
            return real_get(self, entity, ident, *args, **kwargs)

        monkeypatch.setattr(Session, "get", get_once_blind)
        with pytest.raises(DuplicateRunError):
            store.save_result(completed)
        assert blinded  # the race path really ran

    def test_a_failed_bundle_write_leaves_no_run_behind(
        self,
        store: SqlEvidenceStore,
        sessions: sessionmaker[Session],
        completed: AnalysisResult,
        monkeypatch,
    ):
        """Run and bundle share one transaction: no completed run without its bundle."""

        def broken_bundle(result, created_at):
            return EvidenceBundleRow(
                run_id=result.run_id, case_id=result.case_id, contract_version=CONTRACT_VERSION,
                bundle={}, verdict_label=None, item_count=0,
            )  # fmt: skip

        monkeypatch.setattr(sql, "_bundle_row", broken_bundle)
        with pytest.raises(StoreError):
            store.save_result(completed)

        assert store.by_run_id(completed.run_id) is None
        with sessions() as session:
            assert session.scalar(sa.select(sa.func.count()).select_from(AnalysisRunRow)) == 0

    def test_a_result_for_an_unstored_case_is_refused(
        self, sessions: sessionmaker[Session], completed: AnalysisResult
    ):
        bare = SqlEvidenceStore(sessions)  # no upsert_case
        with pytest.raises(UnknownCaseError, match="upsert_case"):
            bare.save_result(completed)
        assert bare.by_run_id(completed.run_id) is None

    @pytest.mark.parametrize("field", ["started_at", "finished_at"])
    @pytest.mark.parametrize("value", ["yesterday", "2026-11-01T12:00:00"])
    def test_a_timestamp_that_names_no_instant_is_refused(
        self, store: SqlEvidenceStore, completed: AnalysisResult, field: str, value: str
    ):
        """Unparseable, or naive (no timezone): guessing would invent a time."""
        with pytest.raises(StoreError, match=field):
            store.save_result(_variant(completed, **{field: value}))


# --- the most recent run for a specification ------------------------------------


class TestBySpecHash:
    def test_returns_the_most_recently_stored_run(
        self, store: SqlEvidenceStore, clock: FakeClock, completed: AnalysisResult
    ):
        first, second, third = (_variant(completed) for _ in range(3))
        # Stored out of id order and out of time order on purpose.
        clock.now = T0 + timedelta(seconds=20)
        store.save_result(second)
        clock.now = T0 + timedelta(seconds=30)
        store.save_result(third)
        clock.now = T0 + timedelta(seconds=10)
        store.save_result(first)

        assert _find(store, completed).run_id == third.run_id

    def test_a_tie_is_broken_by_run_id_and_is_stable(
        self, store: SqlEvidenceStore, clock: FakeClock, completed: AnalysisResult
    ):
        ids = ["run_00000000000000aa", "run_00000000000000cc", "run_00000000000000bb"]
        for run_id in ids:  # the same clock instant for every write
            store.save_result(_variant(completed, run_id))

        answers = {_find(store, completed).run_id for _ in range(5)}
        assert answers == {"run_00000000000000cc"}

    def test_no_match_is_none(self, store: SqlEvidenceStore, completed: AnalysisResult):
        store.save_result(completed)
        assert (
            store.by_spec_hash("0" * 32, data_mode="simulated", engine_version=ENGINE_VERSION)
            is None
        )

    def test_a_refusal_is_a_valid_cached_answer(
        self, store: SqlEvidenceStore, refused: AnalysisResult
    ):
        """Refusals are deterministic, so recomputing one is wasted work."""
        store.save_result(refused)
        assert _find(store, refused) == refused

    def test_an_engine_error_is_stored_but_never_returned(
        self, store: SqlEvidenceStore, clock: FakeClock, completed: AnalysisResult
    ):
        store.save_result(completed)
        clock.tick()
        failed = _variant(
            completed,
            status=EngineStatus.ERROR,
            bundle=None,
            error=AnalysisError(code=ErrorCode.ESTIMATION_FAILED, message="did not converge"),
        )
        store.save_result(failed)

        assert store.by_run_id(failed.run_id).error.code is ErrorCode.ESTIMATION_FAILED
        assert _find(store, completed).run_id == completed.run_id  # not the newer error

    def test_an_engine_error_is_a_failed_job(
        self, store: SqlEvidenceStore, completed: AnalysisResult
    ):
        failed = _variant(
            completed,
            status=EngineStatus.ERROR,
            bundle=None,
            error=AnalysisError(code=ErrorCode.INTERNAL_ERROR, message="boom"),
        )
        store.save_result(failed)
        (summary,) = store.list_for_case(failed.case_id)
        assert (summary.status, summary.engine_status) == ("failed", "error")

    def test_a_result_from_another_engine_version_is_not_returned(
        self, store: SqlEvidenceStore, completed: AnalysisResult
    ):
        """R8: the same hash and seed only mean the same numbers on the same engine."""
        older = _variant(
            completed, engine=EngineRef(engine_version="0.9.0", contract_version=CONTRACT_VERSION)
        )
        store.save_result(older)

        assert _find(store, completed) is None
        assert (
            store.by_spec_hash(
                completed.spec_hash, data_mode="simulated", engine_version="0.9.0"
            ).run_id
            == older.run_id
        )

    def test_the_selectors_are_required(self, store: SqlEvidenceStore, completed: AnalysisResult):
        """No default means a caller cannot forget to say which results it will accept."""
        with pytest.raises(TypeError):
            store.by_spec_hash(completed.spec_hash)  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            store.by_spec_hash(completed.spec_hash, data_mode="simulated")  # type: ignore[call-arg]


# --- simulated data cannot answer an observed lookup ----------------------------


class TestSimulatedAndObserved:
    def _observed(self, completed: AnalysisResult) -> AnalysisResult:
        """A result *labelled* observed, for exercising the store's filtering only."""
        return _variant(completed, data_mode="observed", datasets=())

    def test_a_simulated_run_never_answers_an_observed_lookup(
        self, store: SqlEvidenceStore, completed: AnalysisResult
    ):
        store.save_result(completed)
        assert (
            store.by_spec_hash(
                completed.spec_hash, data_mode="observed", engine_version=ENGINE_VERSION
            )
            is None
        )

    def test_each_mode_finds_only_its_own_run(
        self, store: SqlEvidenceStore, clock: FakeClock, completed: AnalysisResult
    ):
        store.save_result(completed)
        clock.tick()
        observed = self._observed(completed)  # newer, same spec_hash
        store.save_result(observed)

        assert _find(store, completed).run_id == completed.run_id
        assert _find(store, observed).run_id == observed.run_id

    def test_a_simulated_run_cannot_be_filed_as_observed(
        self, store: SqlEvidenceStore, completed: AnalysisResult
    ):
        """R7: synthetic datasets under an 'observed' label are refused at the door."""
        synthetic = DatasetRef(dataset_id="synthetic-ndvi", version="1", provider="synthetic")
        mislabelled = _variant(completed, data_mode="observed", datasets=(synthetic,))
        assert mislabelled.is_simulated
        with pytest.raises(StoreError):
            store.save_result(mislabelled)
        assert store.by_run_id(mislabelled.run_id) is None

    def test_an_unknown_data_mode_is_refused(
        self, store: SqlEvidenceStore, completed: AnalysisResult
    ):
        with pytest.raises(StoreError):
            store.save_result(_variant(completed, data_mode="real"))

    def test_listings_carry_the_simulated_flag(
        self, store: SqlEvidenceStore, clock: FakeClock, completed: AnalysisResult
    ):
        store.save_result(completed)
        clock.tick()
        store.save_result(self._observed(completed))

        by_mode = {s.data_mode: s.is_simulated for s in store.list_for_case(completed.case_id)}
        assert by_mode == {"simulated": True, "observed": False}
        only_observed = store.list_for_case(completed.case_id, data_mode="observed")
        assert [s.data_mode for s in only_observed] == ["observed"]


# --- contract version is recorded and checked on read ---------------------------


class TestContractVersion:
    def test_the_version_is_recorded_on_the_run_and_the_bundle(
        self, store: SqlEvidenceStore, sessions: sessionmaker[Session], completed: AnalysisResult
    ):
        store.save_result(completed)
        with sessions() as session:
            run = session.get(AnalysisRunRow, completed.run_id)
            bundle = session.get(EvidenceBundleRow, completed.run_id)
        assert run.contract_version == bundle.contract_version == completed.contract_version
        assert run.engine_contract_version == completed.engine.contract_version

    def test_a_result_stored_under_1_0_0_loads_after_a_minor_bump(
        self, sessions: sessionmaker[Session], store: SqlEvidenceStore, completed: AnalysisResult
    ):
        store.save_result(completed)
        after_bump = SqlEvidenceStore(sessions, consumer_version="1.1.0")

        loaded = after_bump.by_run_id(completed.run_id)
        assert loaded == completed
        assert loaded.contract_version == "1.0.0"  # still says what it was written under
        assert _find(after_bump, completed) == completed

    @pytest.mark.parametrize("version", ["1.3.0", "2.0.0", "0.9.0"])
    def test_a_completed_run_from_an_unreadable_contract_is_refused(
        self, store: SqlEvidenceStore, completed: AnalysisResult, version: str
    ):
        stored = _variant(completed, contract_version=version)
        store.save_result(stored)
        with pytest.raises(IncompatibleBundleError, match=version.replace(".", r"\.")):
            store.by_run_id(stored.run_id)

    def test_a_refusal_is_checked_too_though_it_has_no_bundle(
        self, store: SqlEvidenceStore, refused: AnalysisResult
    ):
        stored = _variant(refused, contract_version="1.3.0")
        store.save_result(stored)
        with pytest.raises(IncompatibleBundleError):
            store.by_run_id(stored.run_id)

    def test_a_lookup_raises_rather_than_falling_back_to_an_older_run(
        self, store: SqlEvidenceStore, clock: FakeClock, completed: AnalysisResult
    ):
        """A cache that quietly serves a staler result is serving the wrong number."""
        store.save_result(completed)
        clock.tick()
        store.save_result(_variant(completed, contract_version="1.3.0"))
        with pytest.raises(IncompatibleBundleError):
            _find(store, completed)

    def test_a_run_with_no_recorded_engine_contract_is_refused(
        self, store: SqlEvidenceStore, sessions: sessionmaker[Session], completed: AnalysisResult
    ):
        store.save_result(completed)
        with sessions.begin() as session:
            session.get(AnalysisRunRow, completed.run_id).engine_contract_version = None
        with pytest.raises(StoreError, match="no finished engine result"):
            store.by_run_id(completed.run_id)


# --- cases ----------------------------------------------------------------------


class TestCases:
    def test_upsert_creates_then_updates(self, sessions: sessionmaker[Session]):
        from dataclasses import replace

        store = SqlEvidenceStore(sessions)
        case = get_case("kariba-redd")
        store.upsert_case(case)
        store.upsert_case(replace(case, notes="revised"))

        with sessions() as session:
            assert session.scalar(sa.select(sa.func.count()).select_from(CaseRow)) == 1
            row = session.get(CaseRow, "kariba-redd")
        assert row.definition["notes"] == "revised"
        assert (row.name, row.country) == (case.claim.name, case.claim.country)

    def test_the_stored_case_leaves_out_known_reference(self, sessions: sessionmaker[Session]):
        """A third-party figure has no place in the run archive."""
        case = get_case("kariba-redd")
        assert case.known_reference  # so the assertions below mean something
        SqlEvidenceStore(sessions).upsert_case(case)

        with sessions() as session:
            definition = session.get(CaseRow, case.case_id).definition
        stored = str(definition)
        assert "known_reference" not in definition
        # The finding's own content. (Its source_uri is skipped: the claim carries the
        # same registry URL as its own source, so that string is legitimately present.)
        for key in ("description", "source", "caveat"):
            assert " ".join(case.known_reference[key].split()) not in stored
        for key in ("reported_excess_share", "reported_credits_issued_approx"):
            assert key not in stored

    def test_upsert_mirrors_the_status_and_never_promotes_it(self, sessions: sessionmaker[Session]):
        case = get_case("kariba-redd")
        SqlEvidenceStore(sessions).upsert_case(case)
        with sessions() as session:
            assert session.get(CaseRow, case.case_id).status == case.status
        assert case.status != "analysed"  # nothing in the store changes that


# --- listing --------------------------------------------------------------------


class TestListForCase:
    def _fill(self, store: SqlEvidenceStore, clock: FakeClock, completed, n: int) -> list[str]:
        ids = []
        for _ in range(n):
            clock.tick()
            run = _variant(completed)
            store.save_result(run)
            ids.append(run.run_id)
        return ids

    def test_newest_first(self, store: SqlEvidenceStore, clock: FakeClock, completed):
        ids = self._fill(store, clock, completed, 4)
        assert [s.run_id for s in store.list_for_case(completed.case_id)] == ids[::-1]

    def test_pagination_walks_the_whole_list_without_repeats(
        self, store: SqlEvidenceStore, clock: FakeClock, completed
    ):
        ids = self._fill(store, clock, completed, 5)
        pages = [
            [s.run_id for s in store.list_for_case(completed.case_id, limit=2, offset=o)]
            for o in (0, 2, 4)
        ]
        assert [len(p) for p in pages] == [2, 2, 1]
        assert [run_id for page in pages for run_id in page] == ids[::-1]

    def test_an_unknown_case_is_an_empty_list(self, store: SqlEvidenceStore):
        assert store.list_for_case("no-such-case") == []

    def test_only_that_cases_runs_are_listed(
        self, store: SqlEvidenceStore, sessions: sessionmaker[Session], completed
    ):
        store.upsert_case(get_case("southern-cardamom-redd"))
        store.save_result(completed)
        store.save_result(_variant(completed, case_id="southern-cardamom-redd"))
        assert {s.case_id for s in store.list_for_case("kariba-redd")} == {"kariba-redd"}

    def test_a_summary_describes_the_run(self, store: SqlEvidenceStore, completed):
        store.save_result(completed)
        (summary,) = store.list_for_case(completed.case_id)
        assert summary.run_id == completed.run_id
        assert summary.verdict_label == completed.verdict_label
        assert summary.engine_version == ENGINE_VERSION
        assert summary.created_at == T0
        assert summary.status == "succeeded"

    def test_listing_never_reads_an_evidence_document(
        self, store: SqlEvidenceStore, sessions: sessionmaker[Session], clock, completed
    ):
        self._fill(store, clock, completed, 3)
        statements: list[str] = []
        engine = sessions.kw["bind"]
        sa.event.listen(
            engine, "before_cursor_execute", lambda c, cur, stmt, *a: statements.append(stmt)
        )

        store.list_for_case(completed.case_id)

        assert statements
        assert not [s for s in statements if "evidence_bundles" in s]

    @pytest.mark.parametrize(("limit", "offset"), [(0, 0), (-1, 0), (10, -1)])
    def test_nonsense_paging_is_rejected(self, store: SqlEvidenceStore, limit: int, offset: int):
        with pytest.raises(ValueError):
            store.list_for_case("kariba-redd", limit=limit, offset=offset)


# --- schema and boundary --------------------------------------------------------


class TestMigration0002:
    def test_it_adds_and_removes_only_its_column(self, url: str):
        def columns() -> set[str]:
            return {
                c["name"] for c in sa.inspect(create_db_engine(url)).get_columns("analysis_runs")
            }

        migrate.upgrade(url)
        assert "engine_contract_version" in columns()
        migrate.downgrade(url, "0001")
        assert "engine_contract_version" not in columns()
        assert {"run_id", "contract_version", "engine_version"} <= columns()
        migrate.upgrade(url)
        assert "engine_contract_version" in columns()


class TestBoundary:
    def test_the_interface_needs_no_database_library(self):
        """Callers type against ``interface``; they must not need the ``db`` extra."""
        tree = ast.parse((STORE_DIR / "interface.py").read_text(encoding="utf-8"))
        imported = {
            (n.module or "").split(".")[0]
            if isinstance(n, ast.ImportFrom)
            else a.name.split(".")[0]
            for n in ast.walk(tree)
            if isinstance(n, ast.Import | ast.ImportFrom)
            for a in (n.names if isinstance(n, ast.Import) else [n])
        }
        assert imported
        assert not imported & {"sqlalchemy", "alembic"}

    def test_the_store_still_never_imports_the_engine(self):
        offenders = []
        for path in sorted(STORE_DIR.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                module = getattr(node, "module", None) if isinstance(node, ast.ImportFrom) else None
                if module and module.startswith("groundtruth.engine"):
                    offenders.append(f"{path.name}: {module}")
        assert (STORE_DIR / "sql.py").exists()
        assert not offenders, offenders
