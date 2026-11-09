# Earth Observation Architecture

**Engine**: `packages/groundtruth/src/groundtruth/engine/observation/`  
**Data Access**: `packages/groundtruth/src/groundtruth/data_access/`  
**Supported Sensors**: Sentinel-2 MSI, Landsat 9 OLI-2, Landsat 8 OLI, Landsat 7 ETM+, Landsat 5 TM, CHIRPS Precipitation, NASA POWER Climate.

The Earth Observation (EO) subsystem transforms petabytes of multi-spectral satellite rasters into clean, cloud-screened, and sensor-harmonized zonal indicator time series.

```mermaid
flowchart TD
    subgraph UpstreamArchives["1. Upstream STAC Providers"]
        S2["Sentinel-2 Level-2A<br/>(COPERNICUS/S2_SR_HARMONIZED)"]
        L89["Landsat 8/9 C2 L2<br/>(LANDSAT/LC08-LC09/C02/T1_L2)"]
        L57["Landsat 5/7 C2 L2<br/>(LANDSAT/LT05-LE07/C02/T1_L2)"]
        CHIRPS["CHIRPS 0.05° Gridded Rainfall<br/>(UCSB Climate Hazards Group)"]
        POWER["NASA POWER Gridded Meteorology<br/>(0.5° × 0.625° Reanalysis)"]
    end

    subgraph CalibrationMasking["2. Calibration & Pixel Masking"]
        ScaleDN["Reflectance Scaling<br/>• Landsat: DN × 0.0000275 - 0.2<br/>• Sentinel-2: DN / 10000"]
        BitMask["QA Pixel & Cloud Masking<br/>• S2: SCL drop cloud, shadow, snow<br/>• Landsat: QA_PIXEL bits 1, 3, 4<br/>• QA_RADSAT saturation filter"]
    end

    subgraph IndexCalculation["3. Multi-Spectral Index Computation"]
        NDVI["NDVI: (NIR - Red) / (NIR + Red)"]
        EVI["EVI: 2.5 × (NIR - Red) / (NIR + 6Red - 7.5Blue + 1)"]
        NDMI["NDMI: (NIR - SWIR1) / (NIR + SWIR1)"]
        NBR["NBR: (NIR - SWIR2) / (NIR + SWIR2)"]
    end

    subgraph TemporalCompositing["4. Temporal Compositing & Reduction"]
        MedianComp["Per-Pixel Annual Median<br/>(Rejects residual cloud & shadow outliers)"]
        ZonalMean["Zonal Mean Aggregation<br/>(Mean over valid AOI polygon pixels)"]
        AuditMetrics["Coverage Auditing<br/>• Clear-pixel fraction (clear_frac)<br/>• Valid pixel count (n_valid)"]
    end

    subgraph SensorHarmonization["5. Sensor Cross-Calibration"]
        RoyCalibration["Roy et al. (2016) Harmonization<br/>(ETM+ to OLI surface reflectance mapping)"]
        UncertaintyPropagation["Calibration Error Budget Tracking"]
    end

    subgraph EmittedSeries["6. Emitted Analytical TimeSeries"]
        VerifiedSeries["TimeSeries Object<br/>• Explicit EvidenceState: DERIVED<br/>• Complete SHA-256 Provenance<br/>• Invariant: NDVI is NOT Carbon"]
    end

    S2 --> ScaleDN
    L89 --> ScaleDN
    L57 --> ScaleDN
    ScaleDN --> BitMask
    BitMask --> NDVI & EVI & NDMI & NBR
    NDVI & EVI & NDMI & NBR --> MedianComp
    MedianComp --> ZonalMean
    ZonalMean --> AuditMetrics
    AuditMetrics --> RoyCalibration
    RoyCalibration --> UncertaintyPropagation
    UncertaintyPropagation --> VerifiedSeries
    CHIRPS & POWER --> VerifiedSeries
```

![Kariba Overview](../product/screens/kariba-overview.png)

---

## 1. The Seam: Methodology vs. Plumbing

To preserve scientific reproducibility, Earth Observation code is cleanly bisected:

```
ENGINE (Methodology)              │  PLATFORM (Plumbing)
──────────────────────────────────┼──────────────────────────────────
Which index answers the research  │  STAC catalog endpoint discovery
  hypothesis                      │  Authentication & API key storage
Pixel masking logic & thresholds  │  Network retries & rate limits
Reflectance scale factors         │  Tiered blob storage & disk cache
Compositing mathematical rules    │  OpenTelemetry span recording
Refusal thresholds for coverage   │  Job queue scheduling
```

The interface protocol is declared in `groundtruth.contracts.ports.ObservationAccess`:

```python
class ObservationAccess(Protocol):
    def series(self, spec: ObservationSpec) -> TimeSeries: ...
    def dataset(self, indicator: Indicator) -> DatasetRef: ...
    def provenance(self, spec: ObservationSpec) -> Provenance: ...
```

---

## 2. Sensor Timeline & Multi-Decadal Historical Coverage

Long-term additionality baselines require multi-decadal time series spanning distinct satellite eras:

```mermaid
gantt
    title Earth Observation Sensor Lifespans
    dateFormat YYYY
    axisFormat %Y
    
    section Landsat Era
    Landsat 5 TM :1984, 2011
    Landsat 7 ETM+ (Full) :1999, 2003
    Landsat 7 ETM+ (SLC-Off) :2003, 2022
    Landsat 8 OLI :2013, 2026
    Landsat 9 OLI-2 :2022, 2026

    section Sentinel Era
    Sentinel-2A/B MSI :2017, 2026

    section Climate Grids
    CHIRPS Precipitation :1981, 2026
    NASA POWER Temperature :1981, 2026
```

### 2.1 Sensor-Specific Band Designations

| Satellite Platform | Red Band | NIR Band | SWIR1 Band | SWIR2 Band (NBR) |
| :--- | :--- | :--- | :--- | :--- |
| **Sentinel-2 MSI** | B4 (665 nm) | B8 (842 nm) | B11 (1610 nm) | B12 (2190 nm) |
| **Landsat 8/9 OLI** | SR_B4 (655 nm)| SR_B5 (865 nm)| SR_B6 (1610 nm)| SR_B7 (2200 nm) |
| **Landsat 7 ETM+** | SR_B3 (660 nm)| SR_B4 (830 nm)| SR_B5 (1650 nm)| SR_B7 (2220 nm) |
| **Landsat 5 TM** | SR_B3 (660 nm)| SR_B4 (830 nm)| SR_B5 (1650 nm)| SR_B7 (2220 nm) |

---

## 3. Pixel QA Masking & Annual Median Compositing

Tropical and subtropical savanna ecosystems experience intense seasonal cloud contamination during monsoonal wet seasons. GroundTruth 2.0 applies strict, per-pixel masking:

```mermaid
stateDiagram-v2
    [*] --> IngestScene: Level-2 Surface Reflectance Scene
    
    IngestScene --> CheckSCL: Sensor is Sentinel-2?
    CheckSCL --> MaskS2: Evaluate Scene Classification Layer (SCL)
    MaskS2 --> ValidS2: SCL in (4: Vegetation, 5: Bare Soil, 6: Water)
    MaskS2 --> DropPixel: SCL in (1: Saturation, 3: Cloud Shadow, 8: Cloud Med, 9: Cloud High, 10: Cirrus)

    IngestScene --> CheckQA: Sensor is Landsat Collection 2?
    CheckQA --> MaskLandsat: Evaluate QA_PIXEL Bitmask
    MaskLandsat --> ValidLandsat: Bits 1 (Dilated Cloud), 3 (Cloud), 4 (Cloud Shadow) == 0 AND<br/>QA_RADSAT == 0 (No Band Saturation)
    MaskLandsat --> DropPixel: Cloud or Shadow Bit Set

    ValidS2 --> ComputeIndex: Calculate NDVI / EVI / NDMI / NBR
    ValidLandsat --> ComputeIndex
    
    ComputeIndex --> AnnualStack: Append to Calendar Year Clear-Scene Stack
    AnnualStack --> MedianComposite: Compute Per-Pixel Median across Year
    DropPixel --> Discard: Omit from Annual Composite
```

### 3.1 Why Annual Median Rejects Cloud Contamination
Residual, sub-pixel clouds that escape the QA bitmask create heavy, positive-reflectance outliers in the visible spectrum. Computing a mean absorbs these outliers and creates artificial "greening" artifacts. The per-pixel median unconditionally rejects outliers, providing an empirically robust measure of annual peak biomass.

---

## 4. Sensor Cross-Calibration: Roy et al. (2016)

The transition between Landsat 7 ETM+ and Landsat 8 OLI coincides with critical baseline periods for major REDD+ interventions (e.g., Kariba REDD+ VCS 902 intervention boundary in 2011/2012). Because OLI spectral response functions are narrower than ETM+, raw unharmonized indices introduce artificial step changes.

GroundTruth 2.0 implements sensor transformation functions following Roy et al. (2016):

$$\rho_{\text{OLI}} = \text{slope} \times \rho_{\text{ETM+}} + \text{intercept}$$

> [!CAUTION]
> **Independent Audit Insight (Task 5/5B)**:
> GroundTruth 2.0 enforces that harmonization coefficients must be specifically applied to surface reflectance (Collection 2 Level-2) rather than top-of-atmosphere (TOA) reflectance. Furthermore, concurrent overpass empirical cross-calibration must be verified against actual overlapping scenes over the project biome rather than synthesized mathematical series. In the absence of validated overlapping scenes, the system explicitly propagates sensor harmonization uncertainty into the final error budget.

---

## 5. Non-Negotiable Principle: NDVI is NOT Carbon

Under no circumstances does GroundTruth 2.0 convert a spectral vegetation index (NDVI, EVI, NDMI, NBR) into metric tonnes of carbon dioxide equivalent ($\text{tCO}_2\text{e}$) without an empirical, peer-reviewed allometric biomass equation.

This invariant is programmatically enforced in `groundtruth.contracts.units`:
- Any comparison between an index (dimensionless, $[-1.0, +1.0]$) and a carbon credit claim ($\text{tCO}_2\text{e}$) triggers a typed `IncompatibleUnitsError`.
- Spectral indices represent **photosynthetic canopy greenness and water absorption**, not timber volume or underground carbon storage.
