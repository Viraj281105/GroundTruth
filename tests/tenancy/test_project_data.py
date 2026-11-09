"""Task 7: evidence states on observation records and per-project, provenance-checked loaders."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from groundtruth.data_access.aoi_pipeline import AnnualObservationRecord
from groundtruth.data_access.climate import load_project_climate
from groundtruth.platform.config import get_settings
from groundtruth.platform.projects.data import (
    ClimateResult,
    ObservationsResult,
    load_climate,
    load_observations,
)
from groundtruth.platform.store.models import ProjectRow

REPO = Path(__file__).resolve().parents[2]
REAL_DATA = REPO / "data"
REAL_STAC = REAL_DATA / "processed" / "stac_cache"
REAL_CLIMATE = REAL_DATA / "processed" / "climate_cache" / "kariba_chirps_climate.json"

_SKIP_STAC = "real Sentinel-2 cache data/processed/stac_cache is git-ignored and absent here"
_SKIP_CLIMATE = "real climate cache data/processed/climate_cache is git-ignored and absent here"


def _project(case_id: str | None) -> ProjectRow:
    return ProjectRow(
        id=str(uuid.uuid4()),
        slug=f"p-{uuid.uuid4().hex[:8]}",
        organization_id=str(uuid.uuid4()),
        case_id=case_id,
        name="Test project",
        country="ZZ",
        ecosystem="forest",
        intervention="restoration",
        treatment_start_year=2015,
        data_mode="real",
        created_at=datetime.now(UTC),
    )


def _use_data_dir(monkeypatch: pytest.MonkeyPatch, data_dir: Path) -> None:
    monkeypatch.setattr(get_settings(), "data_dir", data_dir)


def _record_dict(**over: Any) -> dict[str, Any]:
    ids = ["S2A_MSIL2A_20210101T000000_N0500_R000_T36KWB_20210101T000000"]
    base: dict[str, Any] = {
        "year": 2021,
        "indicator": "ndvi",
        "value": 0.5,
        "n_valid_observations": 3,
        "clear_pixel_fraction": 0.9,
        "n_scenes": len(ids),
        "scene_ids": ids,
        "acquisition_dates": ["2021-01-01"],
        "sensor": "sentinel2",
        "scenes_sha256": "0" * 64,
    }
    base.update(over)
    return base


# --- record evidence states ------------------------------------------------------------------


def test_record_evidence_states() -> None:
    derived = AnnualObservationRecord.from_dict(_record_dict())
    assert derived.evidence_state == "DERIVED"

    empty = AnnualObservationRecord.from_dict(_record_dict(value=None, n_valid_observations=0))
    assert empty.evidence_state == "UNAVAILABLE"

    harmonized = AnnualObservationRecord.from_dict(
        _record_dict(processing_metadata={"harmonization": {"applied": True}})
    )
    assert harmonized.evidence_state == "MODEL_ESTIMATED"

    not_applied = AnnualObservationRecord.from_dict(
        _record_dict(processing_metadata={"harmonization": {"applied": False}})
    )
    assert not_applied.evidence_state == "DERIVED"

    # NaN wins over harmonization: nothing was observed, so nothing was estimated.
    both = AnnualObservationRecord.from_dict(
        _record_dict(value=None, processing_metadata={"harmonization": {"applied": True}})
    )
    assert both.evidence_state == "UNAVAILABLE"


def test_record_evidence_state_is_serialized_and_backward_compatible() -> None:
    legacy = _record_dict()
    assert "evidence_state" not in legacy  # existing caches predate the field
    rec = AnnualObservationRecord.from_dict(legacy)
    out = rec.to_dict()
    assert out["evidence_state"] == "DERIVED"
    assert AnnualObservationRecord.from_dict(out).evidence_state == "DERIVED"
    # A stored state is honoured on load.
    stored = AnnualObservationRecord.from_dict(_record_dict(evidence_state="MODEL_ESTIMATED"))
    assert stored.evidence_state == "MODEL_ESTIMATED"


def test_record_rejects_unknown_evidence_state() -> None:
    with pytest.raises(ValueError, match="evidence_state"):
        AnnualObservationRecord.from_dict(_record_dict(evidence_state="OBSERVED_ISH"))


# --- observations loader -----------------------------------------------------------------------


def test_load_observations_kariba_available(monkeypatch: pytest.MonkeyPatch) -> None:
    if not (REAL_STAC / "kariba-redd__ndvi.json").exists():
        pytest.skip(_SKIP_STAC)
    _use_data_dir(monkeypatch, REAL_DATA)
    result = load_observations(_project("kariba-redd"), "ndvi")
    assert isinstance(result, ObservationsResult)
    assert result.status == "available"
    assert result.reason is None
    assert result.bundle is not None
    assert result.bundle.records
    assert {r.evidence_state for r in result.bundle.records} <= {
        "DERIVED",
        "MODEL_ESTIMATED",
        "UNAVAILABLE",
    }


def test_load_observations_missing_case_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _use_data_dir(monkeypatch, tmp_path)
    result = load_observations(_project("no-such-case"), "ndvi")
    assert result.status == "unavailable"
    assert result.bundle is None
    assert result.reason and "no-such-case" in result.reason
    # The loader must not create the cache directory as a side effect.
    assert not (tmp_path / "processed").exists()


def test_load_observations_project_without_case_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _use_data_dir(monkeypatch, tmp_path)
    result = load_observations(_project(None), "ndvi")
    assert result.status == "unavailable"
    assert result.reason


def test_observations_unavailable_on_provenance_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    src = REAL_STAC / "kariba-redd__ndvi.json"
    if not src.exists():
        pytest.skip(_SKIP_STAC)
    raw = json.loads(src.read_text(encoding="utf-8"))
    victim = next(r for r in raw["records"] if r["value"] is not None)
    victim["scenes_sha256"] = "f" * 64  # no longer matches the listed scene_ids
    cache = tmp_path / "processed" / "stac_cache"
    cache.mkdir(parents=True)
    (cache / "kariba-redd__ndvi.json").write_text(json.dumps(raw), encoding="utf-8")
    _use_data_dir(monkeypatch, tmp_path)

    result = load_observations(_project("kariba-redd"), "ndvi")
    assert result.status == "unavailable"
    assert result.bundle is None
    assert result.reason and "provenance" in result.reason.lower()


def test_observations_unavailable_on_corrupt_json_and_unsafe_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache = tmp_path / "processed" / "stac_cache"
    cache.mkdir(parents=True)
    (cache / "broken__ndvi.json").write_text("{not json", encoding="utf-8")
    (cache / "partial__ndvi.json").write_text("{}", encoding="utf-8")
    _use_data_dir(monkeypatch, tmp_path)

    corrupt = load_observations(_project("broken"), "ndvi")
    assert corrupt.status == "unavailable" and corrupt.reason

    partial = load_observations(_project("partial"), "ndvi")
    assert partial.status == "unavailable" and partial.reason

    unsafe = load_observations(_project("../escape"), "ndvi")
    assert unsafe.status == "unavailable" and unsafe.reason


def test_observations_unavailable_for_synthetic_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    src = REAL_STAC / "kariba-redd__ndvi.json"
    if not src.exists():
        pytest.skip(_SKIP_STAC)
    raw = json.loads(src.read_text(encoding="utf-8"))
    raw["data_origin"] = "synthetic"
    cache = tmp_path / "processed" / "stac_cache"
    cache.mkdir(parents=True)
    (cache / "kariba-redd__ndvi.json").write_text(json.dumps(raw), encoding="utf-8")
    _use_data_dir(monkeypatch, tmp_path)

    result = load_observations(_project("kariba-redd"), "ndvi")
    assert result.status == "unavailable"
    assert result.reason and "synthetic" in result.reason.lower()


# --- climate loader ----------------------------------------------------------------------------


def test_load_climate_non_kariba_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_data_dir(monkeypatch, REAL_DATA)  # even with the real Kariba cache present
    result = load_climate(_project("mikoko-pamoja"))
    assert isinstance(result, ClimateResult)
    assert result.status == "unavailable"
    assert result.bundle is None
    assert result.reason == "No climate series has been ingested for this project"

    no_case = load_climate(_project(None))
    assert no_case.status == "unavailable"
    assert no_case.reason == "No climate series has been ingested for this project"


def test_load_climate_kariba_available(monkeypatch: pytest.MonkeyPatch) -> None:
    if not REAL_CLIMATE.exists():
        pytest.skip(_SKIP_CLIMATE)
    _use_data_dir(monkeypatch, REAL_DATA)
    result = load_climate(_project("kariba-redd"))
    assert result.status == "available"
    assert result.reason is None
    assert result.bundle is not None
    assert result.bundle.case_id == "kariba-redd"


def test_load_climate_corrupt_cache_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache = tmp_path / "processed" / "climate_cache"
    cache.mkdir(parents=True)
    (cache / "kariba_chirps_climate.json").write_text("{oops", encoding="utf-8")
    _use_data_dir(monkeypatch, tmp_path)
    result = load_climate(_project("kariba-redd"))
    assert result.status == "unavailable"
    assert result.reason and "unreadable" in result.reason.lower()


def test_load_project_climate_absent_or_other_case_returns_none(tmp_path: Path) -> None:
    assert load_project_climate("kariba-redd", tmp_path) is None
    if not REAL_CLIMATE.exists():
        pytest.skip(_SKIP_CLIMATE)
    shutil.copy(REAL_CLIMATE, tmp_path / REAL_CLIMATE.name)
    assert load_project_climate("some-other-case", tmp_path) is None
    bundle = load_project_climate("kariba-redd", tmp_path)
    assert bundle is not None and bundle.case_id == "kariba-redd"
