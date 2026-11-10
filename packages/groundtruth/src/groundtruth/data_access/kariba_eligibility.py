"""Data-access loader for the Kariba donor eligibility matrix.

Reads committed GeoJSON features and real CHIRPS climate bundles from disk before
delegating all pure eligibility classification and matrix conditioning checks to
:func:`groundtruth.engine.matching.eligibility.build_kariba_donor_eligibility_matrix`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from groundtruth.contracts.errors import DataUnavailableError
from groundtruth.data_access.climate import DEFAULT_CLIMATE_CACHE_PATH, load_kariba_climate_bundle
from groundtruth.engine.matching.eligibility import (
    DonorEligibilityAssessment,
    build_kariba_donor_eligibility_matrix,
)

REPO_ROOT = Path(__file__).resolve().parents[5]


def load_kariba_donor_eligibility_matrix(
    *,
    climate_bundle: Any | None = None,
    donor_geojson_path: Path | str | None = None,
    pre_treatment_panel: Mapping[str, Sequence[float]] | None = None,
    treated_pre_series: Sequence[float] | None = None,
) -> DonorEligibilityAssessment:
    """Load donor GeoJSON and climate bundle, then build the pure eligibility matrix."""
    if climate_bundle is None:
        climate_bundle = load_kariba_climate_bundle(DEFAULT_CLIMATE_CACHE_PATH)

    geo_path = (
        Path(donor_geojson_path)
        if donor_geojson_path
        else REPO_ROOT / "cases" / "boundaries" / "kariba-donors.geojson"
    )
    if not geo_path.is_file():
        raise DataUnavailableError(f"Donor boundary GeoJSON not found at {geo_path}")
    features = json.loads(geo_path.read_text(encoding="utf-8")).get("features", [])
    return build_kariba_donor_eligibility_matrix(
        donor_features=features,
        climate_bundle=climate_bundle,
        pre_treatment_panel=pre_treatment_panel,
        treated_pre_series=treated_pre_series,
    )
