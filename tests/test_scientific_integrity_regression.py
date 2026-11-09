"""Regression guards for the independent scientific-integrity audit.

These tests scan the repository so that withdrawn or unsupported claims cannot
quietly return in code, docs, UI copy, demo data or reports. Historical
documents that must *discuss* the withdrawn numbers are allow-listed explicitly.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from groundtruth.engine import describe_engine
from groundtruth.engine.biomass import (
    DEFAULT_BIOMASS_PARAMETERS,
    BiomassParameters,
    NotCalibratedError,
    convert_indicator_to_carbon,
    get_biomass_parameters,
)

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".claude",
    ".git",
    ".venv",
    "node_modules",
    ".next",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
}
TEXT_SUFFIXES = {".py", ".md", ".ts", ".tsx", ".yaml", ".yml", ".txt", ".toml", ".css", ".html"}

# Files that legitimately discuss the withdrawn figures (audit trail / withdrawal notices).
HISTORICAL_ALLOWLIST = {
    "docs/competition/INDEPENDENT_POST_EXECUTION_AUDIT.md",
    "docs/competition/strategy.md",
    "tests/test_scientific_integrity_regression.py",
    "apps/web/tests/scientific-integrity-ui.test.ts",
}


def _walk() -> list[Path]:
    """All files under ROOT, pruning heavy/generated directories without descending."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        out.extend(Path(dirpath) / f for f in filenames)
    return out


_FILES = _walk()


def _text_files() -> list[Path]:
    return [p for p in _FILES if p.suffix in TEXT_SUFFIXES]


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _scan(pattern: str, *, allow: set[str] = frozenset(), flags: int = re.IGNORECASE) -> list[str]:  # type: ignore[assignment]
    rx = re.compile(pattern, flags)
    hits = []
    for path in _text_files():
        if not path.is_file():
            continue
        rel = _rel(path)
        if rel in allow:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if rx.search(line):
                hits.append(f"{rel}:{n}: {line.strip()[:120]}")
    return hits


class TestWithdrawnResults:
    def test_reverse_engineered_ndvi_constant_is_gone(self) -> None:
        assert _scan(r"0\.0609(0088)?\b", allow=HISTORICAL_ALLOWLIST) == []

    def test_57_04_and_70_86_findings_are_gone(self) -> None:
        assert _scan(r"57\.04\s*%?|70\.86\s*%?", allow=HISTORICAL_ALLOWLIST) == []

    def test_no_claim_of_independent_57_percent_recovery(self) -> None:
        hits = _scan(
            r"(independently|rigorously)\s+(reproduc|recover|discover)|recover(s|ing|ed)?\s+verra",
            allow=HISTORICAL_ALLOWLIST,
        )
        assert hits == []

    def test_no_hardcoded_back_calculated_tco2e(self) -> None:
        assert _scan(r"11[,_]?600[,_]?000", allow=HISTORICAL_ALLOWLIST) == []

    def test_strategy_doc_states_withdrawal(self) -> None:
        text = (ROOT / "docs/competition/strategy.md").read_text(encoding="utf-8")
        assert "withdrawn" in text
        assert "NOT CALIBRATED" in text
        assert "has not reproduced" in text or "No. GroundTruth has not reproduced" in text


class TestBiomassHasNoUnsupportedDefaults:
    def test_no_default_slope_anywhere(self) -> None:
        assert BiomassParameters().ndvi_to_agb_slope is None
        for name, params in DEFAULT_BIOMASS_PARAMETERS.items():
            assert params.ndvi_to_agb_slope is None, name
            assert params.root_to_shoot_ratio is None, name
            assert params.allometry_relative_error is None, name

    def test_no_numeric_slope_literal_in_source(self) -> None:
        src = ROOT / "packages/groundtruth/src"
        hits = []
        for path in src.rglob("*.py"):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"ndvi_to_agb_slope\s*[=:]\s*(float\s*=\s*)?\d", line):
                    hits.append(f"{path.name}:{n}: {line.strip()}")
        assert hits == []

    def test_uncalibrated_conversion_raises(self) -> None:
        for region in ("miombo", "tropical_dry_forest", "mangrove", "moist_tropical", "unknown"):
            with pytest.raises(NotCalibratedError):
                convert_indicator_to_carbon(0.05, 1000.0, get_biomass_parameters(region))

    def test_engine_does_not_claim_carbon_capability(self) -> None:
        assert describe_engine()["implemented"]["biomass_carbon_conversion"] is False

    def test_default_pipeline_never_emits_carbon(self) -> None:
        from groundtruth.engine import run_analysis
        from groundtruth.platform.cases.registry import get_case
        from groundtruth.platform.datasets.access import synthetic_access

        request = get_case("kariba-redd").to_request(data_mode="simulated")
        result = run_analysis(request, synthetic_access(request, true_effect=0.06))
        assert result.bundle is not None
        assert "carbon.estimated_tco2e" not in result.bundle
        assert "carbon.over_issuance_share" not in result.bundle
        assert result.bundle.verdict is not None
        assert result.bundle.verdict.label.value == "inconclusive"


class TestTerminology:
    def test_no_ipcc_tier_claim_without_negation(self) -> None:
        rx = re.compile(r"IPCC\s+Tier", re.IGNORECASE)
        neg = re.compile(r"\b(not|never|no)\b", re.IGNORECASE)
        bad = []
        for path in _text_files():
            rel = _rel(path)
            if rel in HISTORICAL_ALLOWLIST:
                continue
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            for n, line in enumerate(lines):
                if rx.search(line):
                    window = " ".join(lines[max(0, n - 1) : n + 3])
                    if not neg.search(window):
                        bad.append(f"{rel}:{n + 1}: {line.strip()[:100]}")
        assert bad == []

    def test_no_95_percent_sensitivity_envelope_label(self) -> None:
        assert (
            _scan(
                r"95\s*%\s*sensitivity",
                allow=HISTORICAL_ALLOWLIST,
            )
            == []
        )

    def test_carbon_interval_is_not_labelled_95(self) -> None:
        from groundtruth.engine.biomass.allometry import ASSUMED_ONE_SIGMA_KIND, ONE_SIGMA_LEVEL

        est = convert_indicator_to_carbon(
            0.01,
            100.0,
            BiomassParameters(
                ndvi_to_agb_slope=1.0,
                root_to_shoot_ratio=0.2,
                allometry_relative_error=0.3,
                calibration_source="TEST-ONLY",
                calibration_is_test_fixture=True,
            ),
        )
        env = est.envelope()
        assert env.level == pytest.approx(ONE_SIGMA_LEVEL)
        assert env.level < 0.7
        assert env.kind == ASSUMED_ONE_SIGMA_KIND

    def test_no_claim_of_real_data_for_kariba(self) -> None:
        hits = _scan(
            r"real,? calibrated|calibrated (landsat|satellite|observed)|real satellite data across|"
            r"executes against real",
            allow=HISTORICAL_ALLOWLIST,
        )
        assert hits == []

    def test_no_copernicus_usgs_provider_in_runtime_code(self) -> None:
        src = ROOT / "packages/groundtruth/src"
        hits = [
            str(p.relative_to(ROOT))
            for p in src.rglob("*.py")
            if "copernicus-usgs" in p.read_text(encoding="utf-8")
        ]
        assert hits == []


class TestSyntheticLabelling:
    FIXTURE = ROOT / "data/synthetic_fixtures/kariba_synthetic_benchmark.json"

    def test_old_observed_path_is_gone(self) -> None:
        assert not (ROOT / "data/observed/kariba_observed.json").exists()
        assert (
            _scan(
                r"kariba_observed",
                allow=HISTORICAL_ALLOWLIST
                | {"docs/competition/INDEPENDENT_POST_EXECUTION_AUDIT.md"},
            )
            == []
        )

    def test_fixture_is_labelled_synthetic(self) -> None:
        import json

        data = json.loads(self.FIXTURE.read_text(encoding="utf-8"))
        assert data["SYNTHETIC"] is True
        assert data["dataset_ref"]["provider"] == "synthetic"
        assert data["dataset_ref"]["dataset_id"].startswith("synthetic")
        assert "SYNTHETIC" in data["fixture_warning"]

    def test_fixture_not_shipped_under_an_observed_name(self) -> None:
        for path in _FILES:
            if "observed" not in path.name or path.suffix != ".json":
                continue
            pytest.fail(f"unexpected 'observed' data file: {_rel(path)}")


class TestCliHonesty:
    def test_doctor_does_not_overstate(self, capsys: pytest.CaptureFixture) -> None:
        from groundtruth.cli import main

        assert main(["doctor"]) == 0
        out = capsys.readouterr().out
        assert "ingestion implemented : no" in out
        assert "none (no satellite data for any case)" in out
        assert "NOT CALIBRATED" in out
        assert "yes (calibrated" not in out
