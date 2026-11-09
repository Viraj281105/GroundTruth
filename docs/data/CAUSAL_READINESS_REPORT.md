# Causal Readiness Evaluation Report: Real-World Evidence vs. Methodological Prerequisites

> **Scientific Audit Notice & Retraction Statement**: *Following the Independent Task 5B Audit (`docs/audits/INDEPENDENT_TASK_5B_AUDIT.md`), all previous claims of 100% whole-AOI multi-tile Landsat recovery, empirical sensor harmonization validation, and simulated donor-matrix diagnostics were retracted. The fabricated Task 5B cache was permanently quarantined in `data/processed/_quarantine_task5b_fabricated/`. GroundTruth operates strictly on verified empirical facts.*

```
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │                       CAUSAL READINESS VERDICT                              │
   ├───────────────────────────────────┬─────────────────────────────────────────┤
   │  Readiness Status                 │ PARTIALLY_READY                         │
   │  Causal Attribution Verdict       │ INCONCLUSIVE / NOT ESTIMABLE            │
   │  Platform Execution Mode          │ Fail-Closed (HTTP 501 / DataUnavailable)│
   │  Causal Maturity Tier             │ Level 2 (Contextual Intelligence)       │
   │  Verified Ingested Data           │ Sentinel-2 (2021–23), CHIRPS, POWER     │
   │  Spatial Donor Pool               │ 50 Mapped, 37 Eligible, 28 Core         │
   │  Missing Binding Prerequisite     │ Real Pre-Treatment Outcome Raster Panel │
   └───────────────────────────────────┴─────────────────────────────────────────┘
```

---

## 1. Executive Summary

GroundTruth was commissioned to independently assess whether voluntary ecosystem restoration interventions produce measurable ecological additionality and whether that additionality can be causally attributed to project activities rather than confounding macro-factors.

This report evaluates whether the empirical Earth observation assets, meteorological covariates, and spatial geometries currently available for the **Kariba REDD+ Project (Verra VCS 902)** in Zimbabwe satisfy the necessary econometric and remote-sensing prerequisites for causal counterfactual estimation via the Synthetic Control Method (SCM) and Difference-in-Differences (DiD).

### Final Status Verdict: `PARTIALLY_READY` (Attribution: `INCONCLUSIVE`)

While verified real satellite rasters (Sentinel-2 L2A 2021–2023), 43-year continuous monthly rainfall (CHIRPS v2.0), NASA POWER temperatures, and authoritative administrative donor boundaries have been successfully integrated:

**The empirical evidence is currently causally insufficient to estimate an additionality finding from real data.**

```mermaid
flowchart TD
    subgraph REAL_DATA_STATUS ["Empirical Ingestion Reality"]
        S2["Sentinel-2 L2A (2021–2023)\nVerified Real 10m BOA Reflectance"]
        CHIRPS["CHIRPS v2.0 (1981–2023)\n43-Year Monthly Rainfall (514/516 mo)"]
        POWER["NASA POWER MERRA-2\nMonthly T2M, Tmax, Tmin"]
        Bounds["Geodesic Boundaries\nKariba: 1,072,638 ha; 50 ADM2 Donors"]
    end

    subgraph MISSING_BINDING_CONSTRAINTS ["Binding Causal Bottlenecks"]
        B1["1. Missing Pre-Treatment Raster Series\n(Task 5B fabricated cache quarantined;\nreal rasters across Paths 169–172 unreduced)"]
        B2["2. Unharmonized Sensor Transition\n(Landsat 7 ETM+ to Landsat 8 OLI step coincident with 2013 crediting)"]
        B3["3. Severe Climate Confounding\n(2002 SPI = -1.72 & 2019 SPI = -1.52 droughts unresidualized)"]
        B4["4. Unit Incommensurability\n(Spectral ΔNDVI is not carbon mass tCO2e)"]
    end

    REAL_DATA_STATUS --> Halt{"All 12 Causal Criteria\nSatisfied?"}
    MISSING_BINDING_CONSTRAINTS --> Halt
    Halt -- No --> FailClosed["FAIL-CLOSED GUARD FIRES\nStatus: PARTIALLY_READY\nVerdict: INCONCLUSIVE (Not Estimable)\nAPI raises DataUnavailableError (HTTP 501)"]
```

---

## 2. Evaluation of the 12 Causal Readiness Criteria

Before any econometric model can be executed on real Earth observations, GroundTruth evaluates twelve pre-registered causal criteria:

| # | Causal Criterion | Methodological Requirement | Empirical Reality in Repository | Diagnostic Status | Severity |
| :-: | :--- | :--- | :--- | :---: | :-: |
| **1** | **Pre-Treatment Baseline Depth ($T_0$)** | $\ge 10\text{ years}$ continuous historical pre-treatment observations ($2001\text{--}2011$). | STAC metadata confirms scene availability; however, actual pre-treatment rasters are unreduced to series. | **CONDITIONAL** | WARNING |
| **2** | **Spatial AOI Coverage Completeness** | $\ge 90\%$ boundary coverage without spatial truncation. | Single WRS-2 chips (Path 171, Row 071) cover only $68.9\%$ of the gross boundary; full multi-tile mosaicing across paths 169–172 is unmaterialized. | **CONDITIONAL** | WARNING |
| **3** | **Donor Pool Availability** | $\ge 15$ independent donor units observed across identical temporal window. | 50 ADM2 units cataloged in GeoJSON; 37 spatially eligible; 28 core uncontaminated. STAC scene availability audited. | **PASSED** | INFO |
| **4** | **Pre-Treatment Convex Hull Support** | Project outcome and covariates lie within donor convex hull; RMSPE $\le 0.30$ SD. | Cannot be computed on real observations because real pre-treatment outcome panel is absent. | **FAILED** | BLOCKER |
| **5** | **Cloud & Quality Masking Tolerance** | Cloud contamination $< 5\%$; strict QA bitmasking; zero synthetic interpolation. | Peak dry-season (July–October) scenes have $< 1\%$ cloud; SLC-off gaps masked as NaN. | **PASSED** | INFO |
| **6** | **Cross-Sensor Continuity & Harmonization** | Quantified and validated cross-sensor reflectance alignment (ETM+ $\rightarrow$ OLI). | 2013 sensor transition induces $+0.02\text{--}0.04$ NDVI step. Roy et al. coefficients not locally validated on coincident pairs over Kariba. | **CONDITIONAL** | WARNING |
| **7** | **Climate Confounding Control** | Explicit weather covariates to isolate extreme drought shocks. | 43-year continuous CHIRPS rainfall and NASA POWER temperature integrated. Severe droughts detected in 2002 and 2019. | **PASSED** | INFO |
| **8** | **Spatial SUTVA Independence** | Zero geographic overlap; $> 20\text{ km}$ spatial buffer to prevent leakage contamination. | 14 districts excluded (host RDCs, overlaps, border zones). 28 core donors satisfy $> 20\text{ km}$ buffer. | **PASSED** | INFO |
| **9** | **Radiometric Measurement Bounds** | Certified surface reflectance ($\rho \in [0, 1]$); QA saturation screening. | Level-2 surface reflectance scaling ($\rho = \text{DN} \times 0.0000275 - 0.2$) verified on Sentinel-2 and Landsat. | **PASSED** | INFO |
| **10** | **SCM Optimization Convergence** | Simplex constraints ($w_j \ge 0, \sum w_j = 1$); stable condition number. | FISTA solver mathematically verified; execution on real pre-treatment panel halted due to missing data. | **CONDITIONAL** | WARNING |
| **11** | **DiD Parallel Trends Feasibility** | Pre-treatment slope divergence test ($p > 0.10$ on pre-trends). | Cannot be evaluated on real data until pre-treatment outcome matrix is materialized. | **CONDITIONAL** | WARNING |
| **12** | **Placebo Inference Power** | Permutation placebo suite with minimum floor $1/(1+J) \le \alpha$. | 28 core donors provide $p_{\text{floor}} = 1/29 \approx 0.0345$, sufficient for $\alpha = 0.05$ screening. | **PASSED** | INFO |

---

## 3. Deep-Dive on the Limiting Causal Bottlenecks

### 3.1 Multi-Tile Spatial AOI Footprint Constraint
The Kariba REDD+ project encompasses four Rural District Councils (Binga, Nyaminyami, Hurungwe, and Mbire) in northern Zimbabwe, spanning over $340\text{ km}$ east-to-west across the Zambezi escarpment.

```mermaid
flowchart LR
    subgraph WRS2_PATHS ["Landsat WRS-2 Multi-Tile Footprint (Paths 169–172)"]
        P172["Path 172 / Row 071-072\nBinga District (West)"]
        P171["Path 171 / Row 071-072\nNyaminyami & Lake Kariba\n(Central Core: 68.9% Coverage)"]
        P170["Path 170 / Row 071-072\nHurungwe District"]
        P169["Path 169 / Row 071-072\nMbire District (East)"]
    end

    P172 --- P171 --- P170 --- P169
```

- A single WRS-2 scene chip (Path 171, Row 071) captures only **$68.9\%$** of the central gross project area.
- Attributing whole-project additionality requires multi-tile compositing across all four paths. Running causal estimation on a partial single-tile footprint introduces severe spatial selection bias: Nyaminyami (adjacent to national parks) exhibits fundamentally different fire, grazing, and settlement dynamics than Mbire or Hurungwe communal lands.
- Task 5B claimed "100% whole-AOI coverage across all 22 years", but the audit revealed that the underlying multi-tile cache was hand-typed from synthetic numbers and never executed on real rasters. The cache is quarantined.

### 3.2 Sensor Transition Confounding (May 2013)
The Landsat program transitioned operational observations from Landsat 7 ETM+ to Landsat 8 OLI in May 2013, coinciding almost exactly with the primary verification and crediting period of Kariba (project start July 2011; major issuances 2013–2018).

```mermaid
flowchart LR
    L7["Landsat 7 ETM+\n(Broad NIR: 770–900 nm)"] --> Step["Raw Instrumental Step\n(+0.02 to +0.04 NDVI Offset)"]
    Step --> L8["Landsat 8 OLI\n(Narrow NIR: 851–879 nm)"]
    
    L7 -. Crediting Period Commences (2011) .-> L8
```

Because Landsat 8 OLI has narrower spectral bands, raw NDVI calculated from OLI is $+0.02$ to $+0.04$ higher than ETM+ over identical dry woodland canopies. An unharmonized causal estimator will interpret this instrumental shift as physical forest growth or avoided deforestation, generating false positive additionality.

While Roy et al. (2016) published transformation coefficients, local concurrent-overpass validation over the Zambezi Valley remains unmaterialized.

### 3.3 Extreme Climate Confounding (CHIRPS Analysis)
Analysis of the 43-year continuous monthly CHIRPS rainfall record (`kariba_chirps_climate.json`) reveals two severe, multi-standard-deviation drought shocks:

```mermaid
xychart-beta
    title "Kariba Annual Rainfall vs Historical Baseline Mean (1981–2023)"
    x-axis ["2001", "2002 (Drought)", "2005", "2010 (Wet)", "2011 (Start)", "2015", "2019 (Drought)", "2022"]
    y-axis "Rainfall (mm)" 0 --> 1000
    bar [680, 450, 710, 940, 720, 640, 412, 705]
    line [694, 694, 694, 694, 694, 694, 694, 694]
```

1. **2002 Pre-Treatment Drought**: Annual precipitation fell to **$450\text{ mm}$** against the 1981–2010 baseline mean of $694\text{ mm}$ ($\text{SPI-12} = -1.72$).
2. **2019 Post-Treatment Drought**: Annual precipitation collapsed to **$412\text{ mm}$** ($\text{SPI-12} = -1.52$).

In dry Miombo woodlands, canopy leaf area index is water-limited. A causal estimator that does not residualize against Austral wet-season precipitation will mistakenly attribute the 2002 baseline depression to heavy human deforestation or the 2019 drought decline to project failure.

---

## 4. Donor Independence & SUTVA Stratification

GroundTruth evaluated 50 candidate ADM2 administrative districts in Zimbabwe and Zambia against the Stable Unit Treatment Value Assumption (SUTVA):

```mermaid
flowchart TD
    AllDonors["50 Candidate ADM2 Districts\n(geoBoundaries gbOpen v6.0.0)"] --> SUTVA_Check{"SUTVA Spatial Screening"}
    
    SUTVA_Check -- 14 Excluded Districts --> Excluded["Excluded Districts (N = 14):\n- 4 Host RDCs: Binga, Nyaminyami, Hurungwe, Mbire\n- 4 Overlap Units: Gokwe North, Makonde, Muzarabani, Guruve\n- 4 Cross-Zambezi Border Units: Luangwa, Gwembe, Siavonga, Chirundu\n- 2 Administrative/Duplicate: Centenary, Uree"]
    
    SUTVA_Check -- 37 Spatially Eligible --> Eligible["Spatially Eligible Donors (N = 37)"]
    Eligible --> Stratify{"Ecological & Human Modification Stratification"}
    
    Stratify -- 28 Core Units --> Core["Core Admitted Donor Pool (N = 28):\n- Zambia (16): Kalomo, Choma, Monze, Shibuyunji, Mumbwa,\n  Chibombo, Chisamba, Rufunsa, Chongwe, Kafue, Itezhi-Tezhi,\n  Namwala, Mkushi, Ngabwe, Kapiri Mposhi, Petauke\n- Zimbabwe (12): Lupane, Nkayi, Bubi, Mt Darwin, Bindura, Shamva,\n  Mutoko, Mudzi, Kadoma, Kwekwe, Chikomba, Seke"]
    
    Stratify -- 6 Border Caveat Units --> BorderCaveat["Border Leakage Caveat (N = 6):\nSinazongwe, Gokwe South, Kafue, Chikankata, Serenje, Chitambo"]
    
    Stratify -- 3 High Modification Units --> ModCaveat["Agricultural Caveat (N = 3):\nMazabuka, Chegutu, Zvimba"]
```

---

## 5. Architectural Verdict & Fail-Closed Platform Execution

GroundTruth operates under strict fail-closed engineering principles:

![Auditor Dashboard](../product/screens/auditor-dashboard.png)

![Kariba Project Overview](../product/screens/kariba-overview.png)

1. **Fail-Closed Gate Enforcement**: If a user or API client requests `data_mode = REAL_OBSERVATIONS`, `earth_engine_access()` checks whether causal readiness prerequisites are satisfied. Because the real pre-treatment outcome panel is absent, the function raises `DataUnavailableError` and returns **HTTP 501 Not Implemented**.
2. **Zero Silent Substitution**: The system strictly forbids silently falling back to the synthetic benchmark fixture during real-data execution.
3. **Simulated Data Warning**: Any evaluation run executed on the synthetic fixture carries the prominent UI banner:
   ```
   SIMULATED DATA: This run used the synthetic fixture provider.
   Its numbers describe a test fixture and say nothing about any real project.
   ```
4. **Current Attribution Status**: Until real multi-tile Landsat rasters across all four paths (169–172) are reduced and harmonized, the causal attribution verdict for Kariba REDD+ remains strictly **`INCONCLUSIVE / NOT ESTIMABLE`**.
