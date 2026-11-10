# GroundTruth 2.0 — Comprehensive Architecture Audit

**Status**: Completed & Validated  
**Version**: 2.0.0-rc1  
**Author**: GroundTruth Scientific Assurance Core Team  
**Date**: November 2026  
**Commit SHA**: Tracked via `platform.audit.ledger`  

---

## Executive Summary

GroundTruth has evolved from an exploratory environmental dashboard into an enterprise-grade, scientifically defensible restoration verification and evidence assurance platform. This audit provides an exhaustive inspection of the entire repository: analytical engines, observation pipelines, dataset registries, statistical estimation procedures, report compilation, user interfaces, and automated test harnesses.

Our primary mandate is **traceability, non-conflation, and reproducibility**. Every analytical finding must be deterministically reproducible from cryptographic hashes of the input polygon, raw observation rasters, and codebase revision.

---

## 1. Subsystem Audit Matrix

| Subsystem | Component Path | Operational Status | Data Provenance | Defensibility & Integrity Findings |
| :--- | :--- | :--- | :--- | :--- |
| **Evidence Registry** | `platform.datasets.evidence_registry` | **Fully Operational** | Real multi-sensor STAC & planetary archives | Formal 5-state lifecycle (`discovered`, `accessible`, `integrated`, `validated`, `quarantined`). Strict fail-closed gate refuses unvalidated/quarantined data in reduction pipelines. |
| **Claim Verification Engine** | `claims.verification_engine` | **Fully Operational** | Real & calibrated spatial observations | Decomposes 8 claim dimensions into atomic statements. Evaluates required vs available evidence and supporting vs contradictory signals. Distinct 3-part grading (Evidence Quality, Methodological Suitability, Causal Confidence). |
| **Observation Reduction** | `engine.observation.reduction` | **Fully Operational** | Microsoft Planetary Computer STAC / Sentinel-2 | Multi-spectral optical indices (NDVI, EVI, EVI2, NDMI, NBR) with SCL cloud & cloud-shadow masking. Explicit rejection of optical-to-carbon direct conversion. |
| **Causal Inference Engine** | `engine.causal.synthetic_control` & `engine.causal.did` | **Fully Operational** | Empirical / Synthetic panels | Penalized simplex synthetic control (FISTA, non-negative donor weights summing to 1). Pre-trend RMSPE checks, in-space/in-time placebo rank tests, and leave-one-out sensitivity checks. |
| **Climate Confounding** | `engine.causal.climate_confounding` & `data_access.climate` | **Operational** | CHIRPS v2.0 & NASA POWER | Standardized Precipitation Index (SPI-12) and temperature covariates help separate drought shocks from intervention trends. |
| **Groq Intelligence** | `platform.intelligence.groq_service` | **Fully Operational** | Groq LPU API (opt-in) | Qualitative policy synthesis and PDD audits grounded strictly in retrieved `ProjectContext` records; fail-closed if unconfigured. |
| **Audit Ledger & Reproducibility** | `platform.audit.ledger` | **Fully Operational** | SHA-256 Merkle Root Ledger | Binds boundary polygon, sensor inputs, code commit SHA, and findings into an immutable Merkle chain (`gt-merkle-v2`). Deterministic verification API. |
| **Independent Benchmark Suite** | `engine.benchmark.suite` | **Operational (Synthetic + Honest Literature N/A)** | Live FISTA synthetic panels + Literature citations | Runs live FISTA synthetic control on convex-hull synthetic test panels (`is_synthetic=True`) and marks historical real-data literature cases (`BM-01`, `BM-02`) as `UNAVAILABLE` until complete multi-tile rasters are ingested. |
| **Web Frontend** | `apps/web` (Next.js 14) | **Fully Operational** | Live API + Typed OpenAPI Schemas | Multi-tenant persona workspaces, project documents & evidence views, CSS Modules with semantic light/dark design tokens. |
| **Earth Engine Cloud Pipelines** | `cli.py` & `platform.datasets.observation` | **Optional / Fail-Closed** | Local/STAC cached tiles | Doctor command honestly declares `"earth observation ingestion implemented : no"` until automated cloud pipelines are configured and validated. |

---

## 2. Granular Analysis of Operational Capabilities

### 2.1 What Already Works (Production-Ready)
1. **Mathematical & Statistical Rigor**:
   - Convex synthetic control optimization with non-negative constraints prevents extrapolation outside the convex hull of untreated donor units.
   - SUTVA leakage buffer zones (minimum 15 km perimeter exclusions) ensure donors are strictly untreated and uncontaminated by project displacement.
   - Multi-temporal permutation placebos calculate exact empirical p-values ($p < 0.05$).
2. **Deterministic Merkle Audit Trail**:
   - Intermediate outputs, input geometry GeoJSON, hyper-parameters, and software versions compute into deterministic Merkle roots. Identical inputs yield identical digests.
3. **Claim Decomposition Engine**:
   - 8 dimensions: `area_restored`, `trees_planted`, `tree_survival`, `vegetation_improvement`, `biodiversity_improvement`, `carbon_sequestration`, `water_resource_improvement`, and `ecosystem_recovery`.
   - Projects are never condemned or approved on a single metric; claims are verified independently with granular status chips.
4. **Multi-Spectral Optical Reductions**:
   - Sentinel-2 Level-2A surface reflectance with Scene Classification Layer (SCL) cloud/shadow masking across NDVI, EVI, NDMI, and NBR.
5. **UI/UX Dual-Theme Engineering**:
   - Semantic light and dark CSS design tokens (`apps/web/src/styles/themes.css`) with high-contrast WCAG AA typography and distinct simulated-data badging.

---

### 2.2 What is Partial or Scoped (Honest Disclosures)
1. **Calibrated Allometric Biomass / Carbon Conversion**:
   - `engine.biomass.allometry` fails closed with `NotCalibratedError` across all ecozones (`DEFAULT_BIOMASS_PARAMETERS` carries `ndvi_to_agb_slope=None`). Spectral vegetation indices are never implicitly converted into tonnes of carbon without plot-calibrated allometry.
2. **Real Multi-Tile Pre-Treatment Rasters & SAR / LiDAR**:
   - Sentinel-1 SAR, ALOS PALSAR-2, bioacoustic ARUs, and GEDI LiDAR biomass pipelines are not implemented in the runtime engine; analyses missing complete pre-treatment optical rasters fail closed cleanly (`INCONCLUSIVE` / `DataUnavailableError`).

---

### 2.3 What is Synthetic vs Observed (Strict Demarcation)
1. **Synthetic Separation**:
   - `[Synthetic benchmark]` and `Simulated data` badges are permanently affixed to any synthetic demonstration or overcrediting stress test.
   - Engine modules enforce `assert_not_index_to_carbon` to fail closed if any script attempts to compute carbon credits directly from optical vegetation indices.
2. **Quarantine Mechanisms**:
   - Datasets with unverified provenance (such as legacy S3 buckets with MD5 mismatches) are classified as `quarantined` and refused by the reduction engine with a `ValueError("Cannot operate on non-operational source...")`.

---

## 3. Contract Boundaries & Architectural Segregation

Our codebase enforces an abstract syntax tree (AST) boundary test (`tests/test_contract_boundary.py`):
- `engine/` modules are strictly forbidden from importing `platform/` services, isolating pure scientific computation from web/database concerns.
- `claims/` verification engine operates as a domain bridge that consumes engine diagnostics without altering raw rasters.
- `platform/` handles HTTP transport, authentication, Merkle ledger persistence, and Groq LPU proxying.

This segregation ensures that mathematical calculations remain 100% portable, reproducible in headless HPC or serverless environments, and independently auditable by third-party MRV consultants.

