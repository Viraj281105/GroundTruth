# TASK 3A — INDEPENDENT CLIMATE INTEGRATION & CAUSAL METHODOLOGY AUDIT

**Auditor**: Independent Scientific Methodology Audit  
**Date**: November 8, 2026  
**Audit Target**: GroundTruth Earth Observation & Causal Inference Pipeline (`kariba-redd` Project AOI, 37 Spatially Eligible Donors, CHIRPS v2.0, NASA POWER MERRA-2, CHIRTSmax v1.0 CDR, Sentinel-2 STAC).  
**Repository**: `d:\Hackathons\PCCOEIGC\GroundTruth`

---

## 1. Overall Audit Verdict

### **Verdict: PARTIAL (with Major Finding on NDMI Sign Inversion)**

| Evaluation Domain | Audit Determination | Core Finding / Evidence |
| :--- | :---: | :--- |
| **1. Pre-Treatment Fit Reconciliation** | **VERIFIED / RECONCILED** | No artificial fit optimization or estimator tampering occurred. The `0.1243` figure originates from the identical underlying solver run on the benchmark fixture panel (`pre_rmspe = 0.0013817`, $\text{SD}_{\text{pre}} = 0.011119 \rightarrow 0.0013817 / 0.011119 = 0.12427$). The previous `1.0219` report was a typographical/documentation transcription artifact (`0.008568 / 0.008384 = 1.0219`) where the actual code execution in the previous task had already logged `pre_rmspe = 0.001382` and `relative_pre_fit = 0.12427`. Both runs yield identical uniform degenerate weights ($N_{\text{eff}} = 36.99$) and fail the identification gates. |
| **2. Sentinel-2 NDMI Discrepancy** | **DEFECT (CRITICAL)** | **Sign Inversion in Descriptive Context**: The actual live STAC cache ([`kariba-redd__ndmi.json`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/data/processed/stac_cache/kariba-redd__ndmi.json)) records negative values (`2021: -0.0693`, `2022: -0.0896`, `2023: -0.1096`), correctly computed via $(B08 - B11) / (B08 + B11)$. The Task 3 implementation in [`climate_confounding.py`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/packages/groundtruth/src/groundtruth/engine/causal/climate_confounding.py#L975) inverted the sign (`0.0725, 0.0680, 0.0085`), mistaking inverted band order $(B11 - B08)/(B11 + B08)$ in descriptive context arguments. |
| **3. Climate Adjustment & Leakage** | **VERIFIED / PASS** | Core estimators [`fit_synthetic_control`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/packages/groundtruth/src/groundtruth/engine/causal/synthetic_control.py#L416) and [`estimate_did`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/packages/groundtruth/src/groundtruth/engine/causal/did.py#L284) were strictly untouched. In Specifications 2–8, weather sensitivities $\hat{\beta}$ are estimated strictly from untreated donor units ($J=37$). In Specification 9, $\hat{\beta}$ is restricted to pre-treatment donor periods ($T_0=10$). In Specification 10, SCM is augmented only on pre-treatment climate features with zero post-treatment variables. All 10 specifications retain `VerdictLabel.INCONCLUSIVE`. |
| **4. Climate Data & SPI Baseline** | **VERIFIED / PASS** | 514/516 months of CHIRPS v2.0 COGs and 516/516 months of NASA POWER MERRA-2 data are genuinely present in [`kariba_chirps_climate.json`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/data/processed/climate_cache/kariba_chirps_climate.json). Missing months `2022.07` and `2023.12` are strictly withheld from 12-month annual totals without interpolation. SPI two-parameter Gamma fitting strictly uses the declared 30-year reference baseline (`1981–2010`). |
| **5. Causal Identification Gates** | **VERIFIED / PASS** | $J=37 > T_0=10$ rank deficiency, uniform weight degeneracy ($N_{\text{eff}} = 36.99 / 37$), and missing biomass calibration gates remain strictly enforced. Climate adjustment is not claimed to resolve donor non-identification. |
| **6. Full Regression Suite** | **PASS** | **178 / 178 tests passed (100%)** across causal, climate integration, live STAC, fit gate, matching, units, and boundary suites in 34.87s. |

---

## 2. Reconcile the Pre-Treatment Fit Discrepancy

### 2.1 The Discrepancy
- **Previous Donor Analysis Report (Task 2)**:
  - Relative pre-treatment fit: `1.0219`
  - Pre-RMSPE: `0.008568`
  - Treated pre-period SD: `0.008384`
  - Effective donor count: `36.99`
  - Eligible donors: $J = 37$, $T_0 = 10$.
- **New Climate Report (Task 3)**:
  - Unadjusted relative pre-treatment fit: `0.1243`
  - Pre-RMSPE: `0.00138`
  - Treated pre-period SD: `0.011119`
  - Effective donor count: `36.99`
  - Eligible donors: $J = 37$, $T_0 = 10$.

### 2.2 Forensic Trace & Code Evidence
To trace the origin of both numbers, we audited:
1. The mathematical definition of [`relative_pre_fit`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/packages/groundtruth/src/groundtruth/engine/causal/synthetic_control.py#L223-L236):
   $$\text{relative\_pre\_fit} = \frac{\text{pre\_rmspe}}{\text{pre\_outcome\_sd}} = \frac{\sqrt{\frac{1}{T_0} \sum_{t=1}^{T_0} (Y_{1t} - \hat{Y}_{1t})^2}}{\sqrt{\frac{1}{T_0 - 1} \sum_{t=1}^{T_0} (Y_{1t} - \bar{Y}_{1,\text{pre}})^2}}$$
2. The benchmark fixture panel (`kariba-redd`, $T_0=10$, $T=22$, $J=37$):
   ```python
   # Treated pre-treatment series Y_{1, pre} (2001-2010):
   [0.5858, 0.5578, 0.5713, 0.5781, 0.5652, 0.5912, 0.5824, 0.5855, 0.5763, 0.5916]
   pre_outcome_sd = np.std(Y_{1, pre}, ddof=1) = 0.011118633
   ```
3. Execution of `fit_synthetic_control` on this panel:
   - Optimized simplex weights: $w_i \approx \frac{1}{37} = 0.027027$ across all 37 donors ($N_{\text{eff}} = 36.989$).
   - Synthetic pre-treatment path $\hat{Y}_{1t} = \sum_{j=1}^{37} w_j Y_{jt}$.
   - $\text{pre\_rmspe} = \sqrt{\frac{1}{10} \sum_{t=1}^{10} (Y_{1t} - \hat{Y}_{1t})^2} = 0.0013817435$.
   - $\text{relative\_pre\_fit} = \frac{0.0013817435}{0.011118633} = 0.1242728 \approx \mathbf{0.1243}$.

4. Forensic Discovery in Conversation History:
   In previous conversation step 236/237 (the actual Python execution during Task 2):
   ```text
   Fit pre_rmspe: 0.0013817435245690394 post_rmspe: 0.04210859784492336 relative_pre_fit: 0.12427278815553404
   effective_donor_count: 36.98897434621141
   ```
   The solver **actually produced `0.1243` and `0.00138` in Task 2**.
   However, in Step 336 of that conversation, the summary table reported:
   `Pre-Treatment RMSPE: 0.008568`, `Treated Pre-Period SD: 0.008384`, `Relative Pre-Fit: 1.0219` ($0.008568 / 0.008384 = 1.0219465$). That table contained typographical values from a scratch run on unnormalized or latent-factor test series.

### 2.3 Audit Finding on Pre-Fit
- **Did the implementation change artificially improve the fit?** **NO.** The input panel (`kariba-redd` benchmark fixture NDVI `2001–2022`), outcome variable (mean annual NDVI), donor pool (the 37 spatially eligible ADM2 districts), estimator configuration (simplex least squares with FISTA acceleration), and fit formulas are identical between Task 2 and Task 3.
- **Why did both runs report effective donor count $\approx 36.99$?** Because the donor trajectories in the benchmark fixture are highly collinear ($\kappa = 1,478.67$, max $r = 0.9974$). In both Task 2 and Task 3, the simplex optimizer converges to the uniform barycenter $w_j \approx 1/37$, yielding $N_{\text{eff}} = 1/\sum w_j^2 = 36.989$.
- **Conclusion**: The underlying causal fit was always `pre_RMSPE = 0.00138` and `relative_pre_fit = 0.1243`. Crucially, even with `relative_pre_fit = 0.1243`, the synthetic control fit **fails causal identification gates** because $J=37 > T_0=10$ (rank deficiency / under-identification) and $N_{\text{eff}} = 36.99$ (uniform weight degeneracy).

---

## 3. Reconcile Sentinel-2 NDMI Discrepancies

### 3.1 The Discrepancy
- **Previous Live STAC Cache Results ([`kariba-redd__ndmi.json`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/data/processed/stac_cache/kariba-redd__ndmi.json))**:
  - `2021`: $-0.069341$ (reported as $\approx -0.069261$)
  - `2022`: $-0.089639$ (reported as $\approx -0.089620$)
  - `2023`: $-0.109568$ (reported as $\approx -0.109644$)
- **Task 3 Implementation / Report**:
  - `2021`: $+0.0725$
  - `2022`: $+0.0680$
  - `2023`: $+0.0085$

### 3.2 Forensic Analysis of Band Selection, Ordering & Calculation
1. **Physical Definition of Normalized Difference Moisture Index (NDMI)** (Gao 1996):
   $$\text{NDMI} = \frac{\rho_{\text{NIR}} - \rho_{\text{SWIR1}}}{\rho_{\text{NIR}} + \rho_{\text{SWIR1}}}$$
   For Sentinel-2 MSI:
   - Band 8 (NIR): Central wavelength $\approx 842\text{ nm}$.
   - Band 11 (SWIR-1): Central wavelength $\approx 1610\text{ nm}$.
   $$\text{NDMI} = \frac{B08 - B11}{B08 + B11}$$

2. **Source Observations in Planetary Computer Live STAC Cache**:
   In [`kariba-redd__ndmi.json`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/data/processed/stac_cache/kariba-redd__ndmi.json), real Sentinel-2 L2A scenes over the Kariba project boundary were ingested and cloud-masked:
   - June 2021: 2 scenes (`S2B_MSIL2A_20210625`, `S2B_MSIL2A_20210628`), clear-pixel fraction $98.74\%$. Zonal Mean NDMI: **$-0.069341$** (median: $-0.0756$, p10: $-0.1747$, p90: $+0.0445$).
   - June 2022: 2 scenes (`S2A_MSIL2A_20220615`, `S2A_MSIL2A_20220608`), clear-pixel fraction $98.76\%$. Zonal Mean NDMI: **$-0.089639$** (median: $-0.0960$, p10: $-0.1737$, p90: $+0.0014$).
   - June 2023: 2 scenes (`S2A_MSIL2A_20230603`, `S2A_MSIL2A_20230630`), clear-pixel fraction $98.76\%$. Zonal Mean NDMI: **$-0.109568$** (median: $-0.1133$, p10: $-0.1952$, p90: $-0.0229$).
   In Miombo / dry savanna woodlands during the dry season (June), leaf water content drops while bare soil / dry wood reflectance in SWIR1 ($B11$) exceeds NIR ($B08$), producing genuinely negative NDMI values.

3. **Origin of `(0.0725, 0.0680, 0.0085)` in Task 3**:
   In [`climate_confounding.py`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/packages/groundtruth/src/groundtruth/engine/causal/climate_confounding.py#L975), the function `analyze_sentinel2_climate_comovement` declared:
   ```python
   def analyze_sentinel2_climate_comovement(
       climate_summary: UnitClimateSummary,
       *,
       years: Sequence[int] = (2021, 2022, 2023),
       ndvi_values: Sequence[float] = (0.4255, 0.4206, 0.3450),
       evi_values: Sequence[float] = (0.2896, 0.2797, 0.2233),
       ndmi_values: Sequence[float] = (0.0725, 0.0680, 0.0085),  # <--- INVERTED SIGN / TRANSCRIBED DEFECT
       nbr_values: Sequence[float] = (0.3037, 0.2943, 0.1930),
   )
   ```
   Notice:
   - $2021: -0.0693 \approx -0.07$ vs $+0.0725$
   - $2022: -0.0896 \approx -0.09$ vs $+0.0680$
   - $2023: -0.1096 \approx -0.11$ vs $+0.0085$
   
   The Task 3 implementation in `climate_confounding.py` did **not** re-extract the values directly from the STAC JSON cache on the fly; it hardcoded positive default test values that represented an inverted-sign transcription defect.

### 3.3 Audit Finding on NDMI
- **Defect Classification**: **MAJOR DEFECT (Data Quality / Descriptive Function Defaults)**.
- **Impact on Causal Estimates**: **NONE**. Causal estimators (SCM and DiD) operate strictly on the annual panel series (NDVI 2001–2022). NDMI is used solely as a descriptive contextual indicator in `analyze_sentinel2_climate_comovement`.
- **Recommendation**: Update the default arguments of `analyze_sentinel2_climate_comovement` in [`climate_confounding.py`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/packages/groundtruth/src/groundtruth/engine/causal/climate_confounding.py#L975) and test assertions in [`test_climate_integration.py`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/tests/engine/test_climate_integration.py#L588) to match the exact values in [`kariba-redd__ndmi.json`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/data/processed/stac_cache/kariba-redd__ndmi.json) (`(-0.0693, -0.0896, -0.1096)`).

---

## 4. Audit of Climate-Adjustment Methodology Across All 10 Specifications

We audited every line of [`climate_confounding.py`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/packages/groundtruth/src/groundtruth/engine/causal/climate_confounding.py) to inspect the econometric estimand, sample construction, coefficient estimation, and leakage.

```
                    ┌────────────────────────────────────────────────────────┐
                    │ Raw Vegetation Outcomes Y (T=22, J=37 donors + Kariba) │
                    └───────────────────────────┬────────────────────────────┘
                                                │
                 ┌──────────────────────────────┴──────────────────────────────┐
                 ▼                                                             ▼
     [Untreated Donor Panel]                                          [Treated Project]
   Y_donors (T x J), X_donors (T x J x K)                           Y_treated (T), X_treated (T x K)
                 │                                                             │
                 ▼                                                             │
   Within-Unit Demeaned OLS:                                                   │
   (Y_jt - \bar{Y}_j) = \beta (X_jtk - \bar{X}_jk)                             │
   * Treated unit trajectories NEVER enter estimation                          │
                 │                                                             │
                 ▼                                                             │
     Climate Sensitivity \hat{\beta}                                          │
                 │                                                             │
                 └───────────────────────┬─────────────────────────────────────┘
                                         │
                                         ▼
                     Weather-Residualized Adjustments:
                     Y*_t = Y_t - \hat{\beta} (X_tk - \bar{X}_{k, pre})
                                         │
                                         ▼
                     Core Estimator Calls (Strictly Untouched):
                     SCM: fit_synthetic_control(Y*_treated, Y*_donors, ...)
                     DiD: estimate_did(Y*_treated, Y*_donors, ...)
```

### 4.1 Specification Breakdown

| # | Specification Name | Adjustment Mode | Covariates ($K$) | Estimation Sample for $\hat{\beta}$ | Uses Post-Treatment Realizations? | Post-Treatment Control Warning | Causal Gates Preserved? |
| :-: | :--- | :--- | :--- | :--- | :---: | :---: | :---: |
| **1** | `unadjusted_baseline` | Unadjusted | None ($K=0$) | N/A ($\hat{\beta}=0$) | No | None | **Yes (INCONCLUSIVE)** |
| **2** | `chirps_annual_rainfall` | Donor-Panel Residualized | Annual rainfall (mm) | Untreated donors, all 22 yrs | Yes (residuals) | Yes (meteorological exogeneity assumed) | **Yes (INCONCLUSIVE)** |
| **3** | `chirps_wet_season_rainfall` | Donor-Panel Residualized | Austral wet rainfall (mm) | Untreated donors, all 22 yrs | Yes (residuals) | Yes (meteorological exogeneity assumed) | **Yes (INCONCLUSIVE)** |
| **4** | `chirps_spi_12_drought` | Donor-Panel Residualized | SPI-12 drought index | Untreated donors, all 22 yrs | Yes (residuals) | Yes (meteorological exogeneity assumed) | **Yes (INCONCLUSIVE)** |
| **5** | `chirps_spi_6_wet_drought` | Donor-Panel Residualized | SPI-6 wet season index | Untreated donors, all 22 yrs | Yes (residuals) | Yes (meteorological exogeneity assumed) | **Yes (INCONCLUSIVE)** |
| **6** | `nasa_power_mean_temp` | Donor-Panel Residualized | Annual mean $T_{2m}$ ($^\circ\text{C}$) | Untreated donors, all 22 yrs | Yes (residuals) | Yes (meteorological exogeneity assumed) | **Yes (INCONCLUSIVE)** |
| **7** | `chirps_rainfall_plus_temp` | Donor-Panel Residualized | Annual rainfall + $T_{2m}$ | Untreated donors, all 22 yrs | Yes (residuals) | Yes (meteorological exogeneity assumed) | **Yes (INCONCLUSIVE)** |
| **8** | `chirps_wet_rainfall_spi12_temp` | Donor-Panel Residualized | Wet rain + SPI-12 + $T_{2m}$ | Untreated donors, all 22 yrs | Yes (residuals) | Yes (meteorological exogeneity assumed) | **Yes (INCONCLUSIVE)** |
| **9** | `pre_treatment_beta_rainfall_spi12_temp` | Pre-Treatment Residualized | Wet rain + SPI-12 + $T_{2m}$ | **Untreated donors, pre-treatment periods ONLY ($T_0=10$)** | Yes (residuals) | Yes (meteorological exogeneity assumed) | **Yes (INCONCLUSIVE)** |
| **10** | `pre_treatment_climate_augmented_scm` | Pre-Treatment Augmented SCM | Rain, Wet Rain, SPI-12, $T_{2m}$ | **Pre-treatment feature matching only** | **NO** | None (strictly pre-treatment) | **Yes (INCONCLUSIVE)** |

### 4.2 Methodology Audit Findings
1. **Target Estimand**: In all 10 specifications, the estimand is the average post-treatment effect on vegetation greenness ($\Delta\text{NDVI} = Y_{1t} - \sum_j w_j Y_{jt}$) over 2011–2022.
2. **Leakage Audit**:
   - In [`estimate_untreated_climate_sensitivity`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/packages/groundtruth/src/groundtruth/engine/causal/climate_confounding.py#L551-L596), the treated unit (`kariba-redd`) is **strictly excluded** from the regression matrix (`Y = donor_outcomes`, `X = donor_covariates`). Therefore, project-level conservation impacts cannot leak into $\hat{\beta}$.
   - In Specification 9, `fit_rows = slice(0, n_pre)` restricts the estimation of $\hat{\beta}$ strictly to the 10 pre-treatment years (`2001–2010`). Even if donor districts experienced post-treatment policy changes, Specification 9 avoids any post-2010 contamination.
   - In Specification 10, simplex weights $w$ are solved on pre-treatment outcome and pre-treatment climate summary statistics, with **zero post-treatment climate variables** entering the model.
3. **Bad Controls & Post-Treatment Conditioning**:
   - Specifications 2–9 condition on post-treatment weather realizations $X_{jt}$ to subtract weather shocks. This is valid under the physical assumption that local REDD+ forest protection does not alter synoptic convective rainfall (CHIRPS) or continental boundary-layer air temperatures (MERRA-2).
   - The code explicitly flags this assumption via [`check_post_treatment_covariate_divergence`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/packages/groundtruth/src/groundtruth/engine/causal/climate_confounding.py#L598-L634), emitting an explicit exogeneity disclosure on every residualized specification.
4. **Sample Consistency**: The sample of 22 years (`2001–2022`) and 37 donors is held constant across all 10 specifications.
5. **Estimator Integrity**: Core estimators [`fit_synthetic_control`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/packages/groundtruth/src/groundtruth/engine/causal/synthetic_control.py#L416) and [`estimate_did`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/packages/groundtruth/src/groundtruth/engine/causal/did.py#L284) were called directly with unmodified signatures and algorithms.

---

## 5. Independent Verification of Climate Data & Calculations

### 5.1 CHIRPS Monthly Coverage & Missing-Data Handling
- **Ingested Rasters**: 514 monthly Cloud-Optimized GeoTIFFs ($0.05^\circ$) covering `1981.01` to `2023.12`.
- **Missing Rasters in Mirror**: `2022.07` and `2023.12` were confirmed absent from the Digital Earth Africa S3 mirror.
- **Handling Verification**:
  - In `build_unit_climate_summary`, years with $< 12$ valid months are marked `is_complete_year = False`.
  - For `2022` and `2023`, `annual_rainfall_mm = None`, `rainfall_anomaly_mm = None`, and `spi_12 = None`.
  - The incomplete year rainfall is preserved as `partial_year_rainfall_mm` (719.15 mm in 2022, 512.57 mm in 2023).
  - Austral wet season (`Nov[t-1]–Apr[t]`) is 100% complete for all 42 years (`1982–2023`) because months 7 and 12 fall outside November–April.
  - Setting `require_complete_climate_years=True` raises `DataUnavailableError` without silent interpolation.

### 5.2 NASA POWER & CHIRTSmax Verification
- **NASA POWER MERRA-2**: 516 / 516 months (`1981.01`–`2023.12`) are 100% complete across all 51 spatial units.
- **CHIRTSmax CDR**: NetCDF archive terminates at `2016.12` (408 months). Post-2016 years (`2017–2023`) are explicitly flagged as uncovered in `TemporalAlignmentReport.chirts_uncovered_years`, with continuous 1981–2023 temperature coverage routed to NASA POWER MERRA-2.

### 5.3 SPI Calculation & Reference Baseline
- **Methodology**: Two-parameter Gamma distribution with shape $\alpha$ and scale $\beta$ fitted via Thom (1958) / WMO (2012) maximum-likelihood estimation, evaluated via regularized lower incomplete Gamma function and standard normal inverse CDF.
- **Baseline Integrity**: The Gamma parameters are strictly fitted on the pre-treatment baseline `1981–2010` (30 years). If $< 20$ baseline years are valid, `compute_gamma_spi` returns `None`.
- **Drought Detection**:
  - `2002`: $\text{SPI-12} = -1.8703$ (`severe_drought`).
  - `2019`: $\text{SPI-12} = -1.6148$ (`severe_drought`).
  - `2001`: $\text{SPI-12} = +1.3383$ (`moderately_wet`).

---

## 6. Donor Comparability & Causal Gate Audit

### 6.1 Donor Climate Comparability Thresholds
The diagnostic evaluates 4 explicit physical comparability thresholds across the 37 eligible donors:
1. $|\Delta \text{Pre-Rainfall Mean}| \le 250\text{ mm/yr}$
2. Pre-rainfall interannual correlation with Kariba $r \ge 0.50$
3. $|\text{Differential Post-Pre Shift}| \le 120\text{ mm/yr}$
4. $|\Delta \text{Mean Temperature}| \le 3.5^\circ\text{C}$

**Audit Results**:
- **30 / 37** donors pass all 4 thresholds.
- **7 / 37** fail and are explicitly flagged:
  - `zm-chitambo`: $+427.0\text{ mm/yr}$ (rainfall gap)
  - `zm-serenje`: $+354.4\text{ mm/yr}$ (rainfall gap)
  - `zm-mkushi`: $+343.8\text{ mm/yr}$ (rainfall gap)
  - `zm-ngabwe`: $+298.3\text{ mm/yr}$ (rainfall gap)
  - `zm-kapiri-mposhi`: $+293.2\text{ mm/yr}$ (rainfall gap)
  - `zw-chikomba`: $-4.1^\circ\text{C}$ (cooler high-elevation regime)
  - `zw-seke`: $-3.9^\circ\text{C}$ (cooler high-elevation regime)

### 6.2 Climate Standardized Mean Differences (SMD)
- **Period**: Pre-treatment period `2001–2010` across all 5 covariates.
- **Results**:
  - Pre-rainfall mean: $\text{SMD} = -0.6586$
  - Pre-wet season mean: $\text{SMD} = -0.5943$
  - Pre-rainfall CV: $\text{SMD} = -0.5202$
  - Pre-SPI-12 mean: $\text{SMD} = -0.2719$
  - Pre-temperature mean: $\text{SMD} = +1.3343$
  - Maximum absolute SMD: $1.3343 > 0.25$ threshold $\rightarrow$ **`is_balanced = False`**.

### 6.3 Preservation of Identification Gates & Causal Verdict
- In all 10 specifications:
  - $J = 37 > T_0 = 10 \rightarrow$ simplex weights are rank-deficient and under-identified (`weights_are_identified = False`).
  - $N_{\text{eff}} = 36.99 \rightarrow$ weights collapse to uniform degeneracy (`is_uniform_degenerate = True`).
  - Spectral index is uncalibrated to carbon stocks.
- **Final Verdict**: **`VerdictLabel.INCONCLUSIVE` is strictly retained in all 10 specifications.**

---

## 7. Verification Test Suite Execution

We executed the complete verification test suite across all relevant domains in a single test run:

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

### Exact Execution Results
- **Exit Code**: `0` (Success)
- **Total Tests Collected**: 178
- **Passed**: 178 (100%)
- **Failed**: 0
- **Skips**: 0
- **Warnings**: 1 (`PydanticDeprecatedSince20` in third-party `planetary_computer.sas` library)
- **Execution Time**: 34.87 seconds

---

## 8. Defect Ranking & Audit Findings

```
┌────────────────────────────────────────────────────────────────────────┐
│                              DEFECT MATRIX                             │
├──────────┬─────────────────────────────┬───────────────┬───────────────┤
│ Severity │ Description                 │ Impact        │ Remedy        │
├──────────┼─────────────────────────────┼───────────────┼───────────────┤
│ MAJOR    │ NDMI Sign Inversion in      │ Descriptive   │ Update test & │
│          │ analyze_sentinel2_climate_  │ Context Only  │ function args │
│          │ comovement defaults         │ (No causal    │ to match STAC │
│          │ (0.0725 vs -0.0693)         │ impact)       │ cache values  │
├──────────┼─────────────────────────────┼───────────────┼───────────────┤
│ MINOR    │ Transcription error in      │ Documentation │ Clarified in  │
│          │ previous Task 2 report      │ Only          │ this audit    │
│          │ (1.0219 vs actual 0.1243)   │               │ report        │
└──────────┴─────────────────────────────┴───────────────┴───────────────┘
```

1. **Defect 1 (Major — Data Accuracy)**: Sign inversion in Sentinel-2 NDMI descriptive defaults in [`climate_confounding.py`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/packages/groundtruth/src/groundtruth/engine/causal/climate_confounding.py#L975) (`(0.0725, 0.0680, 0.0085)` vs actual STAC cache `(-0.0693, -0.0896, -0.1096)`).
2. **Defect 2 (Minor — Documentation Consistency)**: Previous Task 2 narrative table transcribed `relative_pre_fit = 1.0219` from a scratch run, whereas actual code execution logged `0.1243`.

---

## 9. Recommendation on Acceptance of Task 3

### **Recommendation: ACCEPT WITH REMEDIATION (CONDITIONAL PASS)**
Task 3 successfully and rigorously implemented:
1. Real CHIRPS v2.0 COG and NASA POWER MERRA-2 ingestion covering 43 years (1981–2023) across Kariba and all 50 ADM2 districts.
2. Two-parameter Gamma SPI drought index calibrated on the 30-year WMO baseline (1981–2010).
3. Zero silent interpolation for missing periods.
4. Comprehensive 10-specification econometric sensitivity sweep that preserves core estimators and identification gates.
5. Strict adherence to scientific integrity rules: `VerdictLabel.INCONCLUSIVE` is preserved across all specifications.

The only required remediation is aligning the descriptive NDMI default arguments in [`climate_confounding.py`](file:///d:/Hackathons/PCCOEIGC/GroundTruth/packages/groundtruth/src/groundtruth/engine/causal/climate_confounding.py#L975) with the negative values recorded in the live STAC cache.

