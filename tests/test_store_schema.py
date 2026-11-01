"""Database schema and migrations (issue #14).

Everything runs on SQLite, so no database needs installing. PostgreSQL is covered
by rendering the DDL and the migration SQL for that dialect, which catches the
failures that matter without a server: a type SQLite accepts but PostgreSQL does
not, or a trigger written only for one dialect.
"""

from __future__ import annotations

import ast
import io
import pathlib
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from groundtruth.contracts.errors import ConfigurationError
from groundtruth.contracts.evidence import Evidence, EvidenceBundle
from groundtruth.contracts.identifiers import new_run_id
from groundtruth.contracts.provenance import Provenance
from groundtruth.contracts.result import AnalysisStatus
from groundtruth.contracts.types import (
    STANDARD_CAVEATS,
    Confidence,
    VerdictLabel,
    VerificationVerdict,
)
from groundtruth.contracts.version import CONTRACT_VERSION
from groundtruth.platform.store import database, migrate
from groundtruth.platform.store.database import create_db_engine, create_session_factory
from groundtruth.platform.store.models import (
    NOT_ASSESSED,
    AnalysisRunRow,
    Base,
    CaseRow,
    DatasetRow,
    EvidenceBundleRow,
    IncompatibleBundleError,
    JobRow,
    load_bundle,
)

TABLES = {"cases", "analysis_runs", "evidence_bundles", "datasets", "jobs"}
STORE_DIR = (
    pathlib.Path(__file__).resolve().parents[1]
    / "packages"
    / "groundtruth"
    / "src"
    / "groundtruth"
    / "platform"
    / "store"
)


@pytest.fixture
def url(tmp_path: pathlib.Path) -> str:
    return f"sqlite:///{tmp_path / 'groundtruth.db'}"


@pytest.fixture
def engine(url: str) -> Engine:
    """A database at the latest revision, reached through the real migration."""
    migrate.upgrade(url)
    return create_db_engine(url)


@pytest.fixture
def session(engine: Engine) -> Session:
    with create_session_factory(engine)() as s:
        yield s


def _case(case_id: str = "test-case") -> CaseRow:
    return CaseRow(
        case_id=case_id,
        name="Test Project",
        country="Zambia",
        indicator="ndvi",
        status="scaffolded",
        definition={"case_id": case_id},
    )


def _run(run_id: str | None = None, case_id: str = "test-case", **overrides) -> AnalysisRunRow:
    fields = {
        "run_id": run_id or new_run_id(),
        "case_id": case_id,
        "spec_hash": "a" * 32,
        "status": "succeeded",
        "engine_status": "completed",
        "data_mode": "simulated",
        "is_simulated": True,
        "seed": 20260101,
        "contract_version": CONTRACT_VERSION,
        "dataset_refs": [],
    }
    fields.update(overrides)
    return AnalysisRunRow(**fields)


def _bundle_row(run_id: str, bundle: EvidenceBundle, **overrides) -> EvidenceBundleRow:
    fields = {
        "run_id": run_id,
        "case_id": bundle.case_id,
        "contract_version": CONTRACT_VERSION,
        "bundle": bundle.model_dump(mode="json"),
        "verdict_label": bundle.verdict.label.value if bundle.verdict else NOT_ASSESSED,
        "item_count": len(bundle),
    }
    fields.update(overrides)
    return EvidenceBundleRow(**fields)


@pytest.fixture
def rich_bundle() -> EvidenceBundle:
    """A bundle that exercises the awkward parts: intervals, nesting, datetimes, floats."""
    prov = Provenance.computed(
        source="synthetic fixture",
        method="synthetic-control",
        stage="causal",
        parameters={"ridge": 0.01, "donors": [1, 2, 3]},
    )
    items = (
        Evidence(
            id="effect.point_estimate",
            label="Estimated incremental effect on ndvi",
            value=0.04213456789012345,
            unit="ndvi",
            confidence=Confidence(lower=-0.0123, upper=0.0987, level=0.9, kind="permutation"),
            provenance=prov,
            qualifiers={"observed_not_causal": False, "nested": {"a": [1, 2.5, "x"]}},
        ),
        Evidence(id="placebo.p_value", label="Permutation p-value", value=0.0385, provenance=prov),
        Evidence(id="matching.n_donors_admitted", label="Donors", value=32, provenance=prov),
        Evidence(id="flag.simulated", label="Simulated", value=True, provenance=prov),
    )
    verdict = VerificationVerdict(
        label=VerdictLabel.INCONCLUSIVE,
        rationale="Not commensurable.",
        caveats=STANDARD_CAVEATS,
        supporting_evidence_ids=("effect.point_estimate",),
    )
    return EvidenceBundle(
        case_id="test-case", items=items, verdict=verdict, warnings=("SIMULATED DATA",)
    )


def _add_case(session: Session, *case_ids: str) -> None:
    """Write case rows first. Plain foreign keys give the unit of work no insert order."""
    session.add_all([_case(c) for c in (case_ids or ("test-case",))])
    session.flush()


def _store(session: Session, bundle: EvidenceBundle, run_id: str | None = None) -> str:
    run_id = run_id or new_run_id()
    if session.get(CaseRow, bundle.case_id) is None:
        _add_case(session, bundle.case_id)
    session.add(_run(run_id, bundle.case_id))
    session.flush()
    session.add(_bundle_row(run_id, bundle))
    session.commit()
    return run_id


# --- migrations apply and roll back ---------------------------------------------


class TestMigrations:
    def _tables(self, url: str) -> set[str]:
        return set(sa.inspect(create_db_engine(url)).get_table_names()) - {"alembic_version"}

    def _objects(self, url: str, kind: str) -> set[str]:
        with create_db_engine(url).connect() as conn:
            rows = conn.execute(sa.text(f"SELECT name FROM sqlite_master WHERE type='{kind}'"))
            return {r[0] for r in rows if not r[0].startswith("sqlite_")}

    def test_upgrade_creates_all_five_tables(self, url: str):
        migrate.upgrade(url)
        assert self._tables(url) == TABLES

    def test_downgrade_removes_everything_it_created(self, url: str):
        migrate.upgrade(url)
        migrate.downgrade(url)
        assert self._tables(url) == set()
        assert self._objects(url, "trigger") == set()
        assert self._objects(url, "index") == set()

    def test_the_cycle_can_be_repeated(self, url: str):
        """A downgrade that leaves debris breaks the next upgrade."""
        migrate.upgrade(url)
        migrate.downgrade(url)
        migrate.upgrade(url)
        assert self._tables(url) == TABLES

    def test_upgrade_is_idempotent_at_head(self, url: str):
        migrate.upgrade(url)
        migrate.upgrade(url)
        assert self._tables(url) == TABLES

    def test_models_and_migration_describe_the_same_schema(self, engine: Engine):
        """Drift guard: editing a model without a migration fails here."""
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == []

    def test_constraint_and_index_names_match(self, engine: Engine):
        """``compare_metadata`` ignores names; downgrades and later migrations depend on them."""
        inspector = sa.inspect(engine)
        for table in Base.metadata.sorted_tables:
            real = {
                "pk": {inspector.get_pk_constraint(table.name)["name"]},
                "fk": {fk["name"] for fk in inspector.get_foreign_keys(table.name)},
                "uq": {u["name"] for u in inspector.get_unique_constraints(table.name)},
                "ck": {c["name"] for c in inspector.get_check_constraints(table.name)},
                "ix": {i["name"] for i in inspector.get_indexes(table.name)},
            }
            declared = {
                "pk": {table.primary_key.name},
                "fk": {c.name for c in table.constraints if isinstance(c, sa.ForeignKeyConstraint)},
                "uq": {c.name for c in table.constraints if isinstance(c, sa.UniqueConstraint)},
                "ck": {c.name for c in table.constraints if isinstance(c, sa.CheckConstraint)},
                "ix": {i.name for i in table.indexes},
            }
            assert real == declared, table.name

    def test_postgresql_ddl_uses_jsonb(self):
        ddl = str(CreateTable(EvidenceBundleRow.__table__).compile(dialect=postgresql.dialect()))
        assert "bundle JSONB NOT NULL" in ddl

    def test_postgresql_migration_renders_with_its_own_trigger(self):
        """No PostgreSQL server needed: render the offline SQL and read it."""
        buffer = io.StringIO()
        config = migrate.alembic_config("postgresql://user:pw@localhost/db", output_buffer=buffer)
        command.upgrade(config, "head", sql=True)
        sql = buffer.getvalue()
        assert "JSONB" in sql
        assert "CREATE FUNCTION forbid_evidence_bundle_update()" in sql
        assert "CREATE TRIGGER evidence_bundles_immutable BEFORE UPDATE" in sql

        buffer.seek(0), buffer.truncate()
        command.downgrade(config, "0001:base", sql=True)
        down = buffer.getvalue()
        assert "DROP TRIGGER evidence_bundles_immutable ON evidence_bundles" in down
        assert "DROP FUNCTION forbid_evidence_bundle_update()" in down


# --- a bundle survives the database ---------------------------------------------


class TestRoundTrip:
    def test_bundle_round_trips_unchanged(
        self, engine: Engine, session: Session, rich_bundle: EvidenceBundle
    ):
        run_id = _store(session, rich_bundle)

        with create_session_factory(engine)() as fresh:  # a new session: nothing cached
            row = fresh.get(EvidenceBundleRow, run_id)
            loaded = load_bundle(row)

        assert loaded == rich_bundle
        assert loaded.to_json() == rich_bundle.to_json()

    def test_a_bundle_without_a_verdict_projects_as_not_assessed(self, session: Session):
        bundle = EvidenceBundle(case_id="no-verdict")
        run_id = _store(session, bundle)
        assert session.get(EvidenceBundleRow, run_id).verdict_label == NOT_ASSESSED

    def test_projection_columns_describe_the_document(
        self, session: Session, rich_bundle: EvidenceBundle
    ):
        row = session.get(EvidenceBundleRow, _store(session, rich_bundle))
        assert row.verdict_label == "inconclusive"
        assert row.item_count == 4
        assert row.case_id == rich_bundle.case_id

    def test_a_refusal_is_stored_on_the_run_without_a_bundle(self, session: Session):
        """A refused run is a legitimate outcome and must be persistable (ADR-008)."""
        _add_case(session)
        session.add(
            _run(
                "run_refused00000001",
                status="succeeded",
                engine_status="refused",
                error_code="donor_pool_inadequate",
                error={"code": "donor_pool_inadequate", "detail": {"found": 6, "required": 10}},
            )
        )
        session.commit()
        row = session.get(AnalysisRunRow, "run_refused00000001")
        assert row.error["detail"]["found"] == 6
        assert session.get(EvidenceBundleRow, "run_refused00000001") is None

    def test_absent_json_is_sql_null_not_json_null(self, engine: Engine, session: Session):
        _add_case(session)
        session.add(_run("run_nullerror0000001"))
        session.commit()
        with engine.connect() as conn:
            count = conn.execute(
                sa.text("SELECT count(*) FROM analysis_runs WHERE error IS NULL")
            ).scalar()
        assert count == 1


class TestContractVersioning:
    def _row(self, bundle: EvidenceBundle, version: str) -> EvidenceBundleRow:
        return _bundle_row("run_versioned0000001", bundle, contract_version=version)

    def test_a_bundle_stored_under_1_0_0_loads_after_a_minor_bump(
        self, rich_bundle: EvidenceBundle
    ):
        row = self._row(rich_bundle, "1.0.0")
        assert load_bundle(row, consumer_version="1.1.0") == rich_bundle
        assert load_bundle(row, consumer_version="1.9.3") == rich_bundle

    def test_the_stored_version_is_what_the_row_was_written_under(
        self, session: Session, rich_bundle: EvidenceBundle
    ):
        row = session.get(EvidenceBundleRow, _store(session, rich_bundle))
        assert row.contract_version == CONTRACT_VERSION

    def test_a_bundle_from_a_newer_minor_is_refused(self, rich_bundle: EvidenceBundle):
        with pytest.raises(IncompatibleBundleError, match=r"1\.3\.0"):
            load_bundle(self._row(rich_bundle, "1.3.0"), consumer_version="1.0.0")

    def test_a_bundle_from_another_major_is_refused(self, rich_bundle: EvidenceBundle):
        with pytest.raises(IncompatibleBundleError):
            load_bundle(self._row(rich_bundle, "2.0.0"), consumer_version="1.4.0")
        with pytest.raises(IncompatibleBundleError):
            load_bundle(self._row(rich_bundle, "1.0.0"), consumer_version="2.0.0")

    def test_a_bundle_older_than_the_supported_floor_is_refused(self, rich_bundle: EvidenceBundle):
        with pytest.raises(IncompatibleBundleError):
            load_bundle(self._row(rich_bundle, "0.9.0"), consumer_version="0.9.5")

    def test_the_current_contract_reads_its_own_bundles(self, rich_bundle: EvidenceBundle):
        assert load_bundle(self._row(rich_bundle, CONTRACT_VERSION)) == rich_bundle


# --- bundles are immutable ------------------------------------------------------


class TestImmutability:
    def test_a_bundle_cannot_be_updated(self, engine: Engine, session: Session, rich_bundle):
        run_id = _store(session, rich_bundle)
        with engine.begin() as conn, pytest.raises(sa.exc.DBAPIError, match="immutable"):
            conn.execute(
                sa.text("UPDATE evidence_bundles SET verdict_label = 'x' WHERE run_id = :r"),
                {"r": run_id},
            )

    def test_an_orm_edit_is_rejected_by_the_database(self, session: Session, rich_bundle):
        row = session.get(EvidenceBundleRow, _store(session, rich_bundle))
        row.verdict_label = "consistent_with_claim"
        with pytest.raises(sa.exc.DBAPIError, match="immutable"):
            session.commit()
        session.rollback()

    def test_a_rerun_is_a_new_row_and_leaves_the_original_alone(
        self, session: Session, rich_bundle: EvidenceBundle
    ):
        first = _store(session, rich_bundle)
        second = _store(session, rich_bundle)

        assert first != second
        rows = session.scalars(sa.select(EvidenceBundleRow)).all()
        assert {r.run_id for r in rows} == {first, second}
        # Same specification, two runs: the cache key repeats, the identity does not.
        hashes = session.scalars(sa.select(AnalysisRunRow.spec_hash)).all()
        assert hashes[0] == hashes[1]
        assert load_bundle(session.get(EvidenceBundleRow, first)) == rich_bundle

    def test_a_run_status_can_still_change(self, session: Session):
        """Only bundles are immutable: a run moves queued -> running -> succeeded."""
        _add_case(session)
        run = _run("run_lifecycle0000001", status="queued", engine_status=None)
        session.add(run)
        session.commit()
        run.status = "running"
        session.commit()
        assert session.get(AnalysisRunRow, "run_lifecycle0000001").status == "running"


# --- indexes support the listing queries ----------------------------------------


class TestIndexes:
    def _plan(self, engine: Engine, sql: str) -> str:
        with engine.connect() as conn:
            rows = conn.execute(sa.text("EXPLAIN QUERY PLAN " + sql)).all()
        return " | ".join(str(r[-1]) for r in rows)

    @pytest.mark.parametrize(
        ("sql", "index"),
        [
            (
                "SELECT run_id FROM analysis_runs WHERE case_id = 'k' ORDER BY created_at DESC",
                "ix_analysis_runs_case_id_created_at_run_id",
            ),
            (
                "SELECT run_id FROM analysis_runs WHERE status = 'queued' ORDER BY created_at",
                "ix_analysis_runs_status_created_at_run_id",
            ),
            (
                "SELECT run_id FROM analysis_runs ORDER BY created_at DESC LIMIT 20",
                "ix_analysis_runs_created_at_run_id",
            ),
            (
                "SELECT run_id FROM analysis_runs WHERE spec_hash = 'abc'",
                "ix_analysis_runs_spec_hash",
            ),
            (
                "SELECT run_id FROM evidence_bundles WHERE case_id = 'k' ORDER BY created_at DESC",
                "ix_evidence_bundles_case_id_created_at",
            ),
            (
                "SELECT run_id FROM evidence_bundles "
                "WHERE verdict_label = 'inconclusive' ORDER BY created_at DESC",
                "ix_evidence_bundles_verdict_label_created_at",
            ),
            (
                "SELECT run_id FROM evidence_bundles ORDER BY created_at DESC LIMIT 20",
                "ix_evidence_bundles_created_at",
            ),
            (
                "SELECT run_id FROM jobs WHERE available_at <= CURRENT_TIMESTAMP",
                "ix_jobs_available_at",
            ),
        ],
    )
    def test_listing_query_uses_its_index(self, engine: Engine, sql: str, index: str):
        plan = self._plan(engine, sql)
        assert index in plan, plan


# --- the schema refuses what it must refuse -------------------------------------


class TestConstraints:
    def test_every_analysis_status_is_accepted(self, session: Session):
        """Guards the hand-written CHECK literals against the contract enum."""
        _add_case(session)
        for status in AnalysisStatus:
            session.add(_run(status=status.value))
        session.commit()
        assert session.scalar(sa.select(sa.func.count()).select_from(AnalysisRunRow)) == len(
            AnalysisStatus
        )

    @pytest.mark.parametrize(
        "overrides",
        [
            {"status": "finished"},
            {"data_mode": "real"},
            {"data_mode": "observed", "is_simulated": True},
            {"data_mode": "simulated", "is_simulated": False},
        ],
        ids=["status", "data-mode", "observed-but-simulated", "simulated-but-not-flagged"],
    )
    def test_a_run_cannot_be_mislabelled(self, session: Session, overrides: dict):
        _add_case(session)
        session.add(_run(**overrides))
        with pytest.raises(sa.exc.IntegrityError):
            session.commit()

    def test_a_run_needs_a_known_case(self, session: Session):
        session.add(_run(case_id="no-such-case"))
        with pytest.raises(sa.exc.IntegrityError):
            session.commit()

    def test_a_bundle_cannot_disagree_with_its_run_about_the_case(
        self, session: Session, rich_bundle: EvidenceBundle
    ):
        _add_case(session, "test-case", "other-case")
        session.add(_run("run_mismatch0000001", case_id="test-case"))
        session.flush()
        session.add(_bundle_row("run_mismatch0000001", rich_bundle, case_id="other-case"))
        with pytest.raises(sa.exc.IntegrityError):
            session.commit()

    def test_a_run_has_at_most_one_bundle(self, session: Session, rich_bundle: EvidenceBundle):
        run_id = _store(session, rich_bundle)
        session.add(_bundle_row(run_id, rich_bundle))
        with pytest.raises(sa.exc.IntegrityError):
            session.commit()

    def test_an_unknown_case_status_is_refused(self, session: Session):
        case = _case()
        case.status = "published"
        session.add(case)
        with pytest.raises(sa.exc.IntegrityError):
            session.commit()

    def test_a_job_belongs_to_one_run_and_is_unique_per_run(self, session: Session):
        _add_case(session)
        session.add(_run("run_jobbed00000001"))
        session.flush()
        session.add(JobRow(run_id="run_jobbed00000001"))
        session.commit()

        job = session.get(JobRow, "run_jobbed00000001")
        assert (job.attempts, job.max_attempts, job.locked_by) == (0, 3, None)

        # A core insert, so it is the database that refuses, not the ORM identity map.
        with pytest.raises(sa.exc.IntegrityError):
            session.execute(sa.insert(JobRow).values(run_id="run_jobbed00000001"))

    def test_a_job_cannot_point_at_a_missing_run(self, session: Session):
        session.add(JobRow(run_id="run_missing00000001"))
        with pytest.raises(sa.exc.IntegrityError):
            session.commit()

    def test_a_dataset_is_identified_by_id_version_and_provider(self, session: Session):
        def dataset(provider: str) -> DatasetRow:
            return DatasetRow(
                dataset_id="sentinel2-l2a", version="2024.1", provider=provider, is_synthetic=False
            )

        session.add_all([dataset("google-earth-engine"), dataset("copernicus")])
        session.commit()
        session.add(dataset("copernicus"))
        with pytest.raises(sa.exc.IntegrityError):
            session.commit()


# --- configuration --------------------------------------------------------------


class TestConfiguration:
    def test_no_database_configured_is_an_error_not_a_default(self, monkeypatch):
        monkeypatch.setattr(database, "get_settings", lambda: SimpleNamespace(database_url=None))
        with pytest.raises(ConfigurationError, match="DATABASE_URL"):
            create_db_engine()

    def test_the_configured_url_is_used_when_none_is_given(self, monkeypatch, url: str):
        monkeypatch.setattr(database, "get_settings", lambda: SimpleNamespace(database_url=url))
        assert create_db_engine().url == sa.engine.make_url(url)

    def test_an_explicit_url_wins(self, monkeypatch, url: str):
        monkeypatch.setattr(
            database, "get_settings", lambda: SimpleNamespace(database_url="sqlite:///other.db")
        )
        assert create_db_engine(url).url == sa.engine.make_url(url)

    def test_a_url_with_a_percent_encoded_password_survives_the_migration_config(self):
        """configparser treats '%' specially; a password must not break migrations."""
        config = migrate.alembic_config("postgresql://user:p%40ss@localhost/db")
        assert config.get_main_option("sqlalchemy.url") == "postgresql://user:p%40ss@localhost/db"


# --- the boundary ---------------------------------------------------------------


class TestBoundary:
    """These read the real source path.

    ``test_contract_boundary.py`` is the repository-wide check; these guard the new
    code directly and fail if the directory they scan is empty, so they cannot pass
    vacuously.
    """

    def _imports(self) -> list[tuple[pathlib.Path, str]]:
        found = []
        for path in sorted(STORE_DIR.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.module:
                    found.append((path, node.module))
                elif isinstance(node, ast.Import):
                    found.extend((path, alias.name) for alias in node.names)
        return found

    def test_the_scan_actually_found_the_store(self):
        assert any(p.name == "models.py" for p, _ in self._imports())

    def test_the_store_never_imports_the_engine(self):
        offenders = [
            f"{p.name}: {m}" for p, m in self._imports() if m.startswith("groundtruth.engine")
        ]
        assert not offenders, offenders

    def test_importing_the_store_package_does_not_require_sqlalchemy(self):
        """``store/__init__`` stays free of SQLAlchemy so the ``db`` extra remains optional."""
        init = ast.parse((STORE_DIR / "__init__.py").read_text(encoding="utf-8"))
        assert not [n for n in ast.walk(init) if isinstance(n, ast.Import | ast.ImportFrom)]
