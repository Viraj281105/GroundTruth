# Kariba REDD+ (VCS 902) Real-World Data Audit & Foundation Assessment

> **Scientific Audit Notice & Retraction Statement**: *Following the Independent Task 5B Audit (`docs/audits/INDEPENDENT_TASK_5B_AUDIT.md`), all previous claims that a whole-AOI, multi-tile Landsat pre-treatment panel (2001–2022) had been recovered from satellite imagery have been retracted. The underlying cache was hand-typed and has been quarantined in `data/processed/_quarantine_task5b_fabricated/`. This assessment establishes the true factual inventory of genuine Earth observations versus synthetic test fixtures for Kariba REDD+.*

```
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │                          KARIBA DATA AUDIT MATRIX                           │
   ├───────────────────────────────────┬─────────────────────────────────────────┤
   │  Gross Geodesic Project Area      │ 1,072,638 ha (Binga, Nyaminyami, etc.)  │
   │  Crediting Accounting Forest Area │ 784,987 ha (VCS Project Description)    │
   │  Verified Real Satellite Data     │ Sentinel-2 L2A BOA Reflectance (2021–23)│
   │  Verified Real Climate Covariates │ 43-Year CHIRPS Rainfall (514/516 Months)│
   │  Candidate Donor Districts        │ 50 Mapped, 37 Eligible, 28 Core         │
   │  Historical Pre-Treatment Panel   │ Missing / Quarantined                   │
   │  Causal Readiness Verdict         │ PARTIALLY_READY (Level 2 Contextual)    │
   │  Causal Attribution Verdict       │ INCONCLUSIVE / NOT ESTIMABLE            │
   └───────────────────────────────────┴─────────────────────────────────────────┘
```

---

## 1. Executive Summary

This assessment provides an independent, evidence-first audit of the environmental, remote sensing, and econometric data foundation for the **Kariba REDD+ Project (Verra VCS 902)** in northwestern Zimbabwe.

Kariba REDD+ is the largest and most scrutinized project in voluntary carbon market history. Following a two-year investigation concluded in September 2025, Verra confirmed that a substantial fraction (~57%) of the ~27 million carbon credits issued were in excess of achieved emission reductions.

GroundTruth's role is not to reproduce or dispute Verra's investigation, but to establish an auditable, independent causal verification platform that evaluates additionality strictly against empirical Earth observations.

This audit establishes:
1. The exact spatial boundaries and geodesic geometry of the Kariba project area.
2. The inventory of verified real-world datasets vs. synthetic test fixtures.
3. The empirical sensor gaps, instrumental transitions, and climate confounders that govern causal readiness.
4. The architectural trace from user-facing dashboards down to physical storage assets.

---

## 2. Comprehensive Inventory of Datasets

### 2.1 Genuine Real-World Datasets Available in Repository

```mermaid
flowchart TD
    subgraph Genuine_Real_Assets ["Verified Empirical Assets in Repository"]
        A1["Sentinel-2 L2A STAC Observations\n- Spatial: Kariba Tile 36LTH (83,327 ha forest)\n- Temporal: 2021–2023 Dry Season\n- Path: data/processed/stac_cache/kariba-redd__*.json\n- Status: INTEGRATED (Real 10m BOA)"]
        
        A2["CHIRPS v2.0 Monthly Rainfall\n- Spatial: 0.05° grid over Kariba + 50 Donors\n- Temporal: 1981–2023 (514/516 months real)\n- Path: data/processed/climate_cache/kariba_chirps_climate.json\n- Status: INTEGRATED (Real Met Feed)"]
        
        A3["NASA POWER MERRA-2 Climatology\n- Spatial: 0.5° × 0.625° grid over Kariba + Donors\n- Parameters: T2M, Tmax, Tmin (1981–2023)\n- Status: INTEGRATED (Real Temperature)"]
        
        A4["Project Geodesic Boundary\n- Spatial: 1,072,638 ha (4 Rural District Councils)\n- Source: Official Verra Submission (_KML_902.kml)\n- Path: cases/boundaries/kariba-redd.geojson\n- Status: INTEGRATED (Cryptographic SHA-256)"]
        
        A5["Authoritative Donor Boundaries\n- Spatial: 50 ADM2 Districts (ZWE & ZMB)\n- Source: geoBoundaries gbOpen v6.0.0\n- Path: cases/boundaries/kariba-donors.geojson\n- Status: INTEGRATED (37 Eligible, 28 Core)"]
    end
```

### 2.2 Synthetic Datasets Retained Strictly for Testing

| Asset Name | Underlying Origin | Scope & Content | Function & Operating Policy |
| :--- | :--- | :--- | :--- |
| `kariba_synthetic_benchmark.json` | Parametric latent factor simulation | 2000–2022 panel ($N=18$/yr, 50 donors centered on Kariba) | Retained under Operating Rule 12 strictly for deterministic CI/CD regression tests. **Forbidden from being served as real observations.** |
| `SyntheticObservationAccess` | Latent factor generator (`synthetic.py`) | Parametric vegetation series | Verifies simplex solver and gate logic on known ground-truth additionality. |
| `SyntheticCovariateAccess` | Gaussian random generator | Parametric covariate tables | Tests quadratic programming solver under synthetic constraints. |

### 2.3 Quarantined Artifacts (Task 5B Independent Audit P0-1)

| Quarantined Asset | Generating Script | Audit Finding | Location |
| :--- | :--- | :--- | :--- |
| `kariba-redd__{ndvi,evi,ndmi,nbr}.json` | `scripts/build_multitile_cache.py` | Hand-typed dictionary values labeled `REAL_STAC`; hardcoded 100% coverage; synthetic scene IDs and dates. Never read a raster. | `data/processed/_quarantine_task5b_fabricated/` |

---

## 3. Spatial Geometry & Boundary Reconciliation

A rigorous geometric recomputation of `cases/boundaries/kariba-redd.geojson` clarifies the differing hectare figures cited across project literature:

```mermaid
flowchart TD
    GrossKML["1. Gross Geodesic Union Boundary Area\n1,072,638 ha (10,726.38 km²)\n- Derived from Verra _KML_902.kml (SHA-256: 3e9ea051...)\n- Recomputed via Africa Albers Equal Area & UTM 35S\n- Encompasses 4 RDCs: Binga, Nyaminyami, Hurungwe, Mbire"]
    
    GrossPD["2. Project Description Gross Stated Area\n1,077,930 ha (10,779.30 km²)\n- Stated in 2012 Project Description (p. 98)\n- Divergence of 0.49% (5,292 ha) due to legacy planar projection"]
    
    ForestArea["3. Crediting Accounting Forest Area\n784,987 ha (7,849.87 km²)\n- Baseline forested Miombo/Mopane canopy at project start (2011)\n- 72.8% of Gross Boundary (remaining 27.2% is water, rock, settlements)\n- Credits issued exclusively against this area"]
    
    RegistryTypo["4. Public Registry Portal Typo\n747,801 ha (7,478.01 km²)\n- Public web portal typo; appears in zero validation reports\n- Disregarded by GroundTruth"]

    GrossKML -. Planar Distortion .-> GrossPD
    GrossKML === ForestArea
    GrossKML -. Web Typo .-> RegistryTypo
```

---

## 4. Multi-Sensor Constellation & Temporal Coverage

```mermaid
flowchart LR
    subgraph Constellation_Timeline ["Satellite Constellation Timeline over Kariba (2001–2023)"]
        L5["Landsat 5 TM\n(2001–2011)"] --> L7["Landsat 7 ETM+\n(2001–2022)"]
        L7 --> L8["Landsat 8 OLI\n(2013–2022)"]
        L8 --> L9["Landsat 9 OLI-2\n(2021–2022)"]
        L8 -. Overlap .-> S2["Sentinel-2 L2A\n(2021–2023)"]
    end
```

| Time Period | Primary Sensors | Kariba Project Observations | Donor Pool Observations | Empirical Status & Quality Constraints |
| :--- | :--- | :---: | :---: | :--- |
| **2001–2003** | Landsat 5 TM, Landsat 7 ETM+ | 31–43 scenes/yr | Audited across all 37 donors | Pre-SLC-off Landsat 7; clean 30m radiometry; dry-season clear fraction $> 80\%$. |
| **2003–2012** | Landsat 7 ETM+ (SLC-off), Landsat 5 TM | 20–67 scenes/yr | Audited across all 37 donors | Scan Line Corrector failure (post-May 2003) creates ~22% missing scan lines. Gaps strictly masked as NaN. |
| **2013–2020** | Landsat 8 OLI, Landsat 7 ETM+ | 97–100 scenes/yr | Audited across all 37 donors | 12-bit dynamic range; narrow NIR band requires Roy et al. (2016) harmonization to prevent false additionality. |
| **2021–2022** | Landsat 8/9 OLI, Sentinel-2 L2A | Dual-sensor overlap | Audited across all 37 donors | Cross-sensor overlap allows empirical inter-calibration between Landsat 30m and Sentinel-2 10m. |
| **2023** | Sentinel-2 L2A | High-density 5-day repeat | Available across donors | Sentinel-2 processing baseline 05.10; BOA offset harmonization applied. |

---

## 5. Architectural Data Consumption Trace

The following diagram traces user-facing surfaces down to underlying storage assets:

```mermaid
flowchart TD
    subgraph User_Facing_Surfaces ["User Interface & API Surfaces"]
        UI["Web App: EvidenceView / ReportView / CounterfactualChart"]
        API["FastAPI: POST /cases/{id}/verify"]
        Doctor["CLI: groundtruth doctor"]
    end

    subgraph Data_Routing_Gateway ["Data Access Gateway (groundtruth.platform.datasets.access)"]
        Router{"request.synthetic?"}
        SynthAccess["synthetic_fixture_access()"]
        EEAccess["earth_engine_access()"]
    end

    subgraph Physical_Storage_Assets ["Physical Storage Files"]
        SynthFixture["data/synthetic_fixtures/kariba_synthetic_benchmark.json\n(Labeled SIMULATED DATA)"]
        RealCache["data/processed/stac_cache/kariba-redd__*.json\n(Real Sentinel-2 2021–2023 Cache)"]
        ClimCache["data/processed/climate_cache/kariba_chirps_climate.json\n(Real 43-Year CHIRPS Rainfall Cache)"]
        Quarantined["data/processed/_quarantine_task5b_fabricated/\n(Quarantined Fabricated Landsat Cache - Not Read)"]
    end

    UI & Doctor --> API
    API --> Router
    Router -- True --> SynthAccess --> SynthFixture
    Router -- False --> EEAccess
    EEAccess -- Causal Readiness Check Fails --> Fail501["Raise DataUnavailableError\nReturn HTTP 501 Not Implemented\nStatus: INCONCLUSIVE (Not Estimable)"]
    EEAccess -. Future Materialized Path .-> RealCache & ClimCache
```

![Auditor Dashboard](../product/screens/auditor-dashboard.png)

![Kariba Project Overview](../product/screens/kariba-overview.png)

---

## 6. Current Scientific Verdict & Remediation Roadmap

1. **Current Causal Verdict**: **`INCONCLUSIVE / NOT ESTIMABLE`**.
   - GroundTruth refuses to manufacture a causal additionality claim for Kariba REDD+ from real data because genuine, multi-tile pre-treatment Landsat surface reflectance rasters have not been reduced into an outcome panel.
2. **Fail-Closed Principle Preserved**: In `REAL_OBSERVATIONS` mode, the system halts with HTTP 501 rather than serving simulated numbers or unmaterialized caches.
3. **Remediation Roadmap**:
   - Execute cloud-native multi-tile extraction across WRS-2 paths 169–172 via Microsoft Planetary Computer STAC.
   - Apply bit-level QA masking and dry-season compositing across all 22 years for Kariba and the 28 core donor districts.
   - Empirically validate Roy et al. (2016) surface reflectance harmonization across concurrent 2013 overpasses in the Zambezi Basin.
   - Advance from Level 2 (Contextual Intelligence) to Level 3 (Counterfactual Econometrics).
