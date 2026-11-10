"""The reproducibility replay harness (#42), and the cache it vouches for (#47).

The golden stored runs in ``tests/golden/stored_runs`` were made by the real simulated path:
submitted to the queue, run by the worker, stored, then read back exactly as a database replay
reads them. They are regenerated with the same switch as Viraj's golden snapshot::

    GROUNDTRUTH_UPDATE_GOLDEN=1 pytest tests/test_replay.py

One of them is Viraj's own spec (``tests/test_golden_reproducibility.py``: Kariba, seed
20260101, ``min_donors=5``, effect 0.0), and a test here checks it agrees with his snapshot, so
the two goldens cannot drift apart. There is no observed-data golden run: observed data cannot
be produced yet, and a made-up one would be a fabricated result (R6). The observed path is
tested with a constructed record instead.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from groundtruth.contracts.result import AnalysisResult, ErrorCode
from groundtruth.engine import ENGINE_VERSION
from groundtruth.platform import replay as replay_module
from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.datasets.synthetic import simulation_pin
from groundtruth.platform.jobs.queue import JobQueue
from groundtruth.platform.jobs.worker import Worker
from groundtruth.platform.replay import (
    LEGACY_TRUE_EFFECT,
    StoredRun,
    main,
    markdown,
    replay,
    replay_one,
    runs_from_database,
    runs_from_golden,
    write_golden,
)
from groundtruth.platform.store import migrate
from groundtruth.platform.store.database import create_db_engine, create_session_factory
from groundtruth.platform.store.sql import SqlEvidenceStore

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "stored_runs"
SEED = 20260101

GOLDEN_SPECS: dict[str, dict[str, Any]] = {
    # What POST /jobs submits for Kariba today: the simulation pinned with its effect.
    "kariba-completed": {"case": "kariba-redd", "effect": 0.06},
    # A refusal must replay as the same refusal.
    "kariba-refused": {"case": "kariba-redd", "effect": 0.06, "min_donors": 500},
    # Viraj's spec (tests/test_golden_reproducibility.py), recorded as runs are now recorded.
    "kariba-viraj-golden-spec": {"case": "kariba-redd", "effect": 0.0, "min_donors": 5},
    # A run submitted without a pin (before #42, or by the CLI): the worker's default effect.
    "kariba-legacy-unpinned": {"case": "kariba-redd", "effect": None},
    # A second case, so the set is not all one project.
    "alto-mayo-completed": {"case": "alto-mayo-redd", "effect": 0.06},
}


def _request(spec: dict[str, Any]) -> Any:
    pin = () if spec["effect"] is None else (simulation_pin(spec["effect"]),)
    return get_case(spec["case"]).to_request(
        data_mode="simulated", seed=SEED, min_donors=spec.get("min_donors"), datasets=pin
    )


def _database(tmp: Path) -> tuple[str, Any]:
    url = f"sqlite:///{tmp / 'replay.db'}"
    migrate.upgrade(url)
    return url, create_session_factory(create_db_engine(url))


def _run_through_the_worker(sessions: Any, requests: dict[str, Any]) -> dict[str, str]:
    """Submit each request and let a worker run them all. Returns name -> run id."""
    store = SqlEvidenceStore(sessions)
    queue = JobQueue(sessions)
    run_ids = {}
    for name, request in requests.items():
        store.upsert_case(get_case(request.case_id))
        run_ids[name] = queue.submit(request).run_id
    Worker(queue, poll_interval=0.01).run(exit_when_idle=True)
    return run_ids


@pytest.fixture(scope="module")
def golden_folder(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The committed golden runs, regenerated first when GROUNDTRUTH_UPDATE_GOLDEN=1."""
    if os.environ.get("GROUNDTRUTH_UPDATE_GOLDEN") == "1":
        url, sessions = _database(tmp_path_factory.mktemp("golden"))
        names = _run_through_the_worker(
            sessions, {name: _request(spec) for name, spec in GOLDEN_SPECS.items()}
        )
        by_id = {run.run_id: run for run in runs_from_database(url)}
        GOLDEN.mkdir(parents=True, exist_ok=True)
        for old in GOLDEN.glob("*.json"):
            old.unlink()
        for name, run_id in names.items():
            write_golden(by_id[run_id], GOLDEN / f"{name}.json")
    return GOLDEN


def _golden(folder: Path, name: str) -> StoredRun:
    return next(r for r in runs_from_golden(folder) if Path(r.source).stem == name)


def _with_result(run: StoredRun, **updates: Any) -> StoredRun:
    assert run.result is not None
    return StoredRun(**{**run.__dict__, "result": run.result.model_copy(update=updates)})


def _tampered_value(result: AnalysisResult) -> tuple[AnalysisResult, str]:
    """The result with one numeric evidence value nudged by 1%."""
    assert result.bundle is not None
    items = list(result.bundle.items)
    index = next(i for i, item in enumerate(items) if isinstance(item.value, float))
    items[index] = items[index].model_copy(update={"value": items[index].value * 1.01})
    bundle = result.bundle.model_copy(update={"items": tuple(items)})
    return result.model_copy(update={"bundle": bundle}), items[index].id


# --- acceptance 1: every stored run is replayed and its numbers compared ---------------------


class TestTheGoldenRunsReproduce:
    def test_the_golden_set_is_what_it_says(self, golden_folder):
        runs = {Path(r.source).stem: r for r in runs_from_golden(golden_folder)}
        assert set(runs) == set(GOLDEN_SPECS)
        assert runs["kariba-completed"].result.status.value == "completed"
        assert runs["kariba-refused"].result.error.is_refusal is True
        assert runs["alto-mayo-completed"].case_id == "alto-mayo-redd"
        for run in runs.values():
            assert run.request.spec_hash == run.spec_hash == run.result.spec_hash
            assert run.request.data_mode == "simulated"  # no observed golden runs (R6)

    def test_every_golden_run_replays_identically(self, golden_folder):
        report = replay(runs_from_golden(golden_folder))
        outcomes = {o.run_id: (o.outcome, o.reason, o.differences) for o in report.outcomes}
        assert all(o.outcome == "reproduced" for o in report.outcomes), outcomes
        assert not report.failed

    def test_a_run_without_a_pin_says_which_effect_was_assumed(self, golden_folder):
        outcome = replay_one(_golden(golden_folder, "kariba-legacy-unpinned"))
        assert outcome.outcome == "reproduced"
        assert f"({LEGACY_TRUE_EFFECT})" in outcome.notes[0]

    def test_viraj_spec_agrees_with_his_snapshot(self, golden_folder):
        """Same case, seed, min_donors and effect as tests/test_golden_reproducibility.py."""
        sys.path.insert(0, str(ROOT / "tests"))
        import test_golden_reproducibility as viraj

        theirs = json.loads((ROOT / "tests/golden/kariba_synthetic.json").read_text("utf-8"))
        ours = viraj._normalise(
            _golden(golden_folder, "kariba-viraj-golden-spec").result.model_dump(mode="json")
        )
        assert ours["bundle"] == theirs["bundle"]
        assert (ours["status"], ours["seed"]) == (theirs["status"], theirs["seed"])

    def test_the_replay_uses_the_stored_request_never_the_case(self, golden_folder, monkeypatch):
        from groundtruth.platform.cases import registry

        def forbidden(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("the replay rebuilt a request from the case definition")

        for name in ("get_case", "load_case", "load_all_cases"):
            if hasattr(registry, name):
                monkeypatch.setattr(registry, name, forbidden)
        assert replay_one(_golden(golden_folder, "kariba-completed")).outcome == "reproduced"


# --- acceptance 2 and 3: a mismatch in one version fails; across versions it is reported -----


class TestMismatchAndExpectedChange:
    def test_a_different_number_in_the_same_engine_version_is_a_mismatch(self, golden_folder):
        run = _golden(golden_folder, "kariba-completed")
        tampered, evidence_id = _tampered_value(run.result)
        outcome = replay_one(StoredRun(**{**run.__dict__, "result": tampered}))
        assert outcome.outcome == "mismatch"
        assert any(d.startswith(f"{evidence_id}: value") for d in outcome.differences)

    def test_a_tiny_float_difference_is_not_a_mismatch(self, golden_folder):
        run = _golden(golden_folder, "kariba-completed")
        items = list(run.result.bundle.items)
        i = next(i for i, item in enumerate(items) if isinstance(item.value, float))
        items[i] = items[i].model_copy(update={"value": items[i].value * (1 + 1e-12)})
        bundle = run.result.bundle.model_copy(update={"items": tuple(items)})
        assert replay_one(_with_result(run, bundle=bundle)).outcome == "reproduced"

    def test_a_refusal_must_replay_as_the_same_refusal(self, golden_folder):
        run = _golden(golden_folder, "kariba-refused")
        assert replay_one(run).outcome == "reproduced"
        other = run.result.error.model_copy(update={"code": ErrorCode.INSUFFICIENT_DATA})
        outcome = replay_one(_with_result(run, error=other))
        assert outcome.outcome == "mismatch" and "error (code, stage)" in outcome.differences[0]

    def test_a_different_engine_version_is_an_expected_change(self, golden_folder):
        run = _golden(golden_folder, "kariba-completed")
        tampered, _ = _tampered_value(run.result)
        old_engine = tampered.engine.model_copy(update={"engine_version": "0.0.1-old"})
        outcome = replay_one(
            StoredRun(
                **{**run.__dict__, "result": tampered.model_copy(update={"engine": old_engine})}
            )
        )
        assert outcome.outcome == "expected_change"
        assert outcome.reason == f"engine 0.0.1-old -> {ENGINE_VERSION}"

    def test_the_command_fails_only_on_a_same_version_mismatch(self, golden_folder, tmp_path):
        for name in ("same-version", "old-version"):
            run = _golden(golden_folder, "kariba-completed")
            tampered, _ = _tampered_value(run.result)
            if name == "old-version":
                engine = tampered.engine.model_copy(update={"engine_version": "0.0.1-old"})
                tampered = tampered.model_copy(update={"engine": engine})
            folder = tmp_path / name
            folder.mkdir()
            write_golden(StoredRun(**{**run.__dict__, "result": tampered}), folder / "run.json")
        assert main(["--golden", str(tmp_path / "same-version")]) == 1
        assert main(["--golden", str(tmp_path / "old-version")]) == 0
        assert main(["--golden", str(golden_folder)]) == 0

    def test_the_report_lists_expected_changes_apart_from_mismatches(self, golden_folder):
        run = _golden(golden_folder, "kariba-completed")
        tampered, _ = _tampered_value(run.result)
        engine = tampered.engine.model_copy(update={"engine_version": "0.0.1-old"})
        old = StoredRun(
            **{**run.__dict__, "result": tampered.model_copy(update={"engine": engine})}
        )
        bad = StoredRun(**{**run.__dict__, "run_id": "run_bad", "result": tampered})
        text = markdown(replay([old, bad]), title="t")
        assert "Mismatches within an engine version" in text
        assert "Expected changes across engine versions (not failures)" in text


# --- what cannot be replayed honestly is skipped, with the reason ----------------------------


class TestSkipped:
    def test_an_observed_run_is_skipped_never_replayed_on_simulated_data(
        self, golden_folder, monkeypatch
    ):
        def never(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("an observed run was replayed against simulated data")

        monkeypatch.setattr(replay_module, "synthetic_access", never)
        stored = _golden(golden_folder, "kariba-completed")
        observed = get_case("kariba-redd").to_request(data_mode="observed", seed=SEED)
        run = StoredRun(**{**stored.__dict__, "request": observed, "spec_hash": observed.spec_hash})
        outcome = replay_one(run, engine=never)
        assert outcome.outcome == "skipped"
        assert "observed data unavailable" in outcome.reason
        assert "never against simulated data" in outcome.reason

    def test_a_run_with_no_result_or_no_request_is_skipped(self, golden_folder):
        stored = _golden(golden_folder, "kariba-completed")
        no_result = StoredRun(**{**stored.__dict__, "result": None, "status": "failed"})
        no_request = StoredRun(**{**stored.__dict__, "request": None})
        assert "no result stored (the job is failed)" in replay_one(no_result).reason
        assert "no stored request" in replay_one(no_request).reason

    def test_a_golden_file_whose_request_does_not_hash_to_its_run_is_refused(
        self, golden_folder, tmp_path
    ):
        document = json.loads((golden_folder / "kariba-completed.json").read_text("utf-8"))
        document["spec_hash"] = "0" * 32
        (tmp_path / "x.json").write_text(json.dumps(document), encoding="utf-8")
        (outcome,) = replay(runs_from_golden(tmp_path)).outcomes
        assert outcome.outcome == "skipped" and "hashes to" in outcome.reason


# --- a real database, and the cache (#47) ------------------------------------------------------


class TestDatabaseReplay:
    def test_every_stored_run_in_a_database_is_accounted_for(self, tmp_path, capsys):
        url, sessions = _database(tmp_path)
        _run_through_the_worker(
            sessions,
            {
                "pinned": _request({"case": "kariba-redd", "effect": 0.06}),
                "legacy": _request({"case": "kariba-redd", "effect": None, "min_donors": 40}),
            },
        )
        assert main(["--database-url", url]) == 0
        printed = capsys.readouterr().out
        assert "reproduced: **2**" in printed and "mismatch: **0**" in printed

    def test_a_cache_hit_is_a_result_that_replays_identically(self, tmp_path):
        """#47: a repeated spec returns the stored run, and that run reproduces."""
        url, sessions = _database(tmp_path)
        request = _request({"case": "kariba-redd", "effect": 0.06})
        (first,) = _run_through_the_worker(sessions, {"first": request}).values()
        again = JobQueue(sessions).submit(request)
        assert again.from_cache is True and again.run_id == first
        (run,) = [r for r in runs_from_database(url) if r.run_id == first]
        assert replay_one(run).outcome == "reproduced"

    def test_a_different_effect_is_a_different_spec_so_never_a_cache_hit(self, tmp_path):
        _, sessions = _database(tmp_path)
        _run_through_the_worker(sessions, {"a": _request({"case": "kariba-redd", "effect": 0.06})})
        other = JobQueue(sessions).submit(_request({"case": "kariba-redd", "effect": 0.0}))
        assert other.from_cache is False


# --- acceptance 4: on a schedule -------------------------------------------------------------


def test_the_replay_runs_daily_and_by_hand_on_every_supported_python():
    workflow = yaml.safe_load((ROOT / ".github/workflows/replay.yml").read_text("utf-8"))
    triggers = workflow[True] if True in workflow else workflow["on"]  # YAML reads `on` as True
    assert triggers["schedule"] == [{"cron": "30 4 * * *"}]
    assert "workflow_dispatch" in triggers
    job = next(iter(workflow["jobs"].values()))
    assert job["strategy"]["matrix"]["python-version"] == ["3.11", "3.12", "3.13"]
    runs = " ".join(str(step.get("run", "")) for step in job["steps"])
    assert "groundtruth.platform.replay --golden tests/golden/stored_runs" in runs
