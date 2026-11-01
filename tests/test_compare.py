"""The bundle diff and the "may these runs be compared?" rules (issue #35).

Pure functions over contract types: no database, no HTTP. The same code backs the
comparison endpoint and, later, continuous monitoring.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from groundtruth.contracts.evidence import Evidence, EvidenceBundle
from groundtruth.contracts.provenance import Provenance
from groundtruth.contracts.types import (
    STANDARD_CAVEATS,
    Confidence,
    VerdictLabel,
    VerificationVerdict,
)
from groundtruth.platform.compare.comparison import RunSide, compare_runs
from groundtruth.platform.compare.diff import diff_bundles, values_equal
from groundtruth.platform.store.interface import RunSummary


def _prov(method: str = "synthetic-control", **parameters) -> Provenance:
    return Provenance.computed(source="test", method=method, stage="causal", parameters=parameters)


def _item(evidence_id: str, value=1.0, *, unit: str = "", confidence=None, qualifiers=None,
          label: str = "A label", provenance: Provenance | None = None) -> Evidence:  # fmt: skip
    return Evidence(
        id=evidence_id,
        label=label,
        value=value,
        unit=unit,
        confidence=confidence,
        provenance=provenance or _prov(),
        qualifiers=qualifiers or {},
    )


def _bundle(*items: Evidence, verdict=None, warnings=()) -> EvidenceBundle:
    return EvidenceBundle(case_id="c", items=items, verdict=verdict, warnings=warnings)


def _verdict(label=VerdictLabel.INCONCLUSIVE, rationale="r", ratio=None) -> VerificationVerdict:
    return VerificationVerdict(
        label=label, rationale=rationale, divergence_ratio=ratio, caveats=STANDARD_CAVEATS
    )


def _by_id(diff):
    return {i.id: i for i in diff.items}


# --- numbers and containers -----------------------------------------------------


class TestValuesEqual:
    def test_numbers_compare_as_numbers(self):
        assert values_equal(1, 1.0)
        assert values_equal(0.1 + 0.2, 0.3)  # float noise is inside the tolerance

    def test_the_tolerance_is_relative(self):
        assert values_equal(1e9, 1e9 * (1 + 1e-10))
        assert not values_equal(1e9, 1e9 * (1 + 1e-6))
        assert not values_equal(1e-9, 2e-9)  # small numbers are not "close" by being small

    def test_a_number_is_never_close_to_zero_by_accident(self):
        assert values_equal(0.0, 0.0)
        assert values_equal(0.0, -0.0)
        assert not values_equal(0.0, 1e-300)

    def test_bool_is_not_a_number(self):
        assert not values_equal(True, 1)
        assert not values_equal(1, True)
        assert values_equal(True, True)

    def test_two_nans_are_the_same_non_value(self):
        assert values_equal(math.nan, math.nan)
        assert not values_equal(math.nan, 1.0)

    def test_strings_compare_exactly(self):
        assert values_equal("a", "a")
        assert not values_equal("a", "A")
        assert not values_equal("1", 1)

    def test_containers_compare_element_by_element(self):
        assert values_equal({"a": [1, 2.0]}, {"a": [1.0, 2]})
        assert not values_equal({"a": [1, 2]}, {"a": [1, 3]})
        assert not values_equal({"a": 1}, {"a": 1, "b": 2})
        assert not values_equal([1, 2], [1, 2, 3])
        assert values_equal((1, 2), [1, 2])


# --- the diff -------------------------------------------------------------------


class TestDiffBundles:
    def test_every_id_is_added_removed_changed_or_unchanged(self):
        base = _bundle(_item("a.same"), _item("b.changes", 1.0), _item("c.removed"))
        cand = _bundle(_item("a.same"), _item("b.changes", 2.0), _item("d.added"))

        diff = diff_bundles(base, cand)

        statuses = {i.id: i.status for i in diff.items}
        assert statuses == {
            "a.same": "unchanged",
            "b.changes": "changed",
            "c.removed": "removed",
            "d.added": "added",
        }
        assert diff.summary.model_dump() == {"added": 1, "removed": 1, "changed": 1, "unchanged": 1}

    def test_items_come_back_sorted_by_id(self):
        diff = diff_bundles(_bundle(_item("z.z"), _item("a.a")), _bundle(_item("m.m")))
        assert [i.id for i in diff.items] == ["a.a", "m.m", "z.z"]

    def test_identical_bundles_are_entirely_unchanged(self):
        bundle = _bundle(_item("a.a"), _item("b.b", "text"), _item("c.c", True))
        diff = diff_bundles(bundle, bundle)
        assert {i.status for i in diff.items} == {"unchanged"}
        assert diff.verdict.label_changed is False

    def test_a_changed_number_reports_the_delta(self):
        diff = diff_bundles(_bundle(_item("e.e", 0.04)), _bundle(_item("e.e", 0.06)))
        item = _by_id(diff)["e.e"]
        assert [c.field for c in item.changes] == ["value"]
        assert item.changes[0].before == 0.04 and item.changes[0].after == 0.06
        assert item.delta == pytest.approx(0.02)
        assert item.relative_delta == pytest.approx(0.5)

    def test_a_zero_baseline_has_no_relative_delta(self):
        item = _by_id(diff_bundles(_bundle(_item("e.e", 0.0)), _bundle(_item("e.e", 1.0))))["e.e"]
        assert item.delta == 1.0 and item.relative_delta is None

    def test_a_non_numeric_value_has_no_delta(self):
        item = _by_id(diff_bundles(_bundle(_item("e.e", "x")), _bundle(_item("e.e", "y"))))["e.e"]
        assert item.status == "changed" and item.delta is None

    def test_a_bool_flipping_is_a_change_not_a_delta(self):
        item = _by_id(diff_bundles(_bundle(_item("e.e", True)), _bundle(_item("e.e", False))))[
            "e.e"
        ]
        assert item.status == "changed" and item.delta is None

    def test_float_noise_inside_the_tolerance_is_unchanged(self):
        diff = diff_bundles(_bundle(_item("e.e", 0.3)), _bundle(_item("e.e", 0.1 + 0.2)))
        assert _by_id(diff)["e.e"].status == "unchanged"

    def test_the_tolerance_can_be_tightened(self):
        base, cand = _bundle(_item("e.e", 1.0)), _bundle(_item("e.e", 1.0 + 1e-7))
        assert _by_id(diff_bundles(base, cand))["e.e"].status == "changed"
        assert _by_id(diff_bundles(base, cand, rel_tol=1e-3))["e.e"].status == "unchanged"

    def test_a_changed_unit_is_a_change(self):
        diff = diff_bundles(
            _bundle(_item("e.e", 1.0, unit="ndvi")), _bundle(_item("e.e", 1.0, unit="evi"))
        )
        assert [c.field for c in _by_id(diff)["e.e"].changes] == ["unit"]

    def test_the_interval_kind_is_part_of_the_result(self):
        """A sensitivity envelope is not a confidence interval: a kind change is a change."""
        a = Confidence(lower=0.0, upper=1.0, kind="permutation")
        b = Confidence(lower=0.0, upper=1.0, kind="sensitivity-envelope")
        diff = diff_bundles(
            _bundle(_item("e.e", confidence=a)), _bundle(_item("e.e", confidence=b))
        )
        item = _by_id(diff)["e.e"]
        assert [c.field for c in item.changes] == ["confidence"]
        assert item.changes[0].before["kind"] == "permutation"
        assert item.changes[0].after["kind"] == "sensitivity-envelope"

    def test_an_interval_appearing_or_disappearing_is_a_change(self):
        interval = Confidence(lower=0.0, upper=1.0)
        diff = diff_bundles(_bundle(_item("e.e")), _bundle(_item("e.e", confidence=interval)))
        assert [c.field for c in _by_id(diff)["e.e"].changes] == ["confidence"]

    def test_interval_bounds_use_the_tolerance(self):
        a = Confidence(lower=0.1 + 0.2, upper=1.0)
        b = Confidence(lower=0.3, upper=1.0)
        diff = diff_bundles(
            _bundle(_item("e.e", confidence=a)), _bundle(_item("e.e", confidence=b))
        )
        assert _by_id(diff)["e.e"].status == "unchanged"

    def test_changed_qualifiers_are_a_change(self):
        diff = diff_bundles(
            _bundle(_item("e.e", qualifiers={"observed_not_causal": True})),
            _bundle(_item("e.e", qualifiers={"observed_not_causal": False})),
        )
        assert [c.field for c in _by_id(diff)["e.e"].changes] == ["qualifiers"]

    def test_the_same_value_derived_differently_is_flagged(self):
        """Same number, different method or parameters: the number means something else."""
        diff = diff_bundles(
            _bundle(_item("e.e", 1.0, provenance=_prov(ridge=0.01))),
            _bundle(_item("e.e", 1.0, provenance=_prov(ridge=0.5))),
        )
        item = _by_id(diff)["e.e"]
        assert item.status == "changed" and [c.field for c in item.changes] == ["provenance"]
        assert item.changes[0].before["fingerprint"] != item.changes[0].after["fingerprint"]

    def test_retrieval_time_alone_is_not_a_change(self):
        """The fingerprint ignores retrieved_at, so re-fetching the same data is not a change."""
        a = _prov(ridge=0.01).model_copy(update={"retrieved_at": datetime(2026, 1, 1, tzinfo=UTC)})
        b = _prov(ridge=0.01).model_copy(update={"retrieved_at": datetime(2026, 6, 1, tzinfo=UTC)})
        diff = diff_bundles(
            _bundle(_item("e.e", provenance=a)), _bundle(_item("e.e", provenance=b))
        )
        assert _by_id(diff)["e.e"].status == "unchanged"

    def test_rewording_a_label_is_not_a_result(self):
        diff = diff_bundles(_bundle(_item("e.e", label="Old")), _bundle(_item("e.e", label="New")))
        item = _by_id(diff)["e.e"]
        assert item.status == "unchanged" and item.label == "New"

    def test_added_and_removed_items_carry_only_their_own_side(self):
        diff = diff_bundles(_bundle(_item("gone.x")), _bundle(_item("new.x")))
        removed, added = _by_id(diff)["gone.x"], _by_id(diff)["new.x"]
        assert removed.baseline is not None and removed.candidate is None
        assert added.baseline is None and added.candidate is not None
        assert removed.delta is None and added.delta is None

    def test_a_snapshot_carries_what_the_ui_needs_to_show_the_number(self):
        interval = Confidence(lower=0.0, upper=1.0, kind="bootstrap")
        item = _by_id(diff_bundles(_bundle(_item("e.e", 2.0, unit="ndvi", confidence=interval)),
                                   _bundle(_item("e.e", 3.0, unit="ndvi", confidence=interval))))["e.e"]  # fmt: skip
        snap = item.candidate
        assert (snap.value, snap.unit, snap.confidence.kind) == (3.0, "ndvi", "bootstrap")
        assert len(snap.provenance_fingerprint) == 16 and snap.provenance_method

    def test_two_empty_bundles_diff_to_nothing(self):
        diff = diff_bundles(_bundle(), _bundle())
        assert diff.items == () and diff.summary.unchanged == 0


class TestVerdictAndWarningsDiff:
    def test_a_verdict_label_change_is_stated_not_ranked(self):
        base = _bundle(verdict=_verdict(VerdictLabel.INCONCLUSIVE))
        cand = _bundle(verdict=_verdict(VerdictLabel.DIVERGENT_FROM_CLAIM))
        verdict = diff_bundles(base, cand).verdict
        assert (verdict.baseline_label, verdict.candidate_label) == (
            "inconclusive",
            "divergent_from_claim",
        )
        assert verdict.label_changed
        assert set(verdict.model_dump()) == {
            "baseline_label", "candidate_label", "label_changed", "baseline_divergence_ratio",
            "candidate_divergence_ratio", "divergence_ratio_changed", "rationale_changed",
        }  # fmt: skip

    def test_an_unchanged_verdict(self):
        verdict = diff_bundles(_bundle(verdict=_verdict()), _bundle(verdict=_verdict())).verdict
        assert not (verdict.label_changed or verdict.divergence_ratio_changed)
        assert not verdict.rationale_changed

    def test_the_divergence_ratio_uses_the_tolerance(self):
        a = _bundle(verdict=_verdict(ratio=0.3))
        assert not diff_bundles(
            a, _bundle(verdict=_verdict(ratio=0.1 + 0.2))
        ).verdict.divergence_ratio_changed
        assert diff_bundles(
            a, _bundle(verdict=_verdict(ratio=0.9))
        ).verdict.divergence_ratio_changed
        assert diff_bundles(a, _bundle(verdict=_verdict(ratio=None))).verdict.divergence_ratio_changed  # fmt: skip

    def test_a_missing_verdict_is_handled(self):
        verdict = diff_bundles(_bundle(), _bundle(verdict=_verdict())).verdict
        assert verdict.baseline_label is None and verdict.label_changed

    def test_a_changed_rationale(self):
        diff = diff_bundles(
            _bundle(verdict=_verdict(rationale="a")), _bundle(verdict=_verdict(rationale="b"))
        )
        assert diff.verdict.rationale_changed and not diff.verdict.label_changed

    def test_warnings_added_and_removed(self):
        diff = diff_bundles(_bundle(warnings=("keep", "gone")), _bundle(warnings=("keep", "new")))
        assert diff.warnings.added == ("new",) and diff.warnings.removed == ("gone",)


# --- may these runs be compared? ------------------------------------------------


def _summary(**overrides) -> RunSummary:
    fields = {
        "run_id": "run_0000000000000001", "case_id": "kariba-redd", "spec_hash": "a" * 32,
        "status": "succeeded", "engine_status": "completed", "error_code": None,
        "verdict_label": "inconclusive", "data_mode": "simulated", "is_simulated": True,
        "engine_version": "0.10.0", "contract_version": "1.0.0",
        "created_at": datetime(2026, 11, 1, tzinfo=UTC),
    }  # fmt: skip
    fields.update(overrides)
    return RunSummary(**fields)


def _side(bundle: EvidenceBundle | None = None, **overrides) -> RunSide:
    from groundtruth.contracts.identifiers import EngineRef
    from groundtruth.contracts.result import AnalysisResult, EngineStatus

    summary = _summary(**overrides)
    result = None
    if bundle is not None:
        result = AnalysisResult(
            run_id=summary.run_id, case_id=summary.case_id, spec_hash=summary.spec_hash,
            status=EngineStatus.COMPLETED, bundle=bundle,
            engine=EngineRef(engine_version=summary.engine_version or "0", contract_version="1.0.0"),
        )  # fmt: skip
    return RunSide(summary=summary, result=result)


class TestResultState:
    @pytest.mark.parametrize(
        ("status", "engine_status", "expected"),
        [
            ("queued", None, "queued"),
            ("running", None, "running"),
            ("succeeded", "completed", "measured"),
            ("succeeded", "refused", "refused"),
            ("failed", "error", "failed"),
            ("failed", None, "failed"),
            ("cancelled", None, "cancelled"),
        ],
    )
    def test_the_state_follows_the_job_and_the_engine(self, status, engine_status, expected):
        assert _summary(status=status, engine_status=engine_status).result_state == expected

    def test_a_refusal_is_a_succeeded_job_whose_state_is_refused(self):
        run = _summary(status="succeeded", engine_status="refused")
        assert run.status == "succeeded" and run.result_state == "refused"


class TestCompareRuns:
    def test_comparable_runs_get_a_diff(self):
        b = _bundle(_item("a.a", 1.0), _item("b.b", 2.0))
        c = _bundle(_item("a.a", 1.0), _item("b.b", 3.0))
        outcome = compare_runs(_side(b, run_id="run_000000000000000a"),
                               _side(c, run_id="run_000000000000000b"))  # fmt: skip
        assert outcome.comparable and not outcome.not_comparable
        assert outcome.diff is not None
        assert [i.id for i in outcome.diff.items] == ["b.b"]  # unchanged left out ...
        assert outcome.diff.summary.unchanged == 1  # ... but counted

    def test_include_unchanged_lists_everything(self):
        b = _bundle(_item("a.a"), _item("b.b"))
        outcome = compare_runs(_side(b), _side(b), include_unchanged=True)
        assert [i.id for i in outcome.diff.items] == ["a.a", "b.b"]

    def test_a_different_engine_version_is_not_comparable_and_has_no_diff(self):
        b = _bundle(_item("a.a", 1.0))
        outcome = compare_runs(_side(b, engine_version="0.9.0"), _side(b, engine_version="0.10.0"))
        assert not outcome.comparable and outcome.diff is None
        (reason,) = outcome.not_comparable
        assert reason.code == "different_engine_version"
        assert "0.9.0" in reason.message and "0.10.0" in reason.message

    def test_simulated_against_observed_is_not_comparable(self):
        b = _bundle(_item("a.a"))
        outcome = compare_runs(_side(b), _side(b, data_mode="observed", is_simulated=False))
        assert [r.code for r in outcome.not_comparable] == ["different_data_mode"]
        assert outcome.diff is None

    def test_different_cases_are_not_comparable(self):
        b = _bundle(_item("a.a"))
        outcome = compare_runs(_side(b), _side(b, case_id="mikoko-pamoja"))
        assert [r.code for r in outcome.not_comparable] == ["different_case"]

    def test_a_different_contract_major_is_not_comparable(self):
        b = _bundle(_item("a.a"))
        outcome = compare_runs(_side(b), _side(b, contract_version="2.0.0"))
        assert [r.code for r in outcome.not_comparable] == ["different_contract_major"]

    def test_a_different_minor_is_still_comparable(self):
        b = _bundle(_item("a.a"))
        assert compare_runs(_side(b), _side(b, contract_version="1.3.0")).comparable

    def test_every_reason_is_reported_not_just_the_first(self):
        b = _bundle(_item("a.a"))
        outcome = compare_runs(
            _side(b),
            _side(b, case_id="x", data_mode="observed", is_simulated=False, engine_version="9.9.9"),
        )
        assert {r.code for r in outcome.not_comparable} == {
            "different_case", "different_data_mode", "different_engine_version",
        }  # fmt: skip

    def test_a_different_specification_is_comparable_but_flagged(self):
        b = _bundle(_item("a.a"))
        outcome = compare_runs(_side(b), _side(b, spec_hash="b" * 32))
        assert outcome.comparable and outcome.same_specification is False
        assert compare_runs(_side(b), _side(b)).same_specification is True

    @pytest.mark.parametrize(
        ("overrides", "needle"),
        [
            ({"status": "queued", "engine_status": None}, "still queued"),
            ({"status": "running", "engine_status": None}, "still running"),
            ({"status": "cancelled", "engine_status": None}, "cancelled"),
            ({"status": "failed", "engine_status": None, "failure_reason": "unusable-request"},
             "unusable-request"),
            ({"status": "failed", "engine_status": "error"}, "failed"),
        ],
    )  # fmt: skip
    def test_a_run_without_a_bundle_says_why(self, overrides, needle):
        b = _bundle(_item("a.a"))
        outcome = compare_runs(_side(b), _side(None, **overrides))
        (reason,) = outcome.not_comparable
        assert (reason.code, reason.side) == ("no_bundle", "candidate")
        assert needle in reason.message and outcome.diff is None

    def test_both_sides_without_a_bundle_are_both_named(self):
        outcome = compare_runs(_side(None, status="queued", engine_status=None),
                               _side(None, status="running", engine_status=None))  # fmt: skip
        assert [(r.code, r.side) for r in outcome.not_comparable] == [
            ("no_bundle", "baseline"),
            ("no_bundle", "candidate"),
        ]

    def test_an_unreadable_run_is_named(self):
        b = _bundle(_item("a.a"))
        unreadable = RunSide(summary=_summary(), result=None, unreadable="written under 1.3.0")
        outcome = compare_runs(unreadable, _side(b))
        (reason,) = outcome.not_comparable
        assert (reason.code, reason.side) == ("contract_unreadable", "baseline")
        assert "1.3.0" in reason.message

    def test_no_message_accuses_anyone(self):
        """R2: a comparison is about measurements, never about wrongdoing."""
        b = _bundle(_item("a.a"))
        outcome = compare_runs(
            _side(b),
            _side(
                None,
                case_id="x",
                data_mode="observed",
                is_simulated=False,
                status="failed",
                engine_status=None,
                engine_version="9",
            ),
        )
        text = " ".join(r.message for r in outcome.not_comparable).lower()
        assert not any(w in text for w in ("fraud", "misconduct", "lied", "deceiv", "illegal"))
