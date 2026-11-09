# TASK 3C — SENTINEL-2 NDMI DATA INTEGRITY REMEDIATION REPORT

**Status**: PASS  
**Date**: November 8, 2026  
**Target**: GroundTruth Earth Observation & Climate Co-Movement Pipeline (`analyze_sentinel2_climate_comovement`)  
**Repository**: `d:\Hackathons\PCCOEIGC\GroundTruth`

---

## 1. Executive Summary

In accordance with the findings of [`TASK_3A_INDEPENDENT_AUDIT.md`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/TASK_3A_INDEPENDENT_AUDIT.md), the descriptive Sentinel-2 Normalized Difference Moisture Index (NDMI) integrity defect has been remediated. 

Hardcoded positive default arguments in [`analyze_sentinel2_climate_comovement`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/packages/groundtruth/src/groundtruth/engine/causal/climate_confounding.py#L969-L1070) have been eliminated. The descriptive analysis now strictly handles actual observations, preserves missing observations as `None` without fabrication, and aligns with the genuine Sentinel-2 STAC cache ([`kariba-redd__ndmi.json`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/data/processed/stac_cache/kariba-redd__ndmi.json)).

All core causal inference machinery (Synthetic Control Method, Difference-in-Differences, donor eligibility matching, identification gates) was completely untouched and verified across **182 / 182 passed tests**.

---

## 2. Root Cause Analysis

### 2.1 The Defect
In [`climate_confounding.py`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/packages/groundtruth/src/groundtruth/engine/causal/climate_confounding.py), `analyze_sentinel2_climate_comovement` previously specified default arguments:
```python
# PREVIOUS (DEFECTIVE):
def analyze_sentinel2_climate_comovement(
    climate_summary: UnitClimateSummary,
    *,
    years: Sequence[int] = (2021, 2022, 2023),
    ndvi_values: Sequence[float] = (0.4255, 0.4206, 0.3450),
    evi_values: Sequence[float] = (0.2896, 0.2797, 0.2233),
    ndmi_values: Sequence[float] = (0.0725, 0.0680, 0.0085),  # INVERTED SIGN / FABRICATED DEFAULTS
    nbr_values: Sequence[float] = (0.3037, 0.2943, 0.1930),
)
```

### 2.2 Mechanism of Inversion
1. **Mathematical Definition**: Per Gao (1996) and [`indices.py`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/packages/groundtruth/src/groundtruth/engine/observation/indices.py#L49-L56):
   $$\text{NDMI} = \frac{\rho_{\text{NIR}} - \rho_{\text{SWIR1}}}{\rho_{\text{NIR}} + \rho_{\text{SWIR1}}} = \frac{B08 - B11}{B08 + B11}$$
2. **Physical Environment**: In the Kariba project area (Miombo woodlands / dry savanna) during the June dry season, foliar water content is low and soil/litter SWIR1 reflectance ($B11$) exceeds NIR reflectance ($B08$). Hence, true NDMI values are **negative**.
3. **The Discrepancy**: The previous code accidentally used inverted band ordering $(B11 - B08)/(B11 + B08)$ or positive placeholder defaults `(0.0725, 0.0680, 0.0085)` instead of receiving the actual clear-sky STAC cache values `(-0.069341, -0.089639, -0.109568)`.

---

## 3. Files Changed

1. **[`packages/groundtruth/src/groundtruth/engine/causal/climate_confounding.py`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/packages/groundtruth/src/groundtruth/engine/causal/climate_confounding.py)**:
   - Modified `Sentinel2ClimateCoMovement` dataclass to allow optional `float | None` tuples for all spectral indices, and added `ndmi_2023_vs_2021_2022_delta: float | None`.
   - Updated `analyze_sentinel2_climate_comovement` signature: defaults are now `None`. If observations are not provided, fields remain `None` and notes explicitly state that observations are unavailable or incomplete.
   - Refactored delta calculations and narrative formatting to safely format negative numbers (`{val:+.4f}`) without sign ambiguity.
2. **[`tests/engine/test_climate_integration.py`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/tests/engine/test_climate_integration.py)**:
   - Updated `test_sentinel2_comovement_explicitly_refuses_causal_identification` to supply the exact STAC cache values (`(-0.069341, -0.089639, -0.109568)`).
   - Added `TestSentinel2NDMIIntegrity` test suite with 4 new regression tests:
     - `test_stac_cache_ndmi_values_and_provenance`: Verifies the 3 NDMI cache values against [`kariba-redd__ndmi.json`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/data/processed/stac_cache/kariba-redd__ndmi.json).
     - `test_ndmi_formula_and_sign_convention`: Verifies Gao (1996) formula and negative dry-season sign convention.
     - `test_missing_observations_remain_none_without_default_fabrication`: Verifies that missing observations remain `None` without invented defaults.
     - `test_scm_and_did_unaffected_by_ndmi_correction`: Verifies SCM and DiD estimators produce identical outputs.

---

## 4. Before & After Comparison

| Quantity / Property | Before Remediation | After Remediation | Data Provenance Reference |
| :--- | :---: | :---: | :--- |
| **2021 NDMI Value** | `+0.0725` (hardcoded default) | **`-0.069341`** | `data/processed/stac_cache/kariba-redd__ndmi.json` |
| **2022 NDMI Value** | `+0.0680` (hardcoded default) | **`-0.089639`** | `data/processed/stac_cache/kariba-redd__ndmi.json` |
| **2023 NDMI Value** | `+0.0085` (hardcoded default) | **`-0.109568`** | `data/processed/stac_cache/kariba-redd__ndmi.json` |
| **NDMI Trajectory** | Positive values, decreasing | **Negative values, monotonic drying** | June dry season clear-sky Sentinel-2 L2A zonal mean |
| **NDMI 2023 vs 2021–22 $\Delta$** | Not explicitly tracked | **`-0.0301`** (further drying) | Zonal clear-pixel difference |
| **Missing Observation Behavior** | Silently replaced by hardcoded numbers | **Preserved as `None`** with explicit note | Zero data fabrication policy |
| **2021–2023 NDVI Values** | `(0.4255, 0.4206, 0.3450)` | `(0.425465, 0.420619, 0.344995)` | `data/processed/stac_cache/kariba-redd__ndvi.json` |
| **2021–2023 EVI Values** | `(0.2896, 0.2797, 0.2233)` | `(0.243256, 0.231527, 0.198776)` | `data/processed/stac_cache/kariba-redd__evi.json` |
| **2021–2023 NBR Values** | `(0.3037, 0.2943, 0.1930)` | `(0.137656, 0.117227, 0.089675)` | `data/processed/stac_cache/kariba-redd__nbr.json` |

---

## 5. Confirmation that Causal Estimators Were Untouched

- **Estimator Code Untouched**: [`fit_synthetic_control`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/packages/groundtruth/src/groundtruth/engine/causal/synthetic_control.py#L416) and [`estimate_did`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/packages/groundtruth/src/groundtruth/engine/causal/did.py#L284) received 0 lines of edits.
- **Specification Estimands Unchanged**: Causal specifications 1–10 evaluate the 2001–2022 annual NDVI panel. SCM point estimate ($+0.04158$), DiD estimate ($+0.04156$), pre-RMSPE ($0.001382$), relative pre-fit ($0.12427$), and effective donor count ($36.989$) remain strictly identical.
- **Gates Preserved**: `VerdictLabel.INCONCLUSIVE` is preserved across all 10 specifications.

---

## 6. Verification Test Results

```bash
cd D:\Hackathons\PCCOEIGC\GroundTruth; .\.venv\Scripts\pytest.exe \
  tests/engine/test_climate_integration.py \
  tests/data_access/test_live_stac_kariba.py \
  tests/engine/test_causal_diagnostics.py \
  tests/test_fit_gate.py \
  tests/test_scientific_integrity_regression.py \
  tests/test_causal.py \
  tests/test_matching.py \
  tests/test_units.py \
  tests/test_contract_boundary.py -v
```

### Exact Results
- **Exit Code**: `0`
- **Total Tests Collected**: `182`
- **Passed**: `182` (100%)
- **Failed**: `0`
- **Warnings**: `1` (third-party `planetary_computer.sas` Pydantic v1 config warning)
- **Execution Time**: 33.66s
- **Static Analysis**: `mypy` and `ruff check --select F` passed with **0 errors**.

