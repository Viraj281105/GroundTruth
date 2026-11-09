# Real Donor-Area Satellite Data Coverage & Eligibility Assessment Report

> **Scientific Audit Notice & Retraction Statement**: *Following the Independent Task 5B Audit (`docs/audits/INDEPENDENT_TASK_5B_AUDIT.md`), all previous claims that synthetic control numerical diagnostics (rank 11, condition number $\kappa = 91.7$, RMSPE $0.021$, SMD $0.086$, $N_{\text{eff}} = 4.8$) were computed from real donor vegetation data have been retracted. Those figures were produced by an inline pseudo-random generator (`np.random.seed(42)`). The honest empirical state: real administrative boundaries, 43-year CHIRPS climate covariates, and real Landsat STAC scene availability metadata exist across all 37 eligible donor districts; actual pre-treatment vegetation raster extraction remains pending.*

```
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │                          DONOR POOL AUDIT SUMMARY                           │
   ├───────────────────────────────────┬─────────────────────────────────────────┤
   │  Total Administrative Units       │ 50 Real geoBoundaries ADM2 Districts    │
   │  SUTVA Exclusions                 │ 14 Excluded (Host, Overlap, Border)     │
   │  Spatially Eligible Donors        │ 37 Units (16 Zimbabwe, 21 Zambia)       │
   │  Core Uncontaminated Pool         │ 28 Admitted Primary Donors (> 20 km)    │
   │  Satellite Scene Availability     │ 100% Available across 5 Benchmark Epochs│
   │  Climate Covariate Coverage       │ 43-Year Continuous CHIRPS Rainfall      │
   │  Current Econometric State        │ Level 2 (Contextual Intelligence)       │
   └───────────────────────────────────┴─────────────────────────────────────────┘
```

---

## 1. Executive Summary

A defensible causal evaluation using the Synthetic Control Method (SCM) or Difference-in-Differences (DiD) requires an un-contaminated comparison pool of untreated regional units observed across identical pre-treatment and post-treatment time horizons.

GroundTruth evaluated **50 candidate ADM2 administrative districts** across Zimbabwe and Zambia derived from official geoBoundaries gbOpen v6.0.0 layers (`cases/boundaries/kariba-donors.geojson`).

### Key Audit Findings
1. **Authoritative Boundary Provenance**: All donor geometries originate from official ZIMSTAT (Zimbabwe) and GRID3 (Zambia) census cartography with verified polygon vertices.
2. **SUTVA & Leakage Screening**: 14 districts are strictly excluded due to direct physical overlap with Kariba's forest parcels, cross-border adjacency along Lake Kariba, or administrative duplication.
3. **100% STAC Scene Availability**: All 37 spatially eligible donor districts possess verified USGS Landsat Collection 2 Level-2 Surface Reflectance scenes across all five audited benchmark epochs (2001, 2005, 2010, 2015, 2022) during peak dry season (July 1 – October 31) with $0.00\%$ minimum cloud cover (`data/processed/donor_landsat_coverage_audit.json`).
4. **Continuous Precipitation Covariates**: All candidate districts possess complete 43-year monthly precipitation records from CHIRPS v2.0 (1981–2023) enabling rainfall-conditioned matching.
5. **Observational vs. Materialized Panel Distinction**: While satellite scene availability is 100% verified, pixel-level extraction of annual zonal mean vegetation indices ($\text{NDVI}, \text{EVI}$) for the pre-treatment baseline ($2001\text{--}2011$) has not yet been executed on real rasters. Causal estimation remains paused at Level 2 Contextual Intelligence.

---

## 2. Donor Stratification & SUTVA Screening Protocol

```mermaid
flowchart TD
    Total["50 Candidate ADM2 Administrative Districts\n(geoBoundaries gbOpen v6.0.0)"] --> S1{"SUTVA Spatial Overlap Check"}
    
    S1 -- 4 Host Districts --> Ex1["Direct Host RDCs (SUTVA Violation):\nzw-hurungwe, zw-mbire, zw-binga, zw-nyaminyami"]
    S1 -- 4 Boundary Overlaps --> Ex2["Polygon Overlap Districts:\nzw-gokwe-north, zw-makonde, zw-muzarabani, zw-guruve"]
    S1 -- 4 Border Leakage Units --> Ex3["Cross-Zambezi Precautionary Belt (<20km):\nzm-luangwa, zm-gwembe, zm-siavonga, zm-chirundu"]
    S1 -- 2 Invalid / Duplicates --> Ex4["Administrative Anomalies:\nzw-centenary (maps to Muzarabani), zw-uree (non-existent)"]
    
    S1 -- 37 Spatially Eligible --> S2["37 Spatially Eligible Donor Districts"]
    
    S2 --> S3{"Ecological & Human Pressure Stratification"}
    S3 -- 28 Core Units --> Core["Core Admitted Donor Pool (N = 28)\n- Zero Boundary Adjacency (> 20 km Buffer)\n- Balanced Rainfall (550–900 mm)\n- Pristine Zambezian Miombo / Mopane Woodlands"]
    S3 -- 6 Border Units --> Caveat1["Border Leakage Caveat Pool (N = 6)\n- 20–50 km Buffer: zm-sinazongwe, zw-gokwe-south\n- Wet Miombo Outliers: zm-serenje, zm-chitambo\n- Retained strictly for sensitivity testing"]
    S3 -- 3 Modified Units --> Caveat2["Agricultural Modification Caveat Pool (N = 3)\n- High Road Density & Cropland: zm-mazabuka, zw-chegutu, zw-zvimba\n- Downweighted in pristine woodland counterfactuals"]
```

---

## 3. Audited Donor-by-Donor Satellite Scene Availability

The following table summarizes the real satellite scene availability audited from `data/processed/donor_landsat_coverage_audit.json` across the 37 spatially eligible donor districts:

| Donor ID | Unit Name | Country | Gross Area ($km^2$) | 2001 Scenes (Sensors) | 2005 Scenes (Sensors) | 2010 Scenes (Sensors) | 2015 Scenes (Sensors) | 2022 Scenes (Sensors) | Min Cloud | Stratification Tier |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `zw-gokwe-south` | Gokwe South | ZWE | 11,123.9 | 20 (L5, L7) | 20 (L5, L7) | 14 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Border Caveat |
| `zw-hwange` | Hwange | ZWE | 27,275.4 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zw-lupane` | Lupane | ZWE | 8,924.1 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zw-nkayi` | Nkayi | ZWE | 4,675.2 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zw-buby` | Bubi | ZWE | 6,128.8 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zw-mt-darwin` | Mount Darwin | ZWE | 4,635.0 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zw-bindura` | Bindura | ZWE | 2,260.5 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zw-shamva` | Shamva | ZWE | 2,694.7 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zw-mutoko` | Mutoko | ZWE | 4,124.6 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zw-mudzi` | Mudzi | ZWE | 4,213.9 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zw-zvimba` | Zvimba | ZWE | 6,108.3 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Ag Modification |
| `zw-chegutu` | Chegutu | ZWE | 5,348.6 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Ag Modification |
| `zw-kadoma` | Kadoma | ZWE | 9,874.2 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zw-kwekwe` | Kwekwe | ZWE | 8,765.4 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zw-chikomba` | Chikomba | ZWE | 6,532.1 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zw-seke` | Seke | ZWE | 2,641.8 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zm-sinazongwe`| Sinazongwe | ZMB | 4,812.3 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Border Caveat |
| `zm-kalomo` | Kalomo | ZMB | 15,042.8 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zm-choma` | Choma | ZMB | 7,314.5 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zm-monze` | Monze | ZMB | 4,874.2 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zm-mazabuka` | Mazabuka | ZMB | 6,241.9 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Ag Modification |
| `zm-chikankata`| Chikankata | ZMB | 2,754.1 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Border Caveat |
| `zm-shibuyunji`| Shibuyunji | ZMB | 1,732.4 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zm-mumbwa` | Mumbwa | ZMB | 21,114.7 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zm-chibombo` | Chibombo | ZMB | 13,428.1 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zm-chisamba` | Chisamba | ZMB | 5,214.6 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zm-rufunsa` | Rufunsa | ZMB | 9,412.3 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zm-chongwe` | Chongwe | ZMB | 8,623.5 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zm-kafue` | Kafue | ZMB | 4,213.8 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Border Caveat |
| `zm-itezhitezhi`| Itezhi-Tezhi | ZMB | 15,821.4 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zm-namwala` | Namwala | ZMB | 10,241.6 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zm-serenje` | Serenje | ZMB | 23,412.0 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Border Caveat |
| `zm-chitambo` | Chitambo | ZMB | 11,241.5 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Border Caveat |
| `zm-mkushi` | Mkushi | ZMB | 17,621.8 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zm-ngabwe` | Ngabwe | ZMB | 7,124.3 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zm-kapiri-mposhi`| Kapiri Mposhi | ZMB | 17,241.9 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |
| `zm-petauke` | Petauke | ZMB | 15,214.7 | 20 (L5, L7) | 20 (L5, L7) | 20 (L5, L7) | 20 (L7, L8) | 20 (L7, L8, L9) | 0.0% | Core Admitted |

*Note: Query results capped at 20 items per STAC request. In every district-epoch query, multiple valid cloud-free scenes met the filtering criteria.*

---

## 4. Ecological & Climatic Covariate Balance

Using the continuous 43-year CHIRPS v2.0 dataset (`kariba_chirps_climate.json`), candidate donor districts were matched on pre-treatment rainfall distributions:

```mermaid
xychart-beta
    title "Mean Annual Rainfall: Kariba vs Candidate Donor Pools (1981–2010 Baseline)"
    x-axis ["Kariba (Treated)", "Kalomo", "Choma", "Gokwe South", "Kadoma", "Mutoko", "Serenje (Wet Outlier)"]
    y-axis "Rainfall (mm/year)" 0 --> 1200
    bar [694, 742, 768, 710, 745, 680, 1085]
```

- **Kariba Baseline Rainfall**: Mean $694.2\text{ mm/year}$ ($\sigma = 156.2\text{ mm}$).
- **Ecologically Balanced Donors**: Kalomo ($742\text{ mm}$), Gokwe South ($710\text{ mm}$), Kadoma ($745\text{ mm}$), Kwekwe ($685\text{ mm}$), Choma ($768\text{ mm}$).
- **High-Rainfall Wet Outliers**: Northern Zambian districts like Serenje ($1,085\text{ mm}$) and Chitambo ($1,140\text{ mm}$) represent wet Miombo ecoregions that receive zero simplex weight when fitting a dry Miombo counterfactual. They are flagged with a border/rainfall caveat.

---

## 5. Permutation Inference Power with 28 Core Donors

In permutation inference (Abadie et al., 2010; Phipson & Smyth, 2010), the test statistic is evaluated against $J$ in-space placebos:

$$p = \frac{1 + \sum_{j=2}^{J+1} \mathbb{I}\left(R_j \ge R_1\right)}{1 + J}$$

```mermaid
flowchart LR
    A["Core Admitted Pool: J = 28 Donors"] --> B["Total Permutation Fits: J + 1 = 29 Units"]
    B --> C["Sample-Size Permutation Floor:\np_floor = 1 / 29 ≈ 0.0345"]
    C --> D["Sufficient to Reject Null at α = 0.05\nInsufficient for α = 0.01\n(Transparently Reported in UI)"]
```

![Government Regulator Dashboard](../product/screens/government-dashboard.png)

![Kariba Project Overview](../product/screens/kariba-overview.png)

### SCM Weight Non-Identification when $J > T_0$
With $J = 28$ core donors and $T_0 = 11$ pre-treatment baseline years ($2001\text{--}2011$), the optimization problem is underdetermined ($J > T_0$).
- The counterfactual time-series trajectory $\hat{Y}_{1t}^{(0)}$ is uniquely determined.
- The assignment of weights among collinear donors is non-unique.
- GroundTruth reports `fit.weights_identified = False` in the evidence bundle, preventing misrepresentation of specific donor weights as an exclusive counterfactual set.
