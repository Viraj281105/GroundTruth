# GroundTruth 2.0 — Evidence Registry & Provenance Architecture

**Specification**: Version 2.0  
**Status**: Implemented (`platform.datasets.evidence_registry`)  
**Scope**: All Remote Sensing, Vector, Climate, LiDAR, and In-Situ Observations  

---

## 1. Architectural Philosophy: Provable Scientific Provenance

Environmental intelligence platforms must never rely on untracked, unversioned, or ambient data. GroundTruth 2.0 treats every data source as a first-class evidence entity with an explicit lifecycle, cryptographic digest, and legally binding license statement.

### The Non-Conflation Principle
A catalogue entry is **never** represented as an operational integration. GroundTruth maintains a strict distinction between data sources that have merely been discovered versus those that are validated and operational in production reduction pipelines.

---

## 2. Source Lifecycle State Machine

```
   [ DISCOVERED ]  ──>  [ ACCESSIBLE ]  ──>  [ INTEGRATED ]  ──>  [ VALIDATED ]
         │                     │                    │                   │
         └─────────────────────┴────────────────────┴───────────────────┘
                                       │
                                       ▼ (Checksum mismatch / corruption)
                                [ QUARANTINED ]
                                  (FAILS CLOSED)
```

| Lifecycle State | Definition | Operational Permissibility |
| :--- | :--- | :--- |
| **`discovered`** | Identified in an external data catalogue (e.g., UNEP-WCMC, GEOSS). Metadata catalogued, but no direct API pipeline or ingestion adapter implemented. | **Non-operational**. Refused by analytical pipelines. Visible in Evidence Library for discovery only. |
| **`accessible`** | Authentication credentials configured; direct API or bucket access verified. Ingestion adapter prototyped. | **Pre-production only**. Available for sandbox exploration; refused in audit-grade runs. |
| **`integrated`** | Automated programmatic ingestion active (STAC API, cloud-native COG/Zarr readers). Ingestion pipeline tested. | **Operational for exploratory MRV**. |
| **`validated`** | Cryptographic SHA-256 verification complete. Atmospheric correction, sensor calibration, and ground-truth cross-checks certified. | **Fully Operational**. Authorized for certified audit reports, CSR due diligence, and CAR issuance. |
| **`quarantined`** | Detected checksum mismatch, undocumented sensor drift, corrupt tiles, or revoked license. | **STRICTLY REFUSED (Fails Closed)**. Instantly raises `ValueError` if invoked by any analytical estimator. |

---

## 3. Mandatory Metadata Schema for Evidence Sources

Every registered source implements the following canonical metadata fields:

```python
class EvidenceSource(BaseModel):
    source_id: str                      # Unique kebab-case identifier (e.g. 'sentinel2-l2a-planetary-computer')
    name: str                           # Formal scientific dataset name
    provider: str                       # Institutional publisher (e.g. 'ESA Copernicus / Microsoft')
    original_url: str                   # Upstream permanent canonical URL
    dataset_identifier: str             # Upstream DOI or catalog ID
    version: str                        # Dataset release version
    license: str                        # Standard license identifier (e.g. 'CC-BY-4.0', 'Public Domain')
    permitted_usage: str                # Commercial, academic, or MRV usage constraints
    spatial_coverage: str               # Geographic bounding or coverage description
    temporal_coverage: str              # Earliest to latest observation window
    resolution: str                     # Spatial and spectral resolution
    acquisition_date: str               # Temporal revisit frequency or epoch
    retrieval_timestamp: str            # ISO-8601 UTC timestamp of retrieval
    processing_history: List[str]       # Ordered list of transformations and calibrations
    data_quality: str                   # Scientific quality and accuracy benchmarks
    completeness_pct: float             # Spatial/temporal completeness (0.0 to 100.0)
    content_sha256: str                 # Cryptographic SHA-256 digest of catalog/data bundle
    lifecycle: SourceLifecycle          # discovered | accessible | integrated | validated | quarantined
    modality: ModalityType              # optical | radar | lidar | climate | vector | in_situ | multimodal
```

---

## 4. Operational Ingestion & Fail-Closed Gateways

The `EvidenceRegistry.assert_operational(source_id)` method enforces our fail-closed architectural boundary:

```python
def assert_operational(self, source_id: str) -> EvidenceSource:
    source = self.get_source(source_id)
    if source.lifecycle not in (SourceLifecycle.INTEGRATED, SourceLifecycle.VALIDATED):
        raise ValueError(
            f"Evidence source '{source_id}' is in lifecycle state '{source.lifecycle.value}'. "
            f"Only 'integrated' or 'validated' sources may enter analytical pipelines. "
            f"GroundTruth refuses to process non-operational or quarantined data."
        )
    return source
```

---

## 5. Standard Registered Sources in GroundTruth 2.0

1. **`sentinel2-l2a-planetary-computer`** (`validated`):
   - 10m/20m multi-spectral bottom-of-atmosphere surface reflectance with SCL masking.
2. **`chirps-v2-rainfall`** (`validated`):
   - 0.05° daily quasi-global precipitation record spanning 1981-present for SPI-12 drought controls.
3. **`nasa-power-agroclimatology`** (`validated`):
   - 0.5° global solar radiation, temperature, and vapor pressure deficit for climate covariate balancing.
4. **`geoboundaries-global-admin`** (`validated`):
   - Level 0, 1, and 2 administrative topological boundary vectors (WGS84 EPSG:4326).
5. **`gedi-l4a-footprint-biomass`** (`integrated`):
   - 25m spaceborne LiDAR waveform relative height and aboveground biomass density.
6. **`jaxa-alos-palsar2-fnf`** (`accessible`):
   - 25m L-band SAR backscatter mosaics for all-weather understory canopy structure.
7. **`global-mangrove-watch-v3`** (`discovered`):
   - 25m coastal mangrove canopy extent catalogue.
8. **`quarantined-legacy-landsat-cache`** (`quarantined`):
   - Unverified S3 bucket mirror with MD5 checksum mismatch, isolated and blocked from execution.

