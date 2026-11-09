"""Landsat ETM+/TM -> OLI surface-reflectance band harmonization (opt-in).

Source: Roy, D.P., Kovalskyy, V., Zhang, H.K., Vermote, E.F., Yan, L., Kumar, S.S.,
Egorov, A. (2016). "Characterization of Landsat-7 to Landsat-8 reflective wavelength and
normalized difference vegetation index continuity." Remote Sensing of Environment 185:57-70.
doi:10.1016/j.rse.2015.12.024. Table 2, OLS, ETM+ -> OLI surface reflectance.

Transcription provenance: the six band pairs below match the coefficient arrays in Google
Earth Engine's community tutorial "Landsat ETM+ to OLI Harmonization", which cites Roy et
al. (2016) Table 2 OLS. The paper PDF could not be retrieved during the 2026-11-08
remediation, so they should be re-checked against the published table.

Scope decisions (independent audit, finding P1-1):

* **Bands only.** Roy et al. publish band functions and NDVI functions. The NDVI row
  label (TOA vs surface) could not be verified, and the paper gives no EVI/NDMI/NBR
  functions. Indices are therefore never transformed directly. Instead, harmonize the
  input bands and recompute the index.
* **Opt-in.** The same Earth Engine page warns that this harmonization is "outdated and
  not recommended or necessary" for Landsat Collection 2 surface reflectance. Callers must
  request it explicitly, keep the unharmonized series, and treat harmonized values as
  MODEL_ESTIMATED.
* **TM.** The tutorial applies the ETM+ coefficients to Landsat 5 TM. Roy et al.
  characterized ETM+ only, so TM use is an assumption and is recorded as such.
* **No local validation.** No Kariba overlap validation exists. ``validate_*_overlap``
  computes the metrics once real near-coincident ETM+/OLI pairs are supplied.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np

ROY_2016_CITATION = (
    "Roy et al. (2016) RSE 185:57-70, Table 2 (OLS, ETM+ -> OLI surface reflectance)"
)
TM_ASSUMPTION_NOTE = (
    "Landsat 5 TM transformed with the ETM+ coefficients; Roy et al. (2016) characterized "
    "ETM+ only, so this is an assumption."
)

_ETM_FRAME_SENSORS = frozenset({"landsat5", "landsat7"})
_OLI_FRAME_SENSORS = frozenset({"landsat8", "landsat9"})


class HarmonizationMethod(StrEnum):
    """Supported cross-sensor harmonization models."""

    ROY_2016_OLS = "roy_2016_ols"
    NONE = "none"


class SensorReferenceFrame(StrEnum):
    """Reference sensor spectral standard."""

    OLI = "landsat8_oli"
    ETM_PLUS = "landsat7_etm"


class UnsupportedHarmonizationError(ValueError):
    """Requested a transform that has no published, verified coefficients."""


@dataclass(frozen=True)
class LinearCoefficients:
    """Univariate linear transformation parameters: target = slope * source + intercept."""

    slope: float
    intercept: float

    def transform(self, val: float | np.ndarray) -> float | np.ndarray:
        """Apply the linear transformation."""
        return self.slope * val + self.intercept

    def invert(self) -> LinearCoefficients:
        """Invert the transformation: source = (target - intercept) / slope."""
        if abs(self.slope) < 1e-12:
            raise ValueError("Cannot invert degenerate linear coefficients with slope ~ 0")
        return LinearCoefficients(slope=1.0 / self.slope, intercept=-self.intercept / self.slope)


# Roy et al. (2016) Table 2, OLS, ETM+ -> OLI surface reflectance (rho in [0, 1]).
ROY_2016_OLS_ETM_TO_OLI_BANDS: dict[str, LinearCoefficients] = {
    "blue": LinearCoefficients(slope=0.8474, intercept=0.0003),
    "green": LinearCoefficients(slope=0.8483, intercept=0.0088),
    "red": LinearCoefficients(slope=0.9047, intercept=0.0061),
    "nir": LinearCoefficients(slope=0.8462, intercept=0.0412),
    "swir1": LinearCoefficients(slope=0.8937, intercept=0.0254),
    "swir2": LinearCoefficients(slope=0.9071, intercept=0.0172),
}


def _frame(sensor: str) -> str:
    key = sensor.lower().replace("-", "")
    if key in _ETM_FRAME_SENSORS:
        return "etm"
    if key in _OLI_FRAME_SENSORS:
        return "oli"
    raise UnsupportedHarmonizationError(
        f"No Landsat ETM+/OLI harmonization defined for sensor {sensor!r}"
    )


def get_harmonization_coefficients(
    band: str,
    *,
    source_sensor: str = "landsat7",
    target_sensor: str = "landsat8",
    method: HarmonizationMethod = HarmonizationMethod.ROY_2016_OLS,
) -> LinearCoefficients:
    """Return the reflectance transform for one band between Landsat sensor frames.

    Raises:
        UnsupportedHarmonizationError: for a spectral index, an unknown band, or a
            non-Landsat sensor. There is no silent identity fallback.
    """
    if method == HarmonizationMethod.NONE:
        return LinearCoefficients(slope=1.0, intercept=0.0)
    key = band.lower()
    if key not in ROY_2016_OLS_ETM_TO_OLI_BANDS:
        raise UnsupportedHarmonizationError(
            f"{band!r} has no verified Roy et al. (2016) band coefficients. Spectral indices "
            "are not transformed directly: harmonize the input bands and recompute the index."
        )
    src, tgt = _frame(source_sensor), _frame(target_sensor)
    if src == tgt:
        return LinearCoefficients(slope=1.0, intercept=0.0)
    forward = ROY_2016_OLS_ETM_TO_OLI_BANDS[key]
    return forward if (src, tgt) == ("etm", "oli") else forward.invert()


def harmonize_reflectance(
    reflectance: float | np.ndarray,
    band: str,
    *,
    source_sensor: str,
    target_sensor: str = "landsat8",
    method: HarmonizationMethod = HarmonizationMethod.ROY_2016_OLS,
) -> float | np.ndarray:
    """Transform surface reflectance for one band into the target sensor frame.

    NaN stays NaN. Values are not clipped: an out-of-range result is information, not
    something to hide.
    """
    coeffs = get_harmonization_coefficients(
        band, source_sensor=source_sensor, target_sensor=target_sensor, method=method
    )
    if isinstance(reflectance, np.ndarray):
        return coeffs.transform(np.asarray(reflectance, dtype=float))
    if math.isnan(reflectance):
        return float("nan")
    return float(coeffs.transform(reflectance))


@dataclass(frozen=True)
class SensorHarmonizationAudit:
    """Overlap validation of a harmonization on paired ETM+/OLI observations."""

    method: HarmonizationMethod
    quantity: str
    citation: str
    n_overlap_samples: int
    raw_mean_bias: float
    raw_median_bias: float
    raw_rmse: float
    harmonized_mean_bias: float
    harmonized_median_bias: float
    harmonized_rmse: float
    residual_std_error: float
    ci_95_lower: float
    ci_95_upper: float
    is_validated: bool
    status_summary: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize audit to a JSON-compatible dictionary."""
        return {
            "method": self.method.value,
            "quantity": self.quantity,
            "citation": self.citation,
            "n_overlap_samples": self.n_overlap_samples,
            "raw_mean_bias": self.raw_mean_bias,
            "raw_median_bias": self.raw_median_bias,
            "raw_rmse": self.raw_rmse,
            "harmonized_mean_bias": self.harmonized_mean_bias,
            "harmonized_median_bias": self.harmonized_median_bias,
            "harmonized_rmse": self.harmonized_rmse,
            "residual_std_error": self.residual_std_error,
            "ci_95_bounds": [self.ci_95_lower, self.ci_95_upper],
            "is_validated": self.is_validated,
            "status_summary": self.status_summary,
        }


MIN_OVERLAP_SAMPLES = 30
MAX_RESIDUAL_BIAS = 0.015


def _audit(
    quantity: str,
    oli: np.ndarray,
    etm_raw: np.ndarray,
    etm_harm: np.ndarray,
    method: HarmonizationMethod,
) -> SensorHarmonizationAudit:
    valid = np.isfinite(oli) & np.isfinite(etm_raw) & np.isfinite(etm_harm)
    n = int(valid.sum())
    nan = float("nan")
    if n < MIN_OVERLAP_SAMPLES:
        return SensorHarmonizationAudit(
            method,
            quantity,
            ROY_2016_CITATION,
            n,
            nan,
            nan,
            nan,
            nan,
            nan,
            nan,
            nan,
            nan,
            nan,
            False,
            f"INSUFFICIENT_OVERLAP_SAMPLES (N={n} < {MIN_OVERLAP_SAMPLES})",
        )
    raw = oli[valid] - etm_raw[valid]
    harm = oli[valid] - etm_harm[valid]
    sd = float(np.std(harm, ddof=1))
    se = sd / math.sqrt(n)
    h_mean = float(np.mean(harm))
    raw_rmse = float(np.sqrt(np.mean(raw**2)))
    h_rmse = float(np.sqrt(np.mean(harm**2)))
    ok = bool(abs(h_mean) <= MAX_RESIDUAL_BIAS and h_rmse <= raw_rmse)
    return SensorHarmonizationAudit(
        method=method,
        quantity=quantity,
        citation=ROY_2016_CITATION,
        n_overlap_samples=n,
        raw_mean_bias=float(np.mean(raw)),
        raw_median_bias=float(np.median(raw)),
        raw_rmse=raw_rmse,
        harmonized_mean_bias=h_mean,
        harmonized_median_bias=float(np.median(harm)),
        harmonized_rmse=h_rmse,
        residual_std_error=sd,
        ci_95_lower=h_mean - 1.96 * se,
        ci_95_upper=h_mean + 1.96 * se,
        is_validated=ok,
        status_summary=(
            "VALIDATED on the supplied overlap sample"
            if ok
            else "NOT_VALIDATED: residual bias or RMSE does not improve on raw"
        ),
    )


def validate_band_overlap(
    etm_reflectance: Sequence[float] | np.ndarray,
    oli_reflectance: Sequence[float] | np.ndarray,
    *,
    band: str,
    source_sensor: str = "landsat7",
    method: HarmonizationMethod = HarmonizationMethod.ROY_2016_OLS,
) -> SensorHarmonizationAudit:
    """Compare raw vs harmonized ETM+ reflectance against paired OLI reflectance for one band."""
    etm = np.asarray(etm_reflectance, dtype=float)
    oli = np.asarray(oli_reflectance, dtype=float)
    if etm.shape != oli.shape:
        raise ValueError(f"Shape mismatch: ETM {etm.shape} != OLI {oli.shape}")
    harm = np.asarray(
        harmonize_reflectance(etm, band, source_sensor=source_sensor, method=method), float
    )
    return _audit(band, oli, etm, harm, method)


def _ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (nir - red) / (nir + red)
    out[~np.isfinite(out)] = np.nan
    return out


def validate_ndvi_overlap(
    etm_red: Sequence[float] | np.ndarray,
    etm_nir: Sequence[float] | np.ndarray,
    oli_red: Sequence[float] | np.ndarray,
    oli_nir: Sequence[float] | np.ndarray,
    *,
    source_sensor: str = "landsat7",
    method: HarmonizationMethod = HarmonizationMethod.ROY_2016_OLS,
) -> SensorHarmonizationAudit:
    """Validate NDVI continuity: harmonize ETM+ red/NIR, recompute NDVI, compare to OLI NDVI."""
    e_red, e_nir = np.asarray(etm_red, float), np.asarray(etm_nir, float)
    o_red, o_nir = np.asarray(oli_red, float), np.asarray(oli_nir, float)
    if not (e_red.shape == e_nir.shape == o_red.shape == o_nir.shape):
        raise ValueError("All four reflectance arrays must share one shape")
    h_red = np.asarray(
        harmonize_reflectance(e_red, "red", source_sensor=source_sensor, method=method), float
    )
    h_nir = np.asarray(
        harmonize_reflectance(e_nir, "nir", source_sensor=source_sensor, method=method), float
    )
    return _audit("ndvi", _ndvi(o_nir, o_red), _ndvi(e_nir, e_red), _ndvi(h_nir, h_red), method)


__all__ = [
    "MIN_OVERLAP_SAMPLES",
    "ROY_2016_CITATION",
    "ROY_2016_OLS_ETM_TO_OLI_BANDS",
    "TM_ASSUMPTION_NOTE",
    "HarmonizationMethod",
    "LinearCoefficients",
    "SensorHarmonizationAudit",
    "SensorReferenceFrame",
    "UnsupportedHarmonizationError",
    "get_harmonization_coefficients",
    "harmonize_reflectance",
    "validate_band_overlap",
    "validate_ndvi_overlap",
]
