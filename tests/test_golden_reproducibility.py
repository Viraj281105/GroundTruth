"""Golden-snapshot reproducibility for the Kariba synthetic case.

Float policy: every float is rounded to 6 decimal places before comparison;
run ids and timestamps are excluded. To regenerate intentionally, run with
``GROUNDTRUTH_UPDATE_GOLDEN=1`` and review the diff of tests/golden/.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from groundtruth.engine import run_analysis
from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.datasets.access import synthetic_access

GOLDEN = Path(__file__).parent / "golden" / "kariba_synthetic.json"
VOLATILE = {
    "run_id",
    "started_at",
    "finished_at",
    "created_at",
    "timestamp",
    "retrieved_at",
    "metrics",
}
DECIMALS = 6


def _normalise(obj: Any) -> Any:
    if isinstance(obj, float):
        return round(obj, DECIMALS)
    if isinstance(obj, dict):
        return {k: _normalise(v) for k, v in obj.items() if k not in VOLATILE}
    if isinstance(obj, list):
        return [_normalise(v) for v in obj]
    return obj


def _snapshot() -> Any:
    case = get_case("kariba-redd")
    request = case.to_request(seed=20260101, min_donors=5)
    result = run_analysis(request, synthetic_access(request, true_effect=0.0))
    return _normalise(json.loads(result.model_dump_json()))


def test_two_runs_are_identical() -> None:
    assert _snapshot() == _snapshot()


def test_matches_golden_snapshot() -> None:
    snap = _snapshot()
    if os.environ.get("GROUNDTRUTH_UPDATE_GOLDEN") == "1":
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(snap, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert snap == expected, (
        "Kariba output drifted from tests/golden/kariba_synthetic.json. If the change is "
        "intentional, regenerate with GROUNDTRUTH_UPDATE_GOLDEN=1 and review the diff."
    )
