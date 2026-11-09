"""Covariates and unit construction against the real Earth Engine (#23).

**Opt-in.** Skipped unless ``--run-network`` is passed, so it never runs in CI. With the
flag, anything missing fails with the reason rather than skipping, because a run you
asked for should not quietly do nothing.

Run them in this order, since each one's output feeds the next:

    pytest -m network --run-network tests/test_covariates_network.py -k listing -v -s
    pytest -m network --run-network tests/test_covariates_network.py -k timing -v -s
    pytest -m network --run-network tests/test_covariates_network.py -k kariba_pool -v -s

1. **Listing.** Literal names, never a count. Copy the ``ECO_NAME`` strings and a WDPA
   snapshot from it into ``cases/run_parameters/kariba-redd.yaml`` (V5, B6). Also confirms
   the WorldPop 2000 image exists (V2).
2. **Timing.** Seconds per step on one district, never a count (B6). Needs the settings.
3. **Kariba pool.** The acceptance test: real covariates for an 80+ candidate pool. Needs
   every setting decided, and refuses until then. Run it only after the settings are
   committed, because ADR-011 forbids fixing a parameter after seeing a candidate count.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from typing import Any

import pytest

from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.config import get_settings, reset_settings_cache
from groundtruth.platform.datasets.covariates import COVARIATE_KEYS
from groundtruth.platform.datasets.ee_mask import MASK_MEMBER
from groundtruth.platform.units import load_run_settings, run_settings_path
from groundtruth.platform.units.spec import GAUL_ADM0_NAMES

pytestmark = pytest.mark.network

REPO = pathlib.Path(__file__).resolve().parents[1]


def _script() -> Any:
    path = REPO / "experiments/kariba_benchmark/generate_unit_set.py"
    spec = importlib.util.spec_from_file_location("generate_unit_set_network", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _settings() -> Any:
    reset_settings_cache()
    return get_settings()


def test_listing_of_literal_names_with_no_counts():
    listing = _script().study_area_listing(_settings())

    print("\nCopy ECO_NAME strings from here into cases/run_parameters/kariba-redd.yaml (V5):")
    for name in listing["eco_names"]:
        print(f"  {name!r}")
    print("Dated WDPA snapshots (B6):")
    for release in listing["wdpa_releases"][-6:]:
        print(f"  {release}")
    print("GAUL countries in the study bounds:")
    for country in listing["gaul_countries"]:
        print(f"  {country!r}")
    print(f"WorldPop 2000 countries (V2): {listing['worldpop_2000_countries']}")

    assert listing["eco_names"], "RESOLVE returned no ecoregion names over the study bounds"
    assert listing["wdpa_releases"], "no dated WDPA snapshots were listed"
    # The literal GAUL names the ladder relies on, because GAUL has no ISO3 field.
    assert set(GAUL_ADM0_NAMES.values()) <= set(listing["gaul_countries"])
    # V2: the asset is deprecated, so its 2000 image has to be confirmed, not assumed.
    assert set(GAUL_ADM0_NAMES) <= set(listing["worldpop_2000_countries"])


def test_timing_trial_reports_seconds_only():
    script = _script()
    case = get_case("kariba-redd")
    run_settings = load_run_settings(run_settings_path("kariba-redd"))
    seconds = script.timing_trial(case, run_settings, _settings())

    print("\nSeconds per step on one district (no counts, on purpose):")
    for step, value in seconds.items():
        print(f"  {step:<36} {value:>9.1f}")

    assert {"forest", "mask", "fragments"} <= set(seconds)
    assert all(isinstance(value, float) for value in seconds.values())


def test_kariba_pool_has_real_covariates_for_80_or_more_candidates():
    script = _script()
    case = get_case("kariba-redd")
    run_settings = load_run_settings(run_settings_path("kariba-redd"))
    settings = _settings()

    unit_set = script.generate(case, run_settings, settings)

    print(f"\nRung used: {unit_set.rung_used}. Candidates: {len(unit_set.candidates)}.")
    for record in unit_set.outcome.records:
        print(
            f"  rung {record.rung}: {record.eligible_candidates} candidates, "
            f"{record.admitted_donors} admitted; excluded {record.exclusions_by_category}"
        )

    # ADR-011's own stopping rule: it refuses rather than returning fewer than pool_size.
    assert len(unit_set.candidates) >= case.donor_pool_size >= 80

    services = script.build_services(case, run_settings, settings)
    keys = tuple(COVARIATE_KEYS)
    for unit in unit_set.candidate_unit_refs():
        assert MASK_MEMBER in unit.geometry
        assert unit.area_ha and unit.area_ha > 0
        values = services.covariates.covariates(unit, keys)
        assert set(values) == set(keys)
        assert all(value == value for value in values.values())  # not NaN

    # Pinned: every covariate carries a reference epoch separately from its release.
    for ref in unit_set.manifest.covariate_refs:
        assert ";ref=" in ref["version"]
    assert unit_set.manifest.belt_geometry_hash

    # WDPA needs no separate assertion here: generation measures the protected pixels inside
    # every unit and raises if any is left, so a unit set that exists has none.
