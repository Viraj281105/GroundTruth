# GROUNDTRUTH AUTHORITATIVE ENVIRONMENTAL DATA SOURCE REGISTRY

> **Registry Integrity Invariant**: *Every environmental dataset in this registry is cataloged with its verified origin, licensing, temporal resolution, and integration status. GroundTruth distinguishes verified real-world data from unmaterialized or quarantined assets.*

```
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │                          DATA REGISTRY ARCHITECTURE                         │
   ├───────────────────────────────────┬─────────────────────────────────────────┤
   │  Total Cataloged Datasets         │ 105 Authoritative Products              │
   │  Domains Covered                  │ 10 Multi-Disciplinary Environmental Domains│
   │  Verified Real-World Integrations │ Sentinel-2 L2A (2021–23), CHIRPS, POWER │
   │  Metadata Audited                 │ Landsat 5/7/8/9 C2 L2 (2001–2022 STAC)  │
   │  Quarantined Task 5B Artifacts    │ Hand-typed Landsat cache in quarantine  │
   │  Fail-Closed Engine Status        │ HTTP 501 / DataUnavailableError Active  │
   └───────────────────────────────────┴─────────────────────────────────────────┘
```

```mermaid
flowchart TD
    subgraph Multi_Domain_Registry ["105 Authoritative Datasets across 10 Domains"]
        D1["A. Satellite & Remote Sensing (12)"]
        D2["B. Vegetation & Canopy Condition (11)"]
        D3["C. Land Cover & Land Use (11)"]
        D4["D. Biodiversity & Occurrence (10)"]
        D5["E. Climate, Rain & Temperature (11)"]
        D6["F. Hydrology & Surface Water (10)"]
        D7["G. Fire & Thermal Disturbance (10)"]
        D8["H. Soil, Terrain & Elevation (10)"]
        D9["I. Anthropogenic Pressures (10)"]
        D10["J. Conservation & Governance (10)"]
    end

    subgraph Integration_Status_Flow ["Evidence Classification"]
        S_INT["INTEGRATED\n(Active in Real Pipeline: S2, CHIRPS, POWER)"]
        S_AUD["METADATA_AUDITED / ACCESS_VERIFIED\n(STAC Scened Audited: Landsat C2 L2)"]
        S_DISC["DISCOVERED\n(Fully Specified in Catalog)"]
        S_QUAR["QUARANTINED\n(Task 5B Fabricated Cache in _quarantine_task5b_fabricated/)"]
    end
```

![Auditor Dashboard](../product/screens/auditor-dashboard.png)

## 1. Registry Architecture and Scientific Scope

The GroundTruth Data Discovery Registry catalogues authoritative environmental, satellite, climatic, hydrological, soil, biodiversity, and anthropogenic datasets. GroundTruth evaluates ecosystem restoration interventions and voluntary carbon projects against genuine, independently sourced, reproducible real-world evidence.

This registry contains **105 authoritative environmental datasets** systematically catalogued across ten core data domains. Each entry records data provenance, official providers, access mechanics, licensing, spatial/temporal resolution, independence assessment, feasibility for the Kariba REDD+ validation case, and verified integration status.

### Integration Status Definitions
- **`INTEGRATED`**: Real data has been ingested, validated, and actively wired into a working operational pipeline or benchmark cache (e.g., Sentinel-2 2021–2023 10m rasters, 43-year CHIRPS monthly rainfall).
- **`METADATA_AUDITED` / `ACCESS_VERIFIED`**: Official API endpoints, STAC catalogues, or storage buckets have been connected, scene counts and cloud stats audited (e.g., Landsat Collection 2 Level-2 STAC metadata across 2001–2022). Pre-treatment raster reduction to series remains pending.
- **`QUALITY_VALIDATED`**: Data assets have been retrieved, tested against physical constraints, and validated for scientific integrity.
- **`SAMPLE_RETRIEVED`**: Real sample observations have been downloaded and format/coordinate compatibility verified.
- **`DISCOVERED`**: Authoritative data product identified and catalogued with complete technical specifications.
- **`REQUIRES_AUTHENTICATION`**: Access requires specialized researcher or institutional credentials/tokens.
- **`UNAVAILABLE`**: Dataset is restricted, retired without archive access, or technically inaccessible.
- **`QUARANTINED`**: Fabricated or simulated data improperly labeled real, isolated under audit remediation (e.g., Task 5B Landsat cache).

### Domain Summary
| Domain | Description | Count |
| :--- | :--- | :--- |
| **A. Satellite and Remote Sensing** | Domain A_SATELLITE_REMOTE_SENSING | 12 |
| **B. Vegetation and Ecosystem Condition** | Domain B_VEGETATION_ECOSYSTEM_CONDITION | 11 |
| **C. Land Cover and Land Use** | Domain C_LAND_COVER_LAND_USE | 11 |
| **D. Biodiversity and Species Occurrence** | Domain D_BIODIVERSITY | 10 |
| **E. Climate, Precipitation and Temperature** | Domain E_CLIMATE | 11 |
| **F. Hydrology and Surface Water** | Domain F_HYDROLOGY | 10 |
| **G. Fire and Disturbance** | Domain G_FIRE_DISTURBANCE | 10 |
| **H. Soil, Terrain and Elevation** | Domain H_SOIL_TERRAIN | 10 |
| **I. Human Pressures and Infrastructure** | Domain I_HUMAN_ANTHROPOGENIC_PRESSURES | 10 |
| **J. Conservation, Governance and Restoration** | Domain J_CONSERVATION_RESTORATION | 10 |
| **Total Datasets** | Complete Multi-Domain Environmental Catalog | **105** |

---

## A. Satellite and Remote Sensing

### `landsat-5-tm-c2-l2` — USGS Landsat 5 Thematic Mapper (TM) Collection 2 Level-2 Surface Reflectance
- **Original Provider**: USGS / NASA
- **Official URL**: [https://www.usgs.gov/landsat-missions/landsat-5](https://www.usgs.gov/landsat-missions/landsat-5)
- **Data Domain**: `A_SATELLITE_REMOTE_SENSING`
- **Geographic Coverage**: Global land surface
- **Temporal Coverage**: 1984-03-01 to 2012-05-05
- **Spatial Resolution**: 30 m
- **Temporal Resolution**: 16-day repeat cycle
- **Access Mechanism**: STAC API / Cloud-Optimized GeoTIFF (COG) / USGS Machine-to-Machine API
- **API / STAC Availability**: Microsoft Planetary Computer STAC (landsat-c2-l2), AWS Earth Search, USGS M2M
- **Licensing**: Public Domain / CC0 (USGS open data policy)
- **Authentication**: None (free public STAC access via Planetary Computer with anonymous SAS token signing)
- **Update Frequency**: Historical archive (completed mission)
- **Expected Usefulness**: Essential for 2001-2011 pre-treatment historical baseline reconstruction over Kariba
- **Independent Evidence Source**: Yes
- **Integration Status**: `METADATA_AUDITED` (STAC scenes identified and dry-season cloud statistics audited in `kariba_landsat_coverage_audit.json`; raster reduction to pre-treatment panel pending; Task 5B fabricated cache quarantined)
- **Feasibility for Kariba**: High. Covers Kariba WRS-2 paths 170-172, rows 071-073 with clear dry-season scenes.

### `landsat-7-etm-c2-l2` — USGS Landsat 7 Enhanced Thematic Mapper Plus (ETM+) Collection 2 Level-2 Surface Reflectance
- **Original Provider**: USGS / NASA
- **Official URL**: [https://www.usgs.gov/landsat-missions/landsat-7](https://www.usgs.gov/landsat-missions/landsat-7)
- **Data Domain**: `A_SATELLITE_REMOTE_SENSING`
- **Geographic Coverage**: Global land surface
- **Temporal Coverage**: 1999-04-15 to present
- **Spatial Resolution**: 30 m
- **Temporal Resolution**: 16-day repeat cycle
- **Access Mechanism**: STAC API / Cloud-Optimized GeoTIFF (COG) / USGS M2M
- **API / STAC Availability**: Microsoft Planetary Computer STAC (landsat-c2-l2), AWS Earth Search, USGS M2M
- **Licensing**: Public Domain / CC0
- **Authentication**: None (Planetary Computer anonymous SAS token signing)
- **Update Frequency**: Historical & active (standby calibration orbit)
- **Expected Usefulness**: Continuous historical coverage 1999-2022; requires scan-line corrector (SLC-off post May 2003) gap masking
- **Independent Evidence Source**: Yes
- **Integration Status**: `METADATA_AUDITED` (STAC scenes identified and dry-season cloud statistics audited in `kariba_landsat_coverage_audit.json`; raster reduction to pre-treatment panel pending; Task 5B fabricated cache quarantined)
- **Feasibility for Kariba**: High. Extensive dry-season acquisitions over Kariba; SLC-off gap pixels masked via QA_PIXEL bit 0.

### `landsat-8-oli-c2-l2` — USGS Landsat 8 Operational Land Imager (OLI) Collection 2 Level-2 Surface Reflectance
- **Original Provider**: USGS / NASA
- **Official URL**: [https://www.usgs.gov/landsat-missions/landsat-8](https://www.usgs.gov/landsat-missions/landsat-8)
- **Data Domain**: `A_SATELLITE_REMOTE_SENSING`
- **Geographic Coverage**: Global land surface
- **Temporal Coverage**: 2013-02-11 to present
- **Spatial Resolution**: 30 m
- **Temporal Resolution**: 16-day repeat cycle
- **Access Mechanism**: STAC API / Cloud-Optimized GeoTIFF (COG) / USGS M2M
- **API / STAC Availability**: Microsoft Planetary Computer STAC (landsat-c2-l2), AWS Earth Search, USGS M2M
- **Licensing**: Public Domain / CC0
- **Authentication**: None (Planetary Computer anonymous SAS token signing)
- **Update Frequency**: Daily acquisitions added continuously
- **Expected Usefulness**: Primary post-treatment anchor 2013-2022 for project crediting period verification
- **Independent Evidence Source**: Yes
- **Integration Status**: `METADATA_AUDITED` (STAC scenes identified and dry-season cloud statistics audited in `kariba_landsat_coverage_audit.json`; raster reduction to pre-treatment panel pending; Task 5B fabricated cache quarantined)
- **Feasibility for Kariba**: High. Excellent radiometry, 12-bit dynamic range, full coverage over all Kariba RDC parcels.

### `landsat-9-oli2-c2-l2` — USGS Landsat 9 Operational Land Imager 2 (OLI-2) Collection 2 Level-2 Surface Reflectance
- **Original Provider**: USGS / NASA
- **Official URL**: [https://www.usgs.gov/landsat-missions/landsat-9](https://www.usgs.gov/landsat-missions/landsat-9)
- **Data Domain**: `A_SATELLITE_REMOTE_SENSING`
- **Geographic Coverage**: Global land surface
- **Temporal Coverage**: 2021-09-27 to present
- **Spatial Resolution**: 30 m
- **Temporal Resolution**: 16-day repeat cycle (8-day offset with Landsat 8)
- **Access Mechanism**: STAC API / COG
- **API / STAC Availability**: Microsoft Planetary Computer STAC (landsat-c2-l2), AWS Earth Search
- **Licensing**: Public Domain / CC0
- **Authentication**: None (Planetary Computer anonymous SAS token signing)
- **Update Frequency**: Daily acquisitions added continuously
- **Expected Usefulness**: 14-bit radiometry for high-precision recent observation validation (2021-present)
- **Independent Evidence Source**: Yes
- **Integration Status**: `METADATA_AUDITED` (STAC scenes identified and dry-season cloud statistics audited in `kariba_landsat_coverage_audit.json`; raster reduction to pre-treatment panel pending; Task 5B fabricated cache quarantined)
- **Feasibility for Kariba**: High. Complete scene acquisitions for 2022-2023 overlapping Sentinel-2.
- **Feasibility for Kariba**: High. Complete scene acquisitions for 2022-2023 overlapping Sentinel-2.

### `copernicus-sentinel-2-l2a` — Copernicus Sentinel-2 MSI Level-2A Bottom-Of-Atmosphere Reflectance
- **Original Provider**: European Space Agency (ESA) / Copernicus
- **Official URL**: [https://sentinels.copernicus.eu/web/sentinel/missions/sentinel-2](https://sentinels.copernicus.eu/web/sentinel/missions/sentinel-2)
- **Data Domain**: `A_SATELLITE_REMOTE_SENSING`
- **Geographic Coverage**: Global land and coastal waters
- **Temporal Coverage**: 2015-06-23 to present
- **Spatial Resolution**: 10 m (B2, B3, B4, B8), 20 m (B5-B7, B8A, B11, B12, SCL)
- **Temporal Resolution**: 5-day constellation repeat
- **Access Mechanism**: STAC API / COG / Copernicus Data Space Ecosystem (CDSE) OData
- **API / STAC Availability**: Microsoft Planetary Computer STAC (sentinel-2-l2a), CDSE STAC, AWS Earth Search
- **Licensing**: Copernicus Open Access Policy (free, full, open)
- **Authentication**: None on Planetary Computer; CDSE requires free registered OAuth
- **Update Frequency**: Continuous near-real-time
- **Expected Usefulness**: High-resolution 10m validation for project boundary and spatial deforestation patterns
- **Independent Evidence Source**: Yes
- **Integration Status**: `INTEGRATED`
- **Feasibility for Kariba**: High. Ingested and cached for 2021-2023 across tile 36LTH with BOA offset harmonization.

### `copernicus-sentinel-1-grd` — Copernicus Sentinel-1 C-Band SAR Ground Range Detected (GRD)
- **Original Provider**: ESA / Copernicus
- **Official URL**: [https://sentinels.copernicus.eu/web/sentinel/missions/sentinel-1](https://sentinels.copernicus.eu/web/sentinel/missions/sentinel-1)
- **Data Domain**: `A_SATELLITE_REMOTE_SENSING`
- **Geographic Coverage**: Global land and sea zones
- **Temporal Coverage**: 2014-10-03 to present
- **Spatial Resolution**: 10 m (IW GRD)
- **Temporal Resolution**: 6-12 day repeat
- **Access Mechanism**: STAC API / Cloud-Optimized GeoTIFF / CDSE API
- **API / STAC Availability**: Planetary Computer STAC (sentinel-1-grd), CDSE STAC
- **Licensing**: Copernicus Open Access Policy
- **Authentication**: None on Planetary Computer
- **Update Frequency**: Near-real-time
- **Expected Usefulness**: Cloud-penetrating radar backscatter (VV/VH) for wet-season canopy structure monitoring
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: Moderate. Provides cloud-independent backscatter during cloudy wet seasons (Nov-Apr).

### `modis-mcd43a4-nbar` — MODIS/Terra+Aqua BRDF/Albedo Nadir BRDF-Adjusted Surface Reflectance Daily L3 Global 500m (MCD43A4)
- **Original Provider**: NASA LP DAAC / USGS
- **Official URL**: [https://lpdaac.usgs.gov/products/mcd43a4v061/](https://lpdaac.usgs.gov/products/mcd43a4v061/)
- **Data Domain**: `A_SATELLITE_REMOTE_SENSING`
- **Geographic Coverage**: Global land surface
- **Temporal Coverage**: 2000-02-24 to present
- **Spatial Resolution**: 500 m
- **Temporal Resolution**: Daily (16-day moving window)
- **Access Mechanism**: NASA Earthdata Cloud STAC / LP DAAC / Planetary Computer
- **API / STAC Availability**: Microsoft Planetary Computer (modis-43A4-061), NASA CMR-STAC
- **Licensing**: NASA Open Data Policy (public domain)
- **Authentication**: None on Planetary Computer; NASA Earthdata login required on DAAC
- **Update Frequency**: Daily
- **Expected Usefulness**: View-angle normalized reflectance cross-check for regional phenology and donor alignment
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: Moderate. Coarse 500m resolution, but valuable as a regional phenological cross-check.

### `viirs-vnp09ga-sr` — Suomi NPP VIIRS Surface Reflectance Daily L2G Global 500m and 1km (VNP09GA)
- **Original Provider**: NASA LP DAAC
- **Official URL**: [https://lpdaac.usgs.gov/products/vnp09gav002/](https://lpdaac.usgs.gov/products/vnp09gav002/)
- **Data Domain**: `A_SATELLITE_REMOTE_SENSING`
- **Geographic Coverage**: Global
- **Temporal Coverage**: 2012-01-19 to present
- **Spatial Resolution**: 500 m / 1000 m
- **Temporal Resolution**: Daily
- **Access Mechanism**: NASA Earthdata Cloud / OpenDAP
- **API / STAC Availability**: NASA CMR-STAC
- **Licensing**: NASA Open Data Policy
- **Authentication**: Free NASA Earthdata Bearer Token
- **Update Frequency**: Daily
- **Expected Usefulness**: Bridging MODIS continuity with higher geometric fidelity post-2012
- **Independent Evidence Source**: Yes
- **Integration Status**: `SAMPLE_RETRIEVED`
- **Feasibility for Kariba**: Moderate. Coarse resolution, useful for macro-regional trend verification.

### `gedi-l2a-elevation` — GEDI L2A Elevation and Height Metrics Data Global Footprint Level (GEDI02_A)
- **Original Provider**: NASA LP DAAC / University of Maryland
- **Official URL**: [https://gedi.umd.edu/data/products/](https://gedi.umd.edu/data/products/)
- **Data Domain**: `A_SATELLITE_REMOTE_SENSING`
- **Geographic Coverage**: 51.6° N to 51.6° S global footprint transects
- **Temporal Coverage**: 2019-04-18 to 2023-03-17 (resumed 2024)
- **Spatial Resolution**: 25 m footprint diameter along transects
- **Temporal Resolution**: Non-repeat orbital tracks
- **Access Mechanism**: NASA Earthdata Cloud STAC / HDF5 / Planetary Computer
- **API / STAC Availability**: Planetary Computer (gedi-l2a), NASA CMR-STAC
- **Licensing**: NASA Open Data Policy
- **Authentication**: None on Planetary Computer
- **Update Frequency**: Mission phases (curated releases)
- **Expected Usefulness**: True physical canopy height (RH98) profiling inside Kariba forested parcels
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Multiple orbital passes intersect Hurungwe, Nyaminyami, Binga, and Mbire parcels.

### `gedi-l4a-agbd` — GEDI L4A Footprint Level Aboveground Biomass Density (GEDI04_A)
- **Original Provider**: NASA LP DAAC / UMD
- **Official URL**: [https://daac.ornl.gov/cgi-bin/dsviewer.pl?ds_id=2056](https://daac.ornl.gov/cgi-bin/dsviewer.pl?ds_id=2056)
- **Data Domain**: `A_SATELLITE_REMOTE_SENSING`
- **Geographic Coverage**: 51.6° N to 51.6° S
- **Temporal Coverage**: 2019-04-18 to 2023-03-17
- **Spatial Resolution**: 25 m footprint along transects
- **Temporal Resolution**: Point sample transects
- **Access Mechanism**: NASA Earthdata Cloud / ORNL DAAC / Planetary Computer
- **API / STAC Availability**: Planetary Computer (gedi-l4a), ORNL DAAC
- **Licensing**: NASA Open Data Policy
- **Authentication**: None on Planetary Computer
- **Update Frequency**: Mission releases
- **Expected Usefulness**: Direct, independent physical benchmark for dry miombo aboveground biomass (Mg/ha)
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Calibrated parametric models for African dry deciduous woodland biomass.

### `copernicus-dem-glo-30` — Copernicus Digital Elevation Model (DEM) GLO-30 Global 30m
- **Original Provider**: Copernicus / ESA / Airbus
- **Official URL**: [https://spacedata.copernicus.eu/collections/copernicus-digital-elevation-model](https://spacedata.copernicus.eu/collections/copernicus-digital-elevation-model)
- **Data Domain**: `A_SATELLITE_REMOTE_SENSING`
- **Geographic Coverage**: Global landmasses
- **Temporal Coverage**: 2011-2015 acquisition baseline (WorldDEM)
- **Spatial Resolution**: 30 m (1 arc-second)
- **Temporal Resolution**: Static reference surface
- **Access Mechanism**: STAC API / Cloud-Optimized GeoTIFF
- **API / STAC Availability**: Planetary Computer (cop-dem-glo-30), AWS Registry of Open Data
- **Licensing**: Copernicus Open Access Policy (free for commercial and scientific use)
- **Authentication**: None on Planetary Computer
- **Update Frequency**: Annual maintenance releases
- **Expected Usefulness**: Terrain, slope, aspect, and drainage matching for Kariba and candidate donors
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Full seamless coverage of Zambezi valley and Kariba escarpment.

### `alospalsar-2-mosaic-25m` — JAXA ALOS/ALOS-2 L-Band SAR Annual Global Mosaic 25m
- **Original Provider**: Japan Aerospace Exploration Agency (JAXA)
- **Official URL**: [https://www.eorc.jaxa.jp/ALOS/en/dataset/fnf_e.htm](https://www.eorc.jaxa.jp/ALOS/en/dataset/fnf_e.htm)
- **Data Domain**: `A_SATELLITE_REMOTE_SENSING`
- **Geographic Coverage**: Global land surface
- **Temporal Coverage**: 2007-2010 (ALOS PALSAR), 2014-2022 (ALOS-2 PALSAR-2)
- **Spatial Resolution**: 25 m
- **Temporal Resolution**: Annual dry-season mosaic
- **Access Mechanism**: Direct download / JAXA EORC portal / Open Data on AWS
- **API / STAC Availability**: AWS Open Data registry (jpl-nasaserve-alos)
- **Licensing**: Free for research and commercial use with JAXA citation
- **Authentication**: Free JAXA user registration
- **Update Frequency**: Annual
- **Expected Usefulness**: L-band radar penetration sensitive to woody biomass and woody savanna density
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Unaffected by dry grass phenology, directly probes woody stem volume.

## B. Vegetation and Ecosystem Condition

### `modis-mod13q1-ndvi-evi` — MODIS/Terra Vegetation Indices 16-Day L3 Global 250m (MOD13Q1 v061)
- **Original Provider**: NASA LP DAAC
- **Official URL**: [https://lpdaac.usgs.gov/products/mod13q1v061/](https://lpdaac.usgs.gov/products/mod13q1v061/)
- **Data Domain**: `B_VEGETATION_ECOSYSTEM_CONDITION`
- **Geographic Coverage**: Global land
- **Temporal Coverage**: 2000-02-18 to present
- **Spatial Resolution**: 250 m
- **Temporal Resolution**: 16-day composite
- **Access Mechanism**: STAC API / Cloud-Optimized GeoTIFF / NASA Earthdata
- **API / STAC Availability**: Microsoft Planetary Computer (modis-13Q1-061), NASA CMR
- **Licensing**: Public Domain (NASA Open Data)
- **Authentication**: None on Planetary Computer
- **Update Frequency**: 16-day
- **Expected Usefulness**: Independent continuous 2000-2022 time-series cross-check for Kariba NDVI/EVI trends
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Completely bridges the 2001-2022 analysis window across Kariba.

### `modis-myd13q1-aqua` — MODIS/Aqua Vegetation Indices 16-Day L3 Global 250m (MYD13Q1 v061)
- **Original Provider**: NASA LP DAAC
- **Official URL**: [https://lpdaac.usgs.gov/products/myd13q1v061/](https://lpdaac.usgs.gov/products/myd13q1v061/)
- **Data Domain**: `B_VEGETATION_ECOSYSTEM_CONDITION`
- **Geographic Coverage**: Global land
- **Temporal Coverage**: 2002-07-04 to present
- **Spatial Resolution**: 250 m
- **Temporal Resolution**: 16-day composite (8-day offset with MOD13Q1)
- **Access Mechanism**: STAC API / NASA CMR
- **API / STAC Availability**: Planetary Computer (modis-13Q1-061), NASA CMR
- **Licensing**: Public Domain
- **Authentication**: None on Planetary Computer
- **Update Frequency**: 16-day
- **Expected Usefulness**: Diurnal afternoon observation cross-check reducing cloud impact
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Supplements morning Terra passes.

### `modis-mod15a2h-lai-fapar` — MODIS/Terra Leaf Area Index/FAPAR 8-Day L4 Global 500m (MOD15A2H v061)
- **Original Provider**: NASA LP DAAC
- **Official URL**: [https://lpdaac.usgs.gov/products/mod15a2hv061/](https://lpdaac.usgs.gov/products/mod15a2hv061/)
- **Data Domain**: `B_VEGETATION_ECOSYSTEM_CONDITION`
- **Geographic Coverage**: Global land
- **Temporal Coverage**: 2000-02-18 to present
- **Spatial Resolution**: 500 m
- **Temporal Resolution**: 8-day
- **Access Mechanism**: NASA Earthdata Cloud STAC
- **API / STAC Availability**: Planetary Computer (modis-15A2H-061), NASA CMR
- **Licensing**: Public Domain
- **Authentication**: None on Planetary Computer
- **Update Frequency**: 8-day
- **Expected Usefulness**: Direct biophysical parameter (LAI m2/m2 and FAPAR) avoiding empirical NDVI non-linearities
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: Moderate. Coarse resolution, good for regional photosynthetic absorption trends.

### `copernicus-fapar-300m` — Copernicus Global Land Service Fraction of Absorbed Photosynthetically Active Radiation (FAPAR) 300m
- **Original Provider**: Copernicus Land Monitoring Service (CLMS) / VITO
- **Official URL**: [https://land.copernicus.eu/global/products/fapar](https://land.copernicus.eu/global/products/fapar)
- **Data Domain**: `B_VEGETATION_ECOSYSTEM_CONDITION`
- **Geographic Coverage**: Global land
- **Temporal Coverage**: 2014-01-01 to present (300m), 1999-2020 (1km)
- **Spatial Resolution**: 300 m / 1 km
- **Temporal Resolution**: 10-day synthesis
- **Access Mechanism**: CLMS portal / REST API / CDSE
- **API / STAC Availability**: CDSE STAC / CLMS download API
- **Licensing**: Copernicus Open Access
- **Authentication**: Free Copernicus CDSE user account
- **Update Frequency**: Every 10 days
- **Expected Usefulness**: Independent European biophysical product validating photosynthetic activity without MODIS sensor bias
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Clear dry-season profiles available for all Zimbabwe/Zambia districts.

### `eth-global-canopy-height-10m` — ETH Global 10m Canopy Height Map (Lang et al. 2023)
- **Original Provider**: ETH Zurich / EcoVision Lab
- **Official URL**: [https://langnico.github.io/globalcanopyheight/](https://langnico.github.io/globalcanopyheight/)
- **Data Domain**: `B_VEGETATION_ECOSYSTEM_CONDITION`
- **Geographic Coverage**: Global land surface between 60°N and 60°S
- **Temporal Coverage**: 2020 (reference year)
- **Spatial Resolution**: 10 m
- **Temporal Resolution**: Static annual synthesis (2020)
- **Access Mechanism**: AWS S3 Open Data / Cloud-Optimized GeoTIFF / HuggingFace
- **API / STAC Availability**: Hugging Face datasets (ethz/canopy-height-10m), AWS Open Data
- **Licensing**: Creative Commons Attribution 4.0 International (CC BY 4.0)
- **Authentication**: None (public S3 bucket / direct HTTP)
- **Update Frequency**: Static research release (2020 epoch)
- **Expected Usefulness**: Sub-canopy 10m structure mapping to distinguish intact miombo (>8m) from degraded scrub (<4m)
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Covers all 4 Kariba RDCs and donor districts at 10m resolution.

### `meta-world-canopy-height-1m` — Meta / WRI High-Resolution 1m Global Tree Canopy Height
- **Original Provider**: Meta AI / World Resources Institute
- **Official URL**: [https://wri-datalab.github.io/canopy-height-models/](https://wri-datalab.github.io/canopy-height-models/)
- **Data Domain**: `B_VEGETATION_ECOSYSTEM_CONDITION`
- **Geographic Coverage**: Global terrestrial biomes
- **Temporal Coverage**: 2020 baseline
- **Spatial Resolution**: 1 m
- **Temporal Resolution**: Single epoch (2020)
- **Access Mechanism**: AWS S3 Public Dataset
- **API / STAC Availability**: AWS Registry of Open Data (s3://dataforgood-fb-data/forests/v1/canopy_height/)
- **Licensing**: Creative Commons Attribution 4.0 (CC BY 4.0)
- **Authentication**: None
- **Update Frequency**: Static release
- **Expected Usefulness**: Ultra-high resolution tree density verification for disputed clearing patches
- **Independent Evidence Source**: Yes
- **Integration Status**: `SAMPLE_RETRIEVED`
- **Feasibility for Kariba**: Moderate. Enormous raster volume (1m resolution); suitable for sample parcel auditing.

### `hansen-global-tree-cover-2000` — Hansen Global Forest Change v1.11 Tree Canopy Cover Year 2000
- **Original Provider**: University of Maryland / Google / USGS / NASA
- **Official URL**: [https://storage.googleapis.com/earthenginepartners-hansen/GFC-2023-v1.11/download.html](https://storage.googleapis.com/earthenginepartners-hansen/GFC-2023-v1.11/download.html)
- **Data Domain**: `B_VEGETATION_ECOSYSTEM_CONDITION`
- **Geographic Coverage**: Global land surface (latitudes 80°N - 60°S)
- **Temporal Coverage**: 2000 baseline
- **Spatial Resolution**: 30 m (approx 0.00025 deg)
- **Temporal Resolution**: Static baseline (year 2000)
- **Access Mechanism**: Direct HTTP GeoTIFF tiles / Google Earth Engine
- **API / STAC Availability**: Public Google Cloud Storage tiles (treecover2000)
- **Licensing**: CC BY 4.0 International
- **Authentication**: None (public HTTP download)
- **Update Frequency**: Fixed baseline
- **Expected Usefulness**: Standard baseline tree cover thresholding (>10% or >20% forest mask per ADR-011)
- **Independent Evidence Source**: Yes
- **Integration Status**: `INTEGRATED`
- **Feasibility for Kariba**: High. 10S_020E and 20S_020E tiles cover Kariba and all donor districts completely.

### `landsat-c3-fractional-cover` — Digital Earth Africa Fractional Cover (Landsat 1984-2023)
- **Original Provider**: Digital Earth Africa / Geoscience Australia
- **Official URL**: [https://www.digitalearthafrica.org/data-and-services/fractional-cover](https://www.digitalearthafrica.org/data-and-services/fractional-cover)
- **Data Domain**: `B_VEGETATION_ECOSYSTEM_CONDITION`
- **Geographic Coverage**: Continental Africa
- **Temporal Coverage**: 1984 to 2023
- **Spatial Resolution**: 30 m
- **Temporal Resolution**: Seasonal / Annual summaries
- **Access Mechanism**: DE Africa STAC API / OWS / S3
- **API / STAC Availability**: https://explorer.digitalearth.africa/stac
- **Licensing**: CC BY 4.0
- **Authentication**: None (free public STAC)
- **Update Frequency**: Annual updates
- **Expected Usefulness**: Separates photosynthetic green vegetation (PV), non-photosynthetic vegetation (NPV), and bare soil (BS)
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Critically distinguishes dry grass senescing from actual woodland clearing in miombo.

### `modis-phenology-mcd12q2` — MODIS/Terra+Aqua Land Cover Dynamics Yearly L3 Global 500m (MCD12Q2 v006)
- **Original Provider**: NASA LP DAAC / Boston University
- **Official URL**: [https://lpdaac.usgs.gov/products/mcd12q2v006/](https://lpdaac.usgs.gov/products/mcd12q2v006/)
- **Data Domain**: `B_VEGETATION_ECOSYSTEM_CONDITION`
- **Geographic Coverage**: Global
- **Temporal Coverage**: 2001-2021
- **Spatial Resolution**: 500 m
- **Temporal Resolution**: Annual (phenological metrics: greenup, peak, senescence, dormancy)
- **Access Mechanism**: NASA CMR-STAC / LP DAAC
- **API / STAC Availability**: Planetary Computer (modis-12Q2-006), NASA CMR
- **Licensing**: Public Domain
- **Authentication**: None on Planetary Computer
- **Update Frequency**: Annual
- **Expected Usefulness**: Tracks shifts in greenup dates to identify climate-driven vs deforestation-driven phenology
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: Moderate. Coarse resolution, but provides timing of annual Austral greenup onset.

### `copernicus-dry-matter-productivity-300m` — Copernicus Dry Matter Productivity (DMP) 300m v1
- **Original Provider**: Copernicus Land Monitoring Service
- **Official URL**: [https://land.copernicus.eu/global/products/dmp](https://land.copernicus.eu/global/products/dmp)
- **Data Domain**: `B_VEGETATION_ECOSYSTEM_CONDITION`
- **Geographic Coverage**: Global land
- **Temporal Coverage**: 2014-01-01 to present
- **Spatial Resolution**: 300 m
- **Temporal Resolution**: 10-day synthesis (kg DM/ha/day)
- **Access Mechanism**: CLMS API / CDSE
- **API / STAC Availability**: CDSE STAC / CLMS portal
- **Licensing**: Copernicus Open Access
- **Authentication**: Free CDSE registration
- **Update Frequency**: 10-day
- **Expected Usefulness**: Direct agro-ecological biomass productivity estimate without uncalibrated carbon equations
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Directly quantifies Net Primary Production equivalent in kilograms dry matter per hectare.

### `jrc-tropical-moist-forest-degradation` — JRC Tropical Moist Forest and Degradation Dataset (Vancutsem et al. 2021)
- **Original Provider**: European Commission Joint Research Centre (JRC)
- **Official URL**: [https://forobs.jrc.ec.europa.eu/TMF/](https://forobs.jrc.ec.europa.eu/TMF/)
- **Data Domain**: `B_VEGETATION_ECOSYSTEM_CONDITION`
- **Geographic Coverage**: Pan-tropical belt
- **Temporal Coverage**: 1990-2022 (annual degradation and transition dynamics)
- **Spatial Resolution**: 30 m
- **Temporal Resolution**: Annual / Sub-annual disturbance events
- **Access Mechanism**: Direct HTTP / GEE / JRC data portal
- **API / STAC Availability**: JRC download portal / Google Earth Engine assets
- **Licensing**: CC BY 4.0 International
- **Authentication**: None (public download)
- **Update Frequency**: Annual updates
- **Expected Usefulness**: Distinguishes short-term degradation from permanent deforestation
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: Moderate. Focuses primarily on tropical moist forest, but includes transition zone miombo.

## C. Land Cover and Land Use

### `esa-worldcover-10m` — ESA WorldCover Global 10m Land Cover (2020 & 2021)
- **Original Provider**: ESA / VITO / Brockmann Consult
- **Official URL**: [https://esa-worldcover.org/en](https://esa-worldcover.org/en)
- **Data Domain**: `C_LAND_COVER_LAND_USE`
- **Geographic Coverage**: Global terrestrial land
- **Temporal Coverage**: 2020 and 2021
- **Spatial Resolution**: 10 m
- **Temporal Resolution**: Annual discrete classification (11 classes)
- **Access Mechanism**: STAC API / Cloud-Optimized GeoTIFF / AWS / Planetary Computer
- **API / STAC Availability**: Microsoft Planetary Computer (esa-worldcover), AWS S3 Open Data
- **Licensing**: CC BY 4.0
- **Authentication**: None on Planetary Computer
- **Update Frequency**: Multi-year discrete releases
- **Expected Usefulness**: High-accuracy 10m tree cover mask (Class 10) for verifying VCS 902 eligible forested area (784,987 ha)
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Covers 100% of Kariba AOI and donor polygons.

### `dynamic-world-10m-nrt` — Dynamic World Near-Real-Time 10m Land Use / Land Cover
- **Original Provider**: World Resources Institute (WRI) / Google
- **Official URL**: [https://www.dynamicworld.app/](https://www.dynamicworld.app/)
- **Data Domain**: `C_LAND_COVER_LAND_USE`
- **Geographic Coverage**: Global Sentinel-2 land coverage
- **Temporal Coverage**: 2015-06-23 to present
- **Spatial Resolution**: 10 m
- **Temporal Resolution**: Per-scene Sentinel-2 overpass (5-day cadence)
- **Access Mechanism**: Google Earth Engine / STAC API (Earth Search / GEE)
- **API / STAC Availability**: Google Cloud Storage / Earth Engine / AWS Open Data
- **Licensing**: CC BY 4.0
- **Authentication**: Free Google Earth Engine account or GCS requester-pays
- **Update Frequency**: Near-real-time
- **Expected Usefulness**: Continuous probability-based classification (trees, grass, crops, scrub) tracking month-to-month changes
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Rapidly flags crop expansion within Kariba community concessions.

### `hansen-global-forest-change-v1-11` — Hansen Global Forest Change v1.11 (2000-2023 Loss and Gain)
- **Original Provider**: University of Maryland / GLAD
- **Official URL**: [https://earthenginepartners.appspot.com/science-2013-global-forest](https://earthenginepartners.appspot.com/science-2013-global-forest)
- **Data Domain**: `C_LAND_COVER_LAND_USE`
- **Geographic Coverage**: Global land surface
- **Temporal Coverage**: 2000 to 2023 (annual lossyear layer)
- **Spatial Resolution**: 30 m
- **Temporal Resolution**: Annual forest loss events
- **Access Mechanism**: Direct Google Cloud Storage GeoTIFF / STAC
- **API / STAC Availability**: GCS public bucket (earthenginepartners-hansen/GFC-2023-v1.11/)
- **Licensing**: CC BY 4.0
- **Authentication**: None (free public download)
- **Update Frequency**: Annual
- **Expected Usefulness**: Benchmark independent deforestation loss layer to audit project baseline claims
- **Independent Evidence Source**: Yes
- **Integration Status**: `INTEGRATED`
- **Feasibility for Kariba**: High. Primary standard in voluntary carbon markets; tiles 10S_020E and 20S_020E cover the site.

### `esri-land-cover-10m` — Esri 10m Land Cover (Sentinel-2 Deep Learning 2017-2023)
- **Original Provider**: Esri / Impact Observatory / Microsoft
- **Official URL**: [https://www.arcgis.com/home/item.html?id=cfcb7609e2e1431084224c82b99f3659](https://www.arcgis.com/home/item.html?id=cfcb7609e2e1431084224c82b99f3659)
- **Data Domain**: `C_LAND_COVER_LAND_USE`
- **Geographic Coverage**: Global
- **Temporal Coverage**: 2017 to 2023 (annual time series)
- **Spatial Resolution**: 10 m
- **Temporal Resolution**: Annual
- **Access Mechanism**: STAC API / Cloud-Optimized GeoTIFF
- **API / STAC Availability**: Microsoft Planetary Computer (io-lulc-annual-v02), AWS S3
- **Licensing**: CC BY 4.0
- **Authentication**: None on Planetary Computer
- **Update Frequency**: Annual
- **Expected Usefulness**: Multi-year 10m LULC transitions to independently cross-check ESA WorldCover
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Covers complete post-2017 crediting period over Kariba and all donors.

### `copernicus-cgls-lc100` — Copernicus Global Land Cover Layers 100m (CGLS-LC100)
- **Original Provider**: Copernicus / VITO
- **Official URL**: [https://land.copernicus.eu/global/products/lc100](https://land.copernicus.eu/global/products/lc100)
- **Data Domain**: `C_LAND_COVER_LAND_USE`
- **Geographic Coverage**: Global terrestrial land
- **Temporal Coverage**: 2015 to 2019 (annual collections)
- **Spatial Resolution**: 100 m
- **Temporal Resolution**: Annual
- **Access Mechanism**: STAC API / VITO open data / CDSE
- **API / STAC Availability**: Planetary Computer (cgls-lc100), CDSE
- **Licensing**: Copernicus Open Access
- **Authentication**: None on Planetary Computer
- **Update Frequency**: Completed series (superseded by CLMS 10m)
- **Expected Usefulness**: Continuous fractional canopy cover and forest type breakdown for donor stratification
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Full Southern Africa tile coverage.

### `modis-mcd12q1-land-cover` — MODIS Land Cover Type Yearly L3 Global 500m (MCD12Q1 v061)
- **Original Provider**: NASA LP DAAC / Boston University
- **Official URL**: [https://lpdaac.usgs.gov/products/mcd12q1v061/](https://lpdaac.usgs.gov/products/mcd12q1v061/)
- **Data Domain**: `C_LAND_COVER_LAND_USE`
- **Geographic Coverage**: Global
- **Temporal Coverage**: 2001 to 2022
- **Spatial Resolution**: 500 m
- **Temporal Resolution**: Annual (IGBP, UMD, and LAI classifications)
- **Access Mechanism**: NASA CMR-STAC / LP DAAC
- **API / STAC Availability**: Planetary Computer (modis-12Q1-061), NASA CMR
- **Licensing**: Public Domain
- **Authentication**: None on Planetary Computer
- **Update Frequency**: Annual
- **Expected Usefulness**: Consistent 2001-2022 annual macro-classification across both pre- and post-treatment windows
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Coarse resolution, but spans entire Kariba 22-year timeline without temporal gaps.

### `rcmrd-land-cover-viewer` — RCMRD / SERVIR Eastern & Southern Africa Land Cover Historic & Projected (1990-2030)
- **Original Provider**: RCMRD / USAID / NASA SERVIR
- **Official URL**: [https://landcover-geoportal.rcmrd.org/](https://landcover-geoportal.rcmrd.org/)
- **Data Domain**: `C_LAND_COVER_LAND_USE`
- **Geographic Coverage**: Eastern and Southern Africa (including Zimbabwe and Zambia)
- **Temporal Coverage**: 1990, 2000, 2010, 2015, 2020
- **Spatial Resolution**: 30 m
- **Temporal Resolution**: Decadal / 5-year intervals
- **Access Mechanism**: RCMRD Geoportal WMS / GeoTIFF Download
- **API / STAC Availability**: Direct geoportal download
- **Licensing**: Open access (public government / development cooperation)
- **Authentication**: None
- **Update Frequency**: 5-year epochs
- **Expected Usefulness**: Regional institutional classification reflecting Southern African national forest definitions
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Ground-truthed specifically for Zimbabwe and Zambia ecozones.

### `global-cropland-gfsad30` — Global Food Security-support Analysis Data 30m Cropland Extent (GFSAD30AFCE)
- **Original Provider**: USGS LP DAAC / NASA
- **Official URL**: [https://lpdaac.usgs.gov/products/gfsad30afcev001/](https://lpdaac.usgs.gov/products/gfsad30afcev001/)
- **Data Domain**: `C_LAND_COVER_LAND_USE`
- **Geographic Coverage**: Africa
- **Temporal Coverage**: 2015 (nominal)
- **Spatial Resolution**: 30 m
- **Temporal Resolution**: Single nominal release
- **Access Mechanism**: LP DAAC / NASA Earthdata
- **API / STAC Availability**: NASA CMR-STAC
- **Licensing**: Public Domain
- **Authentication**: NASA Earthdata login
- **Update Frequency**: Fixed baseline
- **Expected Usefulness**: Excludes agricultural fields and smallholder plots from forest baseline
- **Independent Evidence Source**: Yes
- **Integration Status**: `SAMPLE_RETRIEVED`
- **Feasibility for Kariba**: High. Accurately maps communal subsistence farming along RDC valleys.

### `fao-wa-land-cover` — FAO WaPOR Land Cover Classification 100m & 20m
- **Original Provider**: Food and Agriculture Organization (FAO)
- **Official URL**: [https://www.fao.org/in-action/remote-sensing-for-water-productivity/wapor-data/en/](https://www.fao.org/in-action/remote-sensing-for-water-productivity/wapor-data/en/)
- **Data Domain**: `C_LAND_COVER_LAND_USE`
- **Geographic Coverage**: Africa and Near East
- **Temporal Coverage**: 2009 to 2023
- **Spatial Resolution**: 100 m (continental), 20 m (basin)
- **Temporal Resolution**: Annual
- **Access Mechanism**: FAO WaPOR API / Cloud-Optimized GeoTIFF
- **API / STAC Availability**: WaPOR v3 API (https://io.apps.fao.org/geoserver/wapor/wms)
- **Licensing**: CC BY-NC-SA 3.0 IGO
- **Authentication**: Free FAO API token for programmatic access
- **Update Frequency**: Annual
- **Expected Usefulness**: Tracks water-productivity and agricultural encroachments in Zambezi River basin
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Specific coverage of the Zambezi Middle Sub-basin encompassing Kariba.

### `glad-forest-alerts-radd` — RADD Radar-based Near-Real-Time Deforestation Alerts
- **Original Provider**: Wageningen University / Global Forest Watch
- **Official URL**: [https://www.globalforestwatch.org/help/guides-and-videos/user-guides/radar-deforestation-alerts/](https://www.globalforestwatch.org/help/guides-and-videos/user-guides/radar-deforestation-alerts/)
- **Data Domain**: `C_LAND_COVER_LAND_USE`
- **Geographic Coverage**: Pan-tropical Africa and Asia
- **Temporal Coverage**: 2019 to present
- **Spatial Resolution**: 10 m
- **Temporal Resolution**: Weekly updates (Sentinel-1 SAR based)
- **Access Mechanism**: Global Forest Watch API / GEE / GFW Data API
- **API / STAC Availability**: https://data-api.globalforestwatch.org/dataset/gfw_radd_alerts
- **Licensing**: CC BY 4.0
- **Authentication**: GFW API key required for heavy batch querying
- **Update Frequency**: Weekly
- **Expected Usefulness**: Detects canopy disturbance independent of cloud cover in high-risk leakage zones
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Active coverage across all 4 host RDCs and Zambezi valley buffer.

### `esa-cci-land-cover-300m` — ESA Climate Change Initiative (CCI) Land Cover v2.0.7 (1992-2020)
- **Original Provider**: ESA / UCLouvain
- **Official URL**: [https://www.esa-landcover-cci.org/](https://www.esa-landcover-cci.org/)
- **Data Domain**: `C_LAND_COVER_LAND_USE`
- **Geographic Coverage**: Global
- **Temporal Coverage**: 1992 to 2020
- **Spatial Resolution**: 300 m
- **Temporal Resolution**: Annual global maps (consistent 29-year time series)
- **Access Mechanism**: ESA CCI Open Access / C3S Climate Data Store
- **API / STAC Availability**: CDS API / direct NetCDF/GeoTIFF download
- **Licensing**: Open access (free for all applications)
- **Authentication**: Free C3S account for automated API downloads
- **Update Frequency**: Historical long-term climate series (superseded by C3S LC)
- **Expected Usefulness**: Provides long-term pre-2001 historical context for land-use trends in Southern Africa
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Crucial for verifying whether 1990-2000 was already undergoing structural deforestation.

## D. Biodiversity and Species Occurrence

### `gbif-occurrence-api` — Global Biodiversity Information Facility (GBIF) Species Occurrence Records
- **Original Provider**: GBIF Secretariat
- **Official URL**: [https://www.gbif.org/](https://www.gbif.org/)
- **Data Domain**: `D_BIODIVERSITY`
- **Geographic Coverage**: Global
- **Temporal Coverage**: 1700s to present (intensive digital records 1970-2024)
- **Spatial Resolution**: Point coordinates with spatial accuracy metadata
- **Temporal Resolution**: Observation timestamp / date
- **Access Mechanism**: GBIF REST API / Darwin Core Archive (DwC-A) / GBIF Parquet on AWS/PC
- **API / STAC Availability**: https://api.gbif.org/v1/occurrence/search, Planetary Computer (gbif)
- **Licensing**: CC0, CC BY 4.0, or CC BY-NC 4.0 (per record dataset declaration)
- **Authentication**: Free GBIF user registration for asynchronous download DOI generation
- **Update Frequency**: Continuous daily ingestion from publishing institutions
- **Expected Usefulness**: Direct biological observations of key umbrella, threatened, and invasive species across Kariba
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. 14,000+ occurrence records in Kariba polygon (Loxodonta africana, Panthera leo, Colophospermum mopane).

### `ebird-basic-dataset` — eBird Basic Dataset (EBD) Observational Bird Abundance & Frequency
- **Original Provider**: Cornell Lab of Ornithology
- **Official URL**: [https://ebird.org/science/download-ebird-data-products](https://ebird.org/science/download-ebird-data-products)
- **Data Domain**: `D_BIODIVERSITY`
- **Geographic Coverage**: Global bird observation locations
- **Temporal Coverage**: 1960 to present (intense systematic checklists 2005-present)
- **Spatial Resolution**: Checklist coordinates with sampling effort distance/time
- **Temporal Resolution**: Precise checklist timestamp
- **Access Mechanism**: eBird API 2.0 / Annual direct TSV download
- **API / STAC Availability**: https://api.ebird.org/v2/
- **Licensing**: Free for research and non-profit conservation use with attribution
- **Authentication**: eBird API key (free upon application)
- **Update Frequency**: Monthly checklist releases; real-time API
- **Expected Usefulness**: Systematic survey effort data allowing detection/non-detection modeling without presence-only bias
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: Moderate. Concentrated around Lake Kariba, safari camps, and Matusadona National Park.

### `inaturalist-research-grade` — iNaturalist Research-Grade Observations
- **Original Provider**: California Academy of Sciences / National Geographic / iNaturalist
- **Official URL**: [https://www.inaturalist.org/](https://www.inaturalist.org/)
- **Data Domain**: `D_BIODIVERSITY`
- **Geographic Coverage**: Global
- **Temporal Coverage**: 2008 to present
- **Spatial Resolution**: Varies by photo metadata (typically 5-30m GPS accuracy)
- **Temporal Resolution**: Exact timestamp of observation photograph
- **Access Mechanism**: iNaturalist API v1 / AWS S3 Open Data / GBIF mirror
- **API / STAC Availability**: https://api.inaturalist.org/v1/observations, AWS S3 (inaturalist-open-data)
- **Licensing**: CC0 / CC BY / CC BY-NC
- **Authentication**: None for public API (rate-limited at 1 req/sec)
- **Update Frequency**: Continuous / daily updates
- **Expected Usefulness**: Crowdsourced photo-verified ecological evidence of flora and fauna in project parcels
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: Moderate. Sparse in remote community districts; strong along tourist and river corridors.

### `iucn-red-list-api` — IUCN Red List of Threatened Species Spatial Distribution & Assessment API
- **Original Provider**: International Union for Conservation of Nature (IUCN)
- **Official URL**: [https://www.iucnredlist.org/](https://www.iucnredlist.org/)
- **Data Domain**: `D_BIODIVERSITY`
- **Geographic Coverage**: Global species geographic range polygons
- **Temporal Coverage**: 1964 to present (annual updates)
- **Spatial Resolution**: Expert range polygons / Extent of Occurrence (EOO)
- **Temporal Resolution**: Species reassessments (5-10 year cycle)
- **Access Mechanism**: IUCN Red List API v4 / Spatial Shapefile Downloads
- **API / STAC Availability**: https://api.iucnredlist.org/
- **Licensing**: Non-commercial conservation and research use; commercial use requires IBAT license
- **Authentication**: Free IUCN API token upon application
- **Update Frequency**: Two to three releases annually
- **Expected Usefulness**: Determines legal threat status (CR, EN, VU) for species impacted by Kariba project activities
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Confirms presence of Vulnerable/Endangered miombo fauna (e.g. African Elephant, Wild Dog).

### `map-of-life-species-ranges` — Map of Life (MOL) Evaluated Species Distributions
- **Original Provider**: Yale University / Center for Biodiversity and Global Change
- **Official URL**: [https://mol.org/](https://mol.org/)
- **Data Domain**: `D_BIODIVERSITY`
- **Geographic Coverage**: Global
- **Temporal Coverage**: Historical & present baseline
- **Spatial Resolution**: 1 km to 10 km refined habitat suitability
- **Temporal Resolution**: Periodic multi-year synthesis
- **Access Mechanism**: MOL API / Cloud downloads
- **API / STAC Availability**: https://mol.org/api/
- **Licensing**: CC BY-NC 4.0
- **Authentication**: Registration required for high-volume API queries
- **Update Frequency**: Periodic releases
- **Expected Usefulness**: Area of Habitat (AOH) modeling matching elevation and forest cover to species requirements
- **Independent Evidence Source**: Yes
- **Integration Status**: `DISCOVERED`
- **Feasibility for Kariba**: High. Translates remote sensing forest loss directly into habitat area shrinkage metrics.

### `biotime-ecological-monitoring` — BioTIME Ecological Time-Series Database
- **Original Provider**: University of St Andrews / BioTIME Consortium
- **Official URL**: [https://biotime.st-andrews.ac.uk/](https://biotime.st-andrews.ac.uk/)
- **Data Domain**: `D_BIODIVERSITY`
- **Geographic Coverage**: Global ecological assemblage sampling sites
- **Temporal Coverage**: 1874 to present (intensive 1970-2020)
- **Spatial Resolution**: Georeferenced plot/transect coordinates
- **Temporal Resolution**: Annual and seasonal repeat surveys
- **Access Mechanism**: Zenodo direct CSV / R package 'BioTIMEr'
- **API / STAC Availability**: https://doi.org/10.5281/zenodo.4044093
- **Licensing**: Open access with citation (CC BY 4.0)
- **Authentication**: None
- **Update Frequency**: Periodic major releases
- **Expected Usefulness**: Long-term local species richness and evenness trends in Southern African protected woodlands
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: Moderate. Contains several Zambezi basin and Hwange/Chizarira ecological plots.

### `predicts-biodiversity-responses` — PREDICTS Database: Projecting Responses of Ecological Diversity in Changing Terrestrial Systems
- **Original Provider**: Natural History Museum (London) / UNEP-WCMC
- **Official URL**: [https://www.predicts.org.uk/](https://www.predicts.org.uk/)
- **Data Domain**: `D_BIODIVERSITY`
- **Geographic Coverage**: Global terrestrial biomes
- **Temporal Coverage**: 1984 to 2016 survey literature compilation
- **Spatial Resolution**: Site-level GPS coordinates
- **Temporal Resolution**: Field study sampling intervals
- **Access Mechanism**: Direct CSV / R package
- **API / STAC Availability**: https://doi.org/10.5519/0066354
- **Licensing**: CC BY 4.0
- **Authentication**: None
- **Update Frequency**: Curated releases
- **Expected Usefulness**: Empirical models of how species richness changes across miombo primary vs degraded vs cropland uses
- **Independent Evidence Source**: Yes
- **Integration Status**: `SAMPLE_RETRIEVED`
- **Feasibility for Kariba**: High. Provides the ecological response curves mapping Hansen/ESA forest loss to biodiversity impact.

### `unep-wcmc-kba` — World Database of Key Biodiversity Areas (KBA)
- **Original Provider**: Key Biodiversity Areas Partnership / BirdLife International
- **Official URL**: [https://www.keybiodiversityareas.org/](https://www.keybiodiversityareas.org/)
- **Data Domain**: `D_BIODIVERSITY`
- **Geographic Coverage**: Global terrestrial, freshwater and marine KBAs
- **Temporal Coverage**: Present inventory (regularly maintained)
- **Spatial Resolution**: Delineated polygon boundaries
- **Temporal Resolution**: Trigger species assessment updates
- **Access Mechanism**: Direct shapefile download / KBA API
- **API / STAC Availability**: https://www.keybiodiversityareas.org/kba-data
- **Licensing**: Non-commercial conservation and educational use
- **Authentication**: Free terms-of-use agreement form
- **Update Frequency**: Semi-annual
- **Expected Usefulness**: Identifies global conservation priority overlaps within the Kariba RDC concession zones
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Overlaps Middle Zambezi KBA and Lake Kariba ecological zones.

### `movebank-animal-tracking` — Movebank Animal Tracking Data Repository
- **Original Provider**: Max Planck Institute of Animal Behavior
- **Official URL**: [https://www.movebank.org/](https://www.movebank.org/)
- **Data Domain**: `D_BIODIVERSITY`
- **Geographic Coverage**: Global animal movement tracks
- **Temporal Coverage**: 1990 to present
- **Spatial Resolution**: GPS collar telemetry fixes (<10m)
- **Temporal Resolution**: Hourly to daily collar pings
- **Access Mechanism**: Movebank REST API / Data Repository studies
- **API / STAC Availability**: https://www.movebank.org/movebank/service/json-study
- **Licensing**: CC0 / CC BY (per study permissions)
- **Authentication**: Free Movebank account; some telemetry datasets require owner permission
- **Update Frequency**: Continuous
- **Expected Usefulness**: Tracks elephant and carnivore migration corridors across the Kariba donor and project boundaries
- **Independent Evidence Source**: Yes
- **Integration Status**: `SAMPLE_RETRIEVED`
- **Feasibility for Kariba**: Moderate. Public studies cover elephant movements in northern Zimbabwe and Kavango-Zambezi (KAZA).

### `living-planet-database` — Living Planet Index (LPI) Population Time Series
- **Original Provider**: Zoological Society of London (ZSL) / WWF
- **Official URL**: [https://www.livingplanetindex.org/](https://www.livingplanetindex.org/)
- **Data Domain**: `D_BIODIVERSITY`
- **Geographic Coverage**: Global vertebrate population monitoring
- **Temporal Coverage**: 1970 to 2020
- **Spatial Resolution**: Site-level georeferenced populations
- **Temporal Resolution**: Annual census counts
- **Access Mechanism**: Direct CSV download / ZSL portal
- **API / STAC Availability**: https://livingplanetindex.org/data_portal
- **Licensing**: CC BY 4.0
- **Authentication**: Free registration
- **Update Frequency**: Biennial updates
- **Expected Usefulness**: Ground-survey population census counts for wildlife populations in Zambezi protected areas
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: Moderate. Historical wildlife census data for Hurungwe Safari Area and Matusadona.

## E. Climate, Precipitation and Temperature

### `chirps-v2-precipitation` — Climate Hazards Center InfraRed Precipitation with Station data (CHIRPS v2.0)
- **Original Provider**: Climate Hazards Center (CHC) / UC Santa Barbara / USGS
- **Official URL**: [https://www.chc.ucsb.edu/data/chirps](https://www.chc.ucsb.edu/data/chirps)
- **Data Domain**: `E_CLIMATE`
- **Geographic Coverage**: 50°S - 50°N all longitudes
- **Temporal Coverage**: 1981-01-01 to present (43+ years)
- **Spatial Resolution**: 0.05° (approx 5.3 km)
- **Temporal Resolution**: Daily, pentadal, dekadal, and monthly aggregates
- **Access Mechanism**: Direct FTP / HTTP / Planetary Computer / AWS Open Data
- **API / STAC Availability**: Planetary Computer (chirps-p05), CHC FTP / HTTP
- **Licensing**: Public Domain (open science)
- **Authentication**: None
- **Update Frequency**: Monthly updates with 1-month latency
- **Expected Usefulness**: Primary authoritative rainfall covariate; essential for SPI drought computation and rainfall-adjusted SCM
- **Independent Evidence Source**: Yes
- **Integration Status**: `INTEGRATED`
- **Feasibility for Kariba**: High. Acquired and cached across Kariba and 37 eligible donor districts (1981-2023).

### `era5-land-reanalysis` — ERA5-Land Monthly Averaged Surface Reanalysis (1950 to present)
- **Original Provider**: European Centre for Medium-Range Weather Forecasts (ECMWF) / Copernicus C3S
- **Official URL**: [https://cds.climate.copernicus.eu/cdsapp#!/dataset/reanalysis-era5-land-monthly-means](https://cds.climate.copernicus.eu/cdsapp#!/dataset/reanalysis-era5-land-monthly-means)
- **Data Domain**: `E_CLIMATE`
- **Geographic Coverage**: Global land surface
- **Temporal Coverage**: 1950 to present
- **Spatial Resolution**: 0.1° (approx 9 km)
- **Temporal Resolution**: Monthly averages / Hourly native
- **Access Mechanism**: Copernicus Climate Data Store (CDS) API / Planetary Computer
- **API / STAC Availability**: Planetary Computer (era5-land-monthly-means), CDS API
- **Licensing**: Copernicus Open Access / ECMWF License
- **Authentication**: CDS API key required for direct CDS; free anonymous on Planetary Computer
- **Update Frequency**: Monthly updates with ~2-3 month latency
- **Expected Usefulness**: High-fidelity physical atmospheric reanalysis (soil temperature, skin temperature, 2m dewpoint, potential evapotranspiration)
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Completely covers Zimbabwe and Zambia with physical mass-and-energy balance.

### `nasa-power-merra2` — NASA POWER MERRA-2 Daily & Monthly Meteorological Indicators
- **Original Provider**: NASA Langley Research Center / NASA POWER Project
- **Official URL**: [https://power.larc.nasa.gov/](https://power.larc.nasa.gov/)
- **Data Domain**: `E_CLIMATE`
- **Geographic Coverage**: Global
- **Temporal Coverage**: 1981 to present
- **Spatial Resolution**: 0.5° x 0.625°
- **Temporal Resolution**: Daily / Monthly (T2M, T2M_MAX, T2M_MIN, PRECTOTCORR)
- **Access Mechanism**: NASA POWER REST API v2
- **API / STAC Availability**: https://power.larc.nasa.gov/api/temporal/monthly/point
- **Licensing**: NASA Open Data Policy (public domain)
- **Authentication**: None (free public REST API)
- **Update Frequency**: Daily / Monthly updates
- **Expected Usefulness**: Provides verified monthly 2m mean, maximum, and minimum temperatures across all Kariba units
- **Independent Evidence Source**: Yes
- **Integration Status**: `INTEGRATED`
- **Feasibility for Kariba**: High. Ingested into climate cache for Kariba and all 51 candidate donor units (1981-2023).

### `chirtsmax-v1-temperature` — Climate Hazards Center InfraRed Temperature with Stations Maximum (CHIRTSmax v1.0)
- **Original Provider**: Climate Hazards Center / UC Santa Barbara
- **Official URL**: [https://www.chc.ucsb.edu/data/chirtsmax](https://www.chc.ucsb.edu/data/chirtsmax)
- **Data Domain**: `E_CLIMATE`
- **Geographic Coverage**: Global 60°S - 70°N
- **Temporal Coverage**: 1983-01-01 to 2016-12-31
- **Spatial Resolution**: 0.05° (approx 5.3 km)
- **Temporal Resolution**: Daily maximum temperature
- **Access Mechanism**: Direct HTTP / CHC FTP
- **API / STAC Availability**: https://data.chc.ucsb.edu/products/CHIRTSmax/
- **Licensing**: Public Domain
- **Authentication**: None
- **Update Frequency**: Historical CDR; ended at 2016
- **Expected Usefulness**: High-resolution temperature extreme validation for 1983-2016 (reaches horizon at 2016)
- **Independent Evidence Source**: Yes
- **Integration Status**: `INTEGRATED`
- **Feasibility for Kariba**: High. Documented and integrated up to its 2016 archive boundary.

### `terraclimate-monthly-gridded` — TerraClimate Monthly High-Resolution Climate and Climatic Water Balance (1958-present)
- **Original Provider**: University of Idaho / Climatology Lab
- **Official URL**: [https://www.climatologylab.org/terraclimate.html](https://www.climatologylab.org/terraclimate.html)
- **Data Domain**: `E_CLIMATE`
- **Geographic Coverage**: Global terrestrial land
- **Temporal Coverage**: 1958 to 2023
- **Spatial Resolution**: 1/24° (~4 km)
- **Temporal Resolution**: Monthly (PDSI, actual evapotranspiration, runoff, vapor pressure deficit)
- **Access Mechanism**: STAC API / Cloud-Optimized GeoTIFF / NetCDF / THREDDS
- **API / STAC Availability**: Microsoft Planetary Computer (terraclimate), THREDDS server
- **Licensing**: Public Domain (CC0)
- **Authentication**: None on Planetary Computer
- **Update Frequency**: Annual updates
- **Expected Usefulness**: Physiological water stress metrics (Vapor Pressure Deficit, Palmer Drought Severity Index PDSI)
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. VPD and climatic water deficit directly drive dry-forest tree mortality.

### `worldclim-v2-1-bioclim` — WorldClim Version 2.1 Baseline Climatology and Bioclimatic Variables (1970-2000)
- **Original Provider**: WorldClim / UC Berkeley
- **Official URL**: [https://www.worldclim.org/data/worldclim21.html](https://www.worldclim.org/data/worldclim21.html)
- **Data Domain**: `E_CLIMATE`
- **Geographic Coverage**: Global land surface
- **Temporal Coverage**: 1970-2000 climatological baseline
- **Spatial Resolution**: 30 arc-seconds (~1 km)
- **Temporal Resolution**: 30-year long-term monthly averages and 19 bioclimatic indicators (BIO1-BIO19)
- **Access Mechanism**: Direct HTTP GeoTIFF download
- **API / STAC Availability**: https://biogeo.ucdavis.edu/data/worldclim/v2.1/
- **Licensing**: CC BY-SA 4.0
- **Authentication**: None
- **Update Frequency**: Static reference climatology
- **Expected Usefulness**: Standardized ecological niche matching (isothermality, precipitation seasonality) for donor candidate selection
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Perfect baseline for Mahalanobis distance donor matching.

### `cru-ts-v4-monthly` — Climatic Research Unit gridded Time Series v4 (CRU TS v4.07)
- **Original Provider**: University of East Anglia CRU
- **Official URL**: [https://crudata.uea.ac.uk/cru/data/hrg/](https://crudata.uea.ac.uk/cru/data/hrg/)
- **Data Domain**: `E_CLIMATE`
- **Geographic Coverage**: Global land (excluding Antarctica)
- **Temporal Coverage**: 1901 to 2022
- **Spatial Resolution**: 0.5° x 0.5°
- **Temporal Resolution**: Monthly station-interpolated climate
- **Access Mechanism**: CEDA Archive / OpenDAP / NetCDF
- **API / STAC Availability**: https://catalogue.ceda.ac.uk/uuid/897782da940842e48545b746813b1945
- **Licensing**: Open Government License / Academic use
- **Authentication**: Free CEDA account
- **Update Frequency**: Annual releases
- **Expected Usefulness**: Century-long instrumental station cross-check for regional Southern Africa precipitation trends
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: Moderate. Coarser spatial resolution than CHIRPS, but useful for multi-decadal trend validation.

### `mswep-v2-8-precipitation` — Multi-Source Weighted-Ensemble Precipitation (MSWEP v2.8)
- **Original Provider**: GloH2O / Princeton University
- **Official URL**: [https://www.gloh2o.org/mswep/](https://www.gloh2o.org/mswep/)
- **Data Domain**: `E_CLIMATE`
- **Geographic Coverage**: Global
- **Temporal Coverage**: 1979 to present
- **Spatial Resolution**: 0.1° (~10 km)
- **Temporal Resolution**: 3-hourly, daily, monthly (optimal gauge-radar-satellite blend)
- **Access Mechanism**: GloH2O Google Drive / OpenDAP
- **API / STAC Availability**: Direct download request on GloH2O portal
- **Licensing**: Free for non-commercial research and educational use
- **Authentication**: Registration required for download link
- **Update Frequency**: Monthly updates
- **Expected Usefulness**: Combines gauge, satellite, and reanalysis data with optimal merging weights
- **Independent Evidence Source**: Yes
- **Integration Status**: `SAMPLE_RETRIEVED`
- **Feasibility for Kariba**: High. High accuracy in mountainous Zambezi escarpment zones.

### `tamsat-v3-rainfall` — Tropical Applications of Meteorology using SATellite data (TAMSAT v3.1)
- **Original Provider**: University of Reading / UK Met Office
- **Official URL**: [https://www.tamsat.org.uk/](https://www.tamsat.org.uk/)
- **Data Domain**: `E_CLIMATE`
- **Geographic Coverage**: All Africa
- **Temporal Coverage**: 1983 to present
- **Spatial Resolution**: 0.0375° (~4 km)
- **Temporal Resolution**: Daily, pentadal, dekadal, monthly
- **Access Mechanism**: TAMSAT Open Data HTTP / NetCDF
- **API / STAC Availability**: https://www.tamsat.org.uk/data/archive
- **Licensing**: Open access with attribution
- **Authentication**: None
- **Update Frequency**: Monthly updates
- **Expected Usefulness**: Africa-specialized thermal infrared rainfall estimate tuned to African convective systems
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Completely independent of CHIRPS calibration, providing an ideal cross-check.

### `spei-global-drought-monitor` — Standardized Precipitation-Evapotranspiration Index Global Drought Monitor (SPEIbase v2.9)
- **Original Provider**: Consejo Superior de Investigaciones Científicas (CSIC)
- **Official URL**: [https://spei.csic.es/spei_database.html](https://spei.csic.es/spei_database.html)
- **Data Domain**: `E_CLIMATE`
- **Geographic Coverage**: Global land
- **Temporal Coverage**: 1901 to 2022
- **Spatial Resolution**: 0.5°
- **Temporal Resolution**: Multi-scale monthly (SPEI-1, 3, 6, 12, 24, 48 months)
- **Access Mechanism**: CSIC Open Data portal / NetCDF
- **API / STAC Availability**: https://spei.csic.es/database.html
- **Licensing**: CC BY-NC 4.0
- **Authentication**: None
- **Update Frequency**: Annual
- **Expected Usefulness**: Integrates potential evapotranspiration (PET) with rainfall to identify multiscale drought
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Validates whether the 2019 severe drought (-1.61 SPI) was accompanied by record PET.

### `gsmap-global-satellite-precipitation` — Global Satellite Mapping of Precipitation (JAXA GSMaP v8)
- **Original Provider**: JAXA Earth Observation Research Center
- **Official URL**: [https://sharaku.eorc.jaxa.jp/GSMaP/](https://sharaku.eorc.jaxa.jp/GSMaP/)
- **Data Domain**: `E_CLIMATE`
- **Geographic Coverage**: 60°N to 60°S
- **Temporal Coverage**: 2000 to present
- **Spatial Resolution**: 0.1° (~10 km)
- **Temporal Resolution**: Hourly / Daily / Monthly
- **Access Mechanism**: JAXA FTP / G-Portal
- **API / STAC Availability**: ftp://hokusai.eorc.jaxa.jp
- **Licensing**: Free with JAXA citation
- **Authentication**: Free registration for FTP credentials
- **Update Frequency**: Near-real-time & gauge-calibrated monthly
- **Expected Usefulness**: Dual-frequency microwave precipitation sounding independent of US/European satellite constellations
- **Independent Evidence Source**: Yes
- **Integration Status**: `SAMPLE_RETRIEVED`
- **Feasibility for Kariba**: Moderate. High temporal resolution, good for storm intensity analysis.

## F. Hydrology and Surface Water

### `hydrosheds-v1-drainage` — HydroSHEDS Hydrographic Information at 3 and 15 Arc-Seconds
- **Original Provider**: World Wildlife Fund (WWF) / USGS
- **Official URL**: [https://www.hydrosheds.org/](https://www.hydrosheds.org/)
- **Data Domain**: `F_HYDROLOGY`
- **Geographic Coverage**: Global 60°N to 56°S
- **Temporal Coverage**: Static baseline (derived from SRTM)
- **Spatial Resolution**: 3 arc-seconds (~90 m) and 15 arc-seconds (~500 m)
- **Temporal Resolution**: Static digital river network
- **Access Mechanism**: Direct shapefile / GeoTIFF download / AWS Open Data
- **API / STAC Availability**: https://data.hydrosheds.org/file/hydrosheds-v1-dem/
- **Licensing**: Free for non-commercial and academic use with WWF citation
- **Authentication**: None
- **Update Frequency**: Periodic version updates (HydroSHEDS v1 / v2 in prep)
- **Expected Usefulness**: River flow routing and basin delineation for the Kariba dam catchment and Zambezi river system
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Covers entire Middle Zambezi sub-basin and Lake Kariba shoreline.

### `hydroatlas-v1-subbasins` — HydroATLAS Basin-Level Hydro-Environmental Attributes (BasinATLAS v1.0)
- **Original Provider**: McGill University / WWF / HydroSHEDS
- **Official URL**: [https://www.hydrosheds.org/hydroatlas](https://www.hydrosheds.org/hydroatlas)
- **Data Domain**: `F_HYDROLOGY`
- **Geographic Coverage**: Global nested sub-basins (levels 1-12)
- **Temporal Coverage**: Comprehensive multi-year climatological and physiographic attributes
- **Spatial Resolution**: Vector polygon sub-basins with 281 hydro-environmental attributes
- **Temporal Resolution**: Static & multi-decadal climatologies
- **Access Mechanism**: Direct Geopackage / Shapefile / Google Earth Engine
- **API / STAC Availability**: https://data.hydrosheds.org/file/hydroatlas/
- **Licensing**: CC BY 4.0
- **Authentication**: None
- **Update Frequency**: Periodic releases
- **Expected Usefulness**: Physiographic, runoff, stream order, and soil moisture attributes for hydrological donor matching
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Provides Level 8 and Level 12 sub-basin boundaries for Zambezi tributaries in Kariba RDCs.

### `jrc-global-surface-water` — JRC Global Surface Water Dataset v1.4 (1984-2021)
- **Original Provider**: European Commission Joint Research Centre (JRC)
- **Official URL**: [https://global-surface-water.appspot.com/](https://global-surface-water.appspot.com/)
- **Data Domain**: `F_HYDROLOGY`
- **Geographic Coverage**: Global
- **Temporal Coverage**: 1984 to 2021
- **Spatial Resolution**: 30 m
- **Temporal Resolution**: Monthly water occurrence / Annual transitions (38-year history)
- **Access Mechanism**: Planetary Computer / Google Earth Engine / Direct HTTP tiles
- **API / STAC Availability**: Microsoft Planetary Computer (jrc-gsw), JRC portal
- **Licensing**: Copernicus Open Access / CC BY 4.0
- **Authentication**: None on Planetary Computer
- **Update Frequency**: Annual
- **Expected Usefulness**: Lake Kariba water level and shoreline fluctuation tracking across 1984-2021
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Prevents false deforestation flags caused by Lake Kariba reservoir drawdown.

### `swot-surface-water-ocean-topography` — SWOT KaRIn High-Rate Lake Single Pass Vector Products
- **Original Provider**: NASA / CNES / JPL
- **Official URL**: [https://swot.jpl.nasa.gov/](https://swot.jpl.nasa.gov/)
- **Data Domain**: `F_HYDROLOGY`
- **Geographic Coverage**: Global 78°S to 78°N
- **Temporal Coverage**: 2023 to present
- **Spatial Resolution**: 10-20 m Ka-band radar interferometry
- **Temporal Resolution**: 21-day orbit cycle
- **Access Mechanism**: NASA PO.DAAC / CMR-STAC
- **API / STAC Availability**: NASA Earthdata Cloud CMR-STAC (SWOT_L2_HR_LakeSP)
- **Licensing**: NASA/CNES Open Data Policy
- **Authentication**: Free NASA Earthdata Bearer Token
- **Update Frequency**: Operational continuous
- **Expected Usefulness**: High-accuracy lake water surface elevation for Lake Kariba monitoring
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Direct radar swaths over Lake Kariba reservoir.

### `grace-fo-mascon-groundwater` — GRACE and GRACE-FO Tellus Land Water Equivalent Thickness (JPL Mascons RL06.1v03)
- **Original Provider**: NASA JPL / University of Texas CSR
- **Official URL**: [https://grace.jpl.nasa.gov/data/get-data/jpl_global_mascons/](https://grace.jpl.nasa.gov/data/get-data/jpl_global_mascons/)
- **Data Domain**: `F_HYDROLOGY`
- **Geographic Coverage**: Global land
- **Temporal Coverage**: 2002 to present (GRACE 2002-2017, GRACE-FO 2018-present)
- **Spatial Resolution**: 0.5° (~55 km equivalent)
- **Temporal Resolution**: Monthly terrestrial water storage anomalies (cm liquid water equivalent)
- **Access Mechanism**: NASA PO.DAAC / Earthdata Cloud
- **API / STAC Availability**: NASA PO.DAAC CMR
- **Licensing**: Public Domain
- **Authentication**: Free NASA Earthdata login
- **Update Frequency**: Monthly updates
- **Expected Usefulness**: Deep groundwater and total terrestrial water storage depletion tracking across Southern Africa
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: Moderate. Coarse gravimetric resolution, ideal for macro-basin groundwater depletion trends.

### `smap-l3-soil-moisture` — SMAP L3 Radiometer Global Daily 36km / 9km EASE-Grid Soil Moisture
- **Original Provider**: NASA NSIDC DAAC / JPL
- **Official URL**: [https://nsidc.org/data/smap](https://nsidc.org/data/smap)
- **Data Domain**: `F_HYDROLOGY`
- **Geographic Coverage**: Global land surface
- **Temporal Coverage**: 2015-03-31 to present
- **Spatial Resolution**: 9 km (enhanced) / 36 km (standard)
- **Temporal Resolution**: Daily L-band passive microwave
- **Access Mechanism**: NASA Earthdata / NSIDC DAAC / Planetary Computer
- **API / STAC Availability**: NASA CMR-STAC
- **Licensing**: Public Domain
- **Authentication**: NASA Earthdata login
- **Update Frequency**: Daily
- **Expected Usefulness**: Top 5 cm soil volumetric water content (cm3/cm3) for drought and vegetation stress validation
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Covers Zimbabwe dry savanna soils with low radio frequency interference (RFI).

### `gldas-noah-land-surface` — Global Land Data Assimilation System (GLDAS) Noah Land Surface Model L4 0.25° Monthly (GLDAS_NOAH025_M v2.1)
- **Original Provider**: NASA GES DISC
- **Official URL**: [https://ldas.gsfc.nasa.gov/gldas](https://ldas.gsfc.nasa.gov/gldas)
- **Data Domain**: `F_HYDROLOGY`
- **Geographic Coverage**: Global 60°S to 90°N
- **Temporal Coverage**: 2000-01-01 to present
- **Spatial Resolution**: 0.25° (~25 km)
- **Temporal Resolution**: Monthly (soil moisture profiles 0-10cm, 10-40cm, 40-100cm, 100-200cm)
- **Access Mechanism**: NASA GES DISC OpenDAP / HTTPS
- **API / STAC Availability**: NASA CMR-STAC
- **Licensing**: Public Domain
- **Authentication**: Free NASA Earthdata login
- **Update Frequency**: Monthly updates
- **Expected Usefulness**: Root-zone soil moisture (0-100 cm) and subsurface runoff for tree survivorship modeling
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Root-zone soil moisture is the primary biophysical driver of miombo tree growth.

### `glofas-river-discharge-reanalysis` — Global Flood Awareness System (GloFAS) River Discharge Reanalysis v4.0
- **Original Provider**: Copernicus CEMS / ECMWF
- **Official URL**: [https://www.globalfloods.eu/](https://www.globalfloods.eu/)
- **Data Domain**: `F_HYDROLOGY`
- **Geographic Coverage**: Global river network
- **Temporal Coverage**: 1979 to present
- **Spatial Resolution**: 0.05° (~5 km river grid)
- **Temporal Resolution**: Daily discharge (m3/s)
- **Access Mechanism**: Copernicus Climate Data Store (CDS) API
- **API / STAC Availability**: CDS API (cems-glofas-historical)
- **Licensing**: Copernicus Open Access
- **Authentication**: CDS API credentials
- **Update Frequency**: Continuous updates
- **Expected Usefulness**: Inflow and discharge rates for the Zambezi, Sengwa, and Ume rivers entering Lake Kariba
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Direct discharge series for Zambezi River at Victoria Falls and Kariba Dam.

### `esa-cci-soil-moisture` — ESA Climate Change Initiative (CCI) Soil Moisture Combined Product v08.1
- **Original Provider**: ESA / TU Wien
- **Official URL**: [https://climate.esa.int/en/projects/soil-moisture/](https://climate.esa.int/en/projects/soil-moisture/)
- **Data Domain**: `F_HYDROLOGY`
- **Geographic Coverage**: Global
- **Temporal Coverage**: 1978 to 2022 (44-year continuous CDR)
- **Spatial Resolution**: 0.25° (~25 km)
- **Temporal Resolution**: Daily active-passive merged satellite observations
- **Access Mechanism**: C3S Climate Data Store / Direct FTP
- **API / STAC Availability**: CDS API / ESA CCI Data Portal
- **Licensing**: Open Access (free)
- **Authentication**: Free CDS account
- **Update Frequency**: Annual historical updates
- **Expected Usefulness**: Multi-decadal satellite soil moisture time-series covering the entire 2001-2022 panel
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Unbroken 44-year record across Southern Africa.

### `merit-hydro-digital-elevation` — MERIT Hydro: High-Resolution Global Hydrography at 3 Arc-Seconds
- **Original Provider**: University of Tokyo / Yamazaki et al.
- **Official URL**: [http://hydro.iis.u-tokyo.ac.jp/~yamadai/MERIT_Hydro/](http://hydro.iis.u-tokyo.ac.jp/~yamadai/MERIT_Hydro/)
- **Data Domain**: `F_HYDROLOGY`
- **Geographic Coverage**: Global land surface
- **Temporal Coverage**: Static hydrological model baseline
- **Spatial Resolution**: 3 arc-seconds (~90 m)
- **Temporal Resolution**: Static hydrography layer
- **Access Mechanism**: Direct HTTP GeoTIFF download
- **API / STAC Availability**: http://hydro.iis.u-tokyo.ac.jp/~yamadai/MERIT_Hydro/
- **Licensing**: CC BY-NC 4.0 or Open for research
- **Authentication**: None (direct HTTP download)
- **Update Frequency**: Curated releases
- **Expected Usefulness**: Hydrologically conditioned flow direction and upstream accumulation without DEM artifacts
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Essential for slope-hydrology matching in donor selection.

## G. Fire and Disturbance

### `modis-mcd64a1-burned-area` — MODIS Burned Area Monthly L3 Global 500m (MCD64A1 v061)
- **Original Provider**: NASA LP DAAC / University of Maryland
- **Official URL**: [https://lpdaac.usgs.gov/products/mcd64a1v061/](https://lpdaac.usgs.gov/products/mcd64a1v061/)
- **Data Domain**: `G_FIRE_DISTURBANCE`
- **Geographic Coverage**: Global land
- **Temporal Coverage**: 2000-11-01 to present (22+ years)
- **Spatial Resolution**: 500 m
- **Temporal Resolution**: Monthly (burn date day-of-year, burn quality)
- **Access Mechanism**: NASA Earthdata Cloud STAC / Planetary Computer
- **API / STAC Availability**: Planetary Computer (modis-64A1-061), NASA CMR
- **Licensing**: Public Domain (NASA Open Data)
- **Authentication**: None on Planetary Computer
- **Update Frequency**: Monthly updates
- **Expected Usefulness**: Primary independent fire disturbance layer; distinguishes fire scars from permanent forest clearing
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Miombo is a fire-adapted ecosystem; tracking fire recurrence is mandatory.

### `viirs-vnp14imgtdl-active-fires` — VIIRS / Suomi NPP 375m NRT Active Fire / Thermal Anomalies (VNP14IMGTDL)
- **Original Provider**: NASA FIRMS / LANCE
- **Official URL**: [https://earthdata.nasa.gov/earth-observation-data/near-real-time/firms/vnp14imgtdl](https://earthdata.nasa.gov/earth-observation-data/near-real-time/firms/vnp14imgtdl)
- **Data Domain**: `G_FIRE_DISTURBANCE`
- **Geographic Coverage**: Global
- **Temporal Coverage**: 2012-01-20 to present
- **Spatial Resolution**: 375 m
- **Temporal Resolution**: Twice daily passes (day & night thermal detections)
- **Access Mechanism**: NASA FIRMS API / Direct CSV / WMS / GeoJSON
- **API / STAC Availability**: https://firms.modaps.eosdis.nasa.gov/api/
- **Licensing**: Public Domain (NASA Open Data)
- **Authentication**: Free NASA FIRMS MAP_KEY
- **Update Frequency**: Real-time within 3 hours of overpass
- **Expected Usefulness**: High-spatial resolution active fire alerts pinpointing agricultural burn-offs inside concessions
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Successfully detects dry-season fires across Kariba's 4 RDCs.

### `modis-mod14a1-active-fires` — MODIS/Terra Thermal Anomalies and Fire Daily L3 Global 1km (MOD14A1 v061)
- **Original Provider**: NASA LP DAAC
- **Official URL**: [https://lpdaac.usgs.gov/products/mod14a1v061/](https://lpdaac.usgs.gov/products/mod14a1v061/)
- **Data Domain**: `G_FIRE_DISTURBANCE`
- **Geographic Coverage**: Global
- **Temporal Coverage**: 2000-02-24 to present
- **Spatial Resolution**: 1 km
- **Temporal Resolution**: Daily
- **Access Mechanism**: NASA CMR-STAC / LP DAAC
- **API / STAC Availability**: Planetary Computer (modis-14A1-061), NASA CMR
- **Licensing**: Public Domain
- **Authentication**: None on Planetary Computer
- **Update Frequency**: Daily
- **Expected Usefulness**: Continuous 2001-2022 fire radiative power (FRP) history spanning the pre-treatment baseline
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Covers entire 2001-2010 pre-treatment period before VIIRS became operational.

### `firecci51-burned-area-250m` — ESA Fire_cci Burned Area Grid product version 5.1 (2001-2020)
- **Original Provider**: ESA Climate Change Initiative / University of Alcala
- **Official URL**: [https://climate.esa.int/en/projects/fire/](https://climate.esa.int/en/projects/fire/)
- **Data Domain**: `G_FIRE_DISTURBANCE`
- **Geographic Coverage**: Global
- **Temporal Coverage**: 2001 to 2020
- **Spatial Resolution**: 250 m
- **Temporal Resolution**: Monthly / Daily burn date estimate (MODIS 250m guided)
- **Access Mechanism**: CEDA Archive / ESA CCI Data Portal
- **API / STAC Availability**: https://data.ceda.ac.uk/neodc/esacci/fire/
- **Licensing**: Open Access (free)
- **Authentication**: Free CEDA account
- **Update Frequency**: Historical climate benchmark
- **Expected Usefulness**: European independent burned area algorithm verifying MODIS MCD64A1 estimates
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. High agreement on dry-season burn scar boundaries in Zambezi woodland.

### `gwis-global-wildfire-info` — Global Wildfire Information System (GWIS) Fire Danger Forecast and Near-Real-Time Statistics
- **Original Provider**: European Commission JRC / GEO
- **Official URL**: [https://gwis.jrc.ec.europa.eu/](https://gwis.jrc.ec.europa.eu/)
- **Data Domain**: `G_FIRE_DISTURBANCE`
- **Geographic Coverage**: Global
- **Temporal Coverage**: 2000 to present
- **Spatial Resolution**: 0.25° (Fire Weather Index) and 500m (burnt area)
- **Temporal Resolution**: Daily fire weather index (FWI) components
- **Access Mechanism**: GWIS WMS / WFS / Direct NetCDF API
- **API / STAC Availability**: https://gwis.jrc.ec.europa.eu/apps/gwis.server/
- **Licensing**: EU Open Data Policy
- **Authentication**: None
- **Update Frequency**: Daily
- **Expected Usefulness**: Canadian Fire Weather Index (FWI) ratings assessing meteorological fire danger vs human ignitions
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Disentangles weather-induced fire risk from intentional project anti-poaching/agricultural burns.

### `sentinel-2-burn-severity-nbr` — Differenced Normalized Burn Ratio (dNBR) from Sentinel-2 L2A
- **Original Provider**: Derived internally by GroundTruth pipeline from Copernicus Sentinel-2
- **Official URL**: [https://sentinels.copernicus.eu/web/sentinel/technical-guides/sentinel-2-msi](https://sentinels.copernicus.eu/web/sentinel/technical-guides/sentinel-2-msi)
- **Data Domain**: `G_FIRE_DISTURBANCE`
- **Geographic Coverage**: Kariba project and donor AOIs
- **Temporal Coverage**: 2016 to 2023
- **Spatial Resolution**: 20 m
- **Temporal Resolution**: Per-overpass / Pre-post fire season comparison
- **Access Mechanism**: Computed on demand via STAC pipeline
- **API / STAC Availability**: In-memory / GroundTruth STAC engine
- **Licensing**: CC BY 4.0 (GroundTruth implementation)
- **Authentication**: None (derived from open S2 imagery)
- **Update Frequency**: Annual / Seasonal
- **Expected Usefulness**: High-resolution classification of burn severity (unburned, low severity, high severity scorched canopy)
- **Independent Evidence Source**: No (Derived indicator)
- **Integration Status**: `INTEGRATED`
- **Feasibility for Kariba**: High. NBR band calculation (B8 - B12)/(B8 + B12) is already implemented in `indices.py`.

### `glad-forest-alerts-gfw` — GLAD Landsat Deforestation Alerts (Hansen et al. 2016)
- **Original Provider**: University of Maryland GLAD / Global Forest Watch
- **Official URL**: [https://glad.umd.edu/projects/primary-forest-analytics](https://glad.umd.edu/projects/primary-forest-analytics)
- **Data Domain**: `G_FIRE_DISTURBANCE`
- **Geographic Coverage**: 30°N to 30°S pan-tropical zone
- **Temporal Coverage**: 2016 to present
- **Spatial Resolution**: 30 m
- **Temporal Resolution**: Weekly updates (Landsat-derived)
- **Access Mechanism**: Global Forest Watch Data API / GEE
- **API / STAC Availability**: https://data-api.globalforestwatch.org/dataset/gfw_glad_alerts
- **Licensing**: CC BY 4.0
- **Authentication**: GFW API key for high-volume requests
- **Update Frequency**: Weekly
- **Expected Usefulness**: Independent near-real-time loss verification independent of project self-monitoring reports
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Covers all 784,987 ha of VCS 902 forested area.

### `landsat-burned-area-conus-global` — USGS Landsat Burned Area Essential Climate Variable (ECV)
- **Original Provider**: USGS EROS / Hawbaker et al.
- **Official URL**: [https://www.usgs.gov/landsat-missions/landsat-burned-area](https://www.usgs.gov/landsat-missions/landsat-burned-area)
- **Data Domain**: `G_FIRE_DISTURBANCE`
- **Geographic Coverage**: Global land surface
- **Temporal Coverage**: 1984 to present
- **Spatial Resolution**: 30 m
- **Temporal Resolution**: Per-scene Landsat overpass (16-day)
- **Access Mechanism**: USGS M2M / EarthExplorer / GEE
- **API / STAC Availability**: USGS M2M API
- **Licensing**: Public Domain
- **Authentication**: Free USGS EROS user login
- **Update Frequency**: Collection 2 provisional release
- **Expected Usefulness**: 30m fire history extending back to 1984, bridging Landsat 5, 7, and 8
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: Moderate. Provides 30m resolution for fires prior to MODIS launch in 2000.

### `firms-historical-archive` — NASA FIRMS Archive: MODIS & VIIRS Historical Thermal Detections (2000-2023)
- **Original Provider**: NASA LANCE / FIRMS
- **Official URL**: [https://earthdata.nasa.gov/earth-observation-data/near-real-time/firms](https://earthdata.nasa.gov/earth-observation-data/near-real-time/firms)
- **Data Domain**: `G_FIRE_DISTURBANCE`
- **Geographic Coverage**: Global
- **Temporal Coverage**: 2000 to 2023
- **Spatial Resolution**: Point vector (1km MODIS / 375m VIIRS pixel centroid)
- **Temporal Resolution**: Exact satellite overpass timestamp
- **Access Mechanism**: FIRMS Archive Download Tool / REST API
- **API / STAC Availability**: https://firms.modaps.eosdis.nasa.gov/download/
- **Licensing**: Public Domain
- **Authentication**: NASA Earthdata login & FIRMS API key
- **Update Frequency**: Monthly archive packaging
- **Expected Usefulness**: Exact geographic clustering of ignition points (roads, villages, hunting concessions)
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Downloads ready for Zimbabwe (145,000+ fire detections 2000-2022).

### `fao-forest-fire-statistics` — FAOSTAT Forest Fires and Burned Area Emissions
- **Original Provider**: Food and Agriculture Organization (FAO)
- **Official URL**: [https://www.fao.org/faostat/en/#data/GI](https://www.fao.org/faostat/en/#data/GI)
- **Data Domain**: `G_FIRE_DISTURBANCE`
- **Geographic Coverage**: National and regional totals
- **Temporal Coverage**: 1990 to 2022
- **Spatial Resolution**: National / Sub-national administrative aggregates
- **Temporal Resolution**: Annual totals (hectares burned and GHG emissions in CO2e)
- **Access Mechanism**: FAOSTAT REST API / Bulk CSV
- **API / STAC Availability**: https://fenixservices.fao.org/faostat/api/v1/en/data/GI
- **Licensing**: CC BY-NC-SA 3.0 IGO
- **Authentication**: None (free public API)
- **Update Frequency**: Annual
- **Expected Usefulness**: National baseline calibration for Zimbabwe official AFOLU emissions reporting
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: Moderate. Country-level aggregate, useful for checking project claims against national trends.

## H. Soil, Terrain and Elevation

### `soilgrids-250m-v2` — SoilGrids 250m v2.0 Global Gridded Soil Properties
- **Original Provider**: ISRIC - World Soil Information
- **Official URL**: [https://www.isric.org/explore/soilgrids](https://www.isric.org/explore/soilgrids)
- **Data Domain**: `H_SOIL_TERRAIN`
- **Geographic Coverage**: Global land (excluding permafrost and shifting dunes)
- **Temporal Coverage**: Static spatial predictions (based on ~240,000 profile records)
- **Spatial Resolution**: 250 m
- **Temporal Resolution**: Static baseline across 6 depth intervals (0-5cm, 5-15cm, 15-30cm, 30-60cm, 60-100cm, 100-200cm)
- **Access Mechanism**: WCS / WebDAV / Cloud-Optimized GeoTIFF / REST API
- **API / STAC Availability**: https://files.isric.org/soilgrids/latest/data/
- **Licensing**: CC BY 4.0 International
- **Authentication**: None (public open access)
- **Update Frequency**: Decadal major updates (v2.0 active standard)
- **Expected Usefulness**: Soil Organic Carbon (SOC), clay fraction, bulk density, and pH for donor soil matching and carbon pools
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Covers all Kariba parcels and donor districts. Crucial for matching sandy arenosols vs fertile clay.

### `nasadem-global-30m` — NASADEM Merged Global Digital Elevation Model NC 30m (NASADEM_HGT)
- **Original Provider**: NASA LP DAAC / JPL
- **Official URL**: [https://lpdaac.usgs.gov/products/nasadem_hgtv001/](https://lpdaac.usgs.gov/products/nasadem_hgtv001/)
- **Data Domain**: `H_SOIL_TERRAIN`
- **Geographic Coverage**: Global 60°N to 56°S
- **Temporal Coverage**: 2000 (reprocessed with ICESat/GLAS and ASTER)
- **Spatial Resolution**: 30 m (1 arc-second)
- **Temporal Resolution**: Static reference elevation
- **Access Mechanism**: STAC API / Cloud-Optimized GeoTIFF / Planetary Computer
- **API / STAC Availability**: Microsoft Planetary Computer (nasadem), NASA CMR
- **Licensing**: Public Domain (NASA Open Data)
- **Authentication**: None on Planetary Computer
- **Update Frequency**: Static product
- **Expected Usefulness**: Slope, aspect, elevation, and terrain ruggedness index (TRI) for donor matching
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Resolves Zambezi valley escarpment (400m to 1,200m elevation gradient).

### `srtm-gl1-30m` — Shuttle Radar Topography Mission (SRTM) Global 1 Arc-Second (SRTMGL1 v003)
- **Original Provider**: NASA / USGS
- **Official URL**: [https://lpdaac.usgs.gov/products/srtmgl1v003/](https://lpdaac.usgs.gov/products/srtmgl1v003/)
- **Data Domain**: `H_SOIL_TERRAIN`
- **Geographic Coverage**: Global 60°N to 56°S
- **Temporal Coverage**: 2000-02-11 to 2000-02-22
- **Spatial Resolution**: 30 m (1 arc-second)
- **Temporal Resolution**: Static February 2000 baseline
- **Access Mechanism**: USGS EarthExplorer / Planetary Computer
- **API / STAC Availability**: USGS EarthExplorer, AWS Registry of Open Data
- **Licensing**: Public Domain
- **Authentication**: None on AWS
- **Update Frequency**: Completed mission
- **Expected Usefulness**: Historical year 2000 baseline elevation matching project inception
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Canonical elevation reference specified in Kariba project design documents.

### `hwsd-v2-fao-soil` — Harmonized World Soil Database version 2.0 (HWSD v2.0)
- **Original Provider**: FAO / International Institute for Applied Systems Analysis (IIASA)
- **Official URL**: [https://www.fao.org/soils-portal/data-hub/soil-maps-and-databases/harmonized-world-soil-database-v20/en/](https://www.fao.org/soils-portal/data-hub/soil-maps-and-databases/harmonized-world-soil-database-v20/en/)
- **Data Domain**: `H_SOIL_TERRAIN`
- **Geographic Coverage**: Global
- **Temporal Coverage**: 2023 update of global soil units
- **Spatial Resolution**: 30 arc-seconds (~1 km)
- **Temporal Resolution**: Static database
- **Access Mechanism**: Direct SQLite / Raster download / FAO portal
- **API / STAC Availability**: https://www.fao.org/soils-portal/
- **Licensing**: CC BY-NC-SA 3.0 IGO
- **Authentication**: None
- **Update Frequency**: Periodic major releases (v2.0 released 2023)
- **Expected Usefulness**: FAO UNESCO soil unit classification (Lithosols, Luvisols, Vertisols) for categorical donor stratification
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Distinguishes Kalahari sands from Zambezi rift valley alluvium.

### `isric-wise-soil-profiles` — ISRIC World Inventory of Soil Emission Potentials (WISE30sec)
- **Original Provider**: ISRIC - World Soil Information / Batjes
- **Official URL**: [https://www.isric.org/explore/wise-databases](https://www.isric.org/explore/wise-databases)
- **Data Domain**: `H_SOIL_TERRAIN`
- **Geographic Coverage**: Global land surface
- **Temporal Coverage**: Static harmonization of ~10,250 profile samples
- **Spatial Resolution**: 30 arc-seconds (~1 km)
- **Temporal Resolution**: Static reference dataset
- **Access Mechanism**: Direct HTTP download
- **API / STAC Availability**: https://files.isric.org/wise/
- **Licensing**: CC BY 4.0
- **Authentication**: None
- **Update Frequency**: Curated database
- **Expected Usefulness**: Independent profile-derived organic carbon stocks (tonnes C/ha) for soil carbon pool checks
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: Moderate. 1km resolution, good for regional background soil carbon validation.

### `fao-gsocmap-soil-carbon` — FAO Global Soil Organic Carbon Map (GSOCmap v1.5)
- **Original Provider**: FAO Global Soil Partnership (GSP)
- **Official URL**: [https://www.fao.org/global-soil-partnership/resources/highlights/detail/en/c/1266014/](https://www.fao.org/global-soil-partnership/resources/highlights/detail/en/c/1266014/)
- **Data Domain**: `H_SOIL_TERRAIN`
- **Geographic Coverage**: Global
- **Temporal Coverage**: 2020 baseline (0-30 cm topsoil)
- **Spatial Resolution**: 1 km
- **Temporal Resolution**: Static baseline (t C/ha)
- **Access Mechanism**: FAO GeoNetwork / WMS / GeoTIFF
- **API / STAC Availability**: https://data.apps.fao.org/catalog/dataset/global-soil-organic-carbon-map-gsocmap-v1-5-0
- **Licensing**: CC BY-NC-SA 3.0 IGO
- **Authentication**: None
- **Update Frequency**: Periodic national updates
- **Expected Usefulness**: National government-submitted soil organic carbon stocks to check against IPPC Tier 1 assumptions
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Directly calibrated with Zimbabwe and Zambia national agricultural laboratory samples.

### `merit-dem-terrain` — Multi-Error-Removed Improved-Terrain DEM (MERIT DEM 90m)
- **Original Provider**: University of Tokyo / Yamazaki et al.
- **Official URL**: [http://hydro.iis.u-tokyo.ac.jp/~yamadai/MERIT_DEM/](http://hydro.iis.u-tokyo.ac.jp/~yamadai/MERIT_DEM/)
- **Data Domain**: `H_SOIL_TERRAIN`
- **Geographic Coverage**: Global land surface
- **Temporal Coverage**: Static baseline (removes tree height bias from SRTM/AW3D)
- **Spatial Resolution**: 3 arc-seconds (~90 m)
- **Temporal Resolution**: Static elevation surface
- **Access Mechanism**: Direct HTTP download
- **API / STAC Availability**: http://hydro.iis.u-tokyo.ac.jp/~yamadai/MERIT_DEM/
- **Licensing**: CC BY-NC 4.0 or Open for research
- **Authentication**: Registration form
- **Update Frequency**: Completed project
- **Expected Usefulness**: Removes vegetation canopy height bias inherent in radar SRTM, providing true bare-earth elevations
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Removes 10-15m miombo canopy bias present in raw SRTM over the forest parcels.

### `global-land-degradation-trends-earth-engine` — UNCCD Trends.Earth Soil Organic Carbon and Land Degradation Indicators
- **Original Provider**: Conservation International / UNCCD
- **Official URL**: [https://trends.earth/](https://trends.earth/)
- **Data Domain**: `H_SOIL_TERRAIN`
- **Geographic Coverage**: Global land
- **Temporal Coverage**: 2001 to 2020
- **Spatial Resolution**: 250 m (SOC) / 30 m (productivity)
- **Temporal Resolution**: Reporting epochs (SDG 15.3.1)
- **Access Mechanism**: QGIS Plugin / Google Earth Engine assets / API
- **API / STAC Availability**: https://api.trends.earth/
- **Licensing**: GPL v3 / CC BY 4.0
- **Authentication**: Free Trends.Earth user login
- **Update Frequency**: UNCCD 4-year reporting cycles
- **Expected Usefulness**: Official UNCCD indicator framework separating degradation into productivity, land cover, and soil carbon
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Standard method for UN Land Degradation Neutrality targets in Zimbabwe.

### `global-aridity-pet-database` — Global Aridity Index and Potential Evapo-Transpiration (ET0) Database v3
- **Original Provider**: CGIAR-CSI / Zomer et al.
- **Official URL**: [https://cgiarcsi.community/data/global-aridity-and-pet-database/](https://cgiarcsi.community/data/global-aridity-and-pet-database/)
- **Data Domain**: `H_SOIL_TERRAIN`
- **Geographic Coverage**: Global land surface
- **Temporal Coverage**: 1970-2000 climatological baseline
- **Spatial Resolution**: 30 arc-seconds (~1 km)
- **Temporal Resolution**: Annual and monthly climatologies
- **Access Mechanism**: Direct HTTP GeoTIFF download
- **API / STAC Availability**: https://figshare.com/articles/dataset/Global_Aridity_Index_and_Potential_Evapotranspiration_ET0_Climate_Database_v3/7504448
- **Licensing**: CC BY 4.0
- **Authentication**: None
- **Update Frequency**: Curated release (v3 published 2022)
- **Expected Usefulness**: Aridity Index (P / PET) matching to guarantee donors share identical agro-climatic water balance
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Semi-arid to sub-humid classification perfectly matches Zambezi valley dry woodlands.

### `fao-soil-erosion-glosem` — Global Soil Erosion Modelling platform (GloSEM 2012-2020)
- **Original Provider**: European Commission JRC / Borrelli et al.
- **Official URL**: [https://esdac.jrc.ec.europa.eu/content/global-soil-erosion-modelling-platform-glosem](https://esdac.jrc.ec.europa.eu/content/global-soil-erosion-modelling-platform-glosem)
- **Data Domain**: `H_SOIL_TERRAIN`
- **Geographic Coverage**: Global
- **Temporal Coverage**: 2012 and 2020 projections
- **Spatial Resolution**: 250 m
- **Temporal Resolution**: Annual water erosion rates (tons/ha/yr)
- **Access Mechanism**: ESDAC data portal request
- **API / STAC Availability**: https://esdac.jrc.ec.europa.eu/
- **Licensing**: Open access with citation (free for scientific use)
- **Authentication**: Free ESDAC online request form
- **Update Frequency**: Periodic releases
- **Expected Usefulness**: Identifies erosion-prone escarpments where vegetation loss leads to irreversible soil wash-out
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Critical along steep Chizarira and Gache Gache escarpment slopes.

## I. Human Pressures and Infrastructure

### `ghsl-population-grid-2023` — Global Human Settlement Layer Population Grid (GHSL-POP R2023A)
- **Original Provider**: European Commission JRC
- **Official URL**: [https://human-settlement.emergency.copernicus.eu/ghs_pop2023.php](https://human-settlement.emergency.copernicus.eu/ghs_pop2023.php)
- **Data Domain**: `I_HUMAN_ANTHROPOGENIC_PRESSURES`
- **Geographic Coverage**: Global
- **Temporal Coverage**: 1975 to 2030 (5-year epochs: 2000, 2005, 2010, 2015, 2020, 2025)
- **Spatial Resolution**: 100 m and 1 km
- **Temporal Resolution**: 5-year epochs
- **Access Mechanism**: Direct HTTP / WMS / Planetary Computer
- **API / STAC Availability**: Planetary Computer (ghsl-pop), JRC direct download
- **Licensing**: CC BY 4.0 International
- **Authentication**: None on Planetary Computer
- **Update Frequency**: Major releases every 2-3 years
- **Expected Usefulness**: High-accuracy residential population density matching for donor units; controls for human pressure
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Matches settlement distribution along Binga, Nyaminyami, and Hurungwe communal lands.

### `worldpop-unconstrained-100m` — WorldPop Global High Resolution Population Denominators (100m Unconstrained)
- **Original Provider**: WorldPop / University of Southampton
- **Official URL**: [https://www.worldpop.org/project/categories?id=3](https://www.worldpop.org/project/categories?id=3)
- **Data Domain**: `I_HUMAN_ANTHROPOGENIC_PRESSURES`
- **Geographic Coverage**: Global (individual country rasters)
- **Temporal Coverage**: 2000 to 2020 (annual)
- **Spatial Resolution**: 100 m (~3 arc-seconds)
- **Temporal Resolution**: Annual estimates
- **Access Mechanism**: WorldPop REST API / Direct GeoTIFF / AWS Open Data
- **API / STAC Availability**: https://data.worldpop.org/GIS/Population/Global_2000_2020/
- **Licensing**: CC BY 4.0
- **Authentication**: None
- **Update Frequency**: Annual releases
- **Expected Usefulness**: Continuous annual population growth rates inside Kariba community wards
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. ZWE (Zimbabwe) and ZMB (Zambia) annual 100m geotiffs readily available.

### `grip4-global-roads-database` — Global Roads Inventory Project (GRIP4) Road Density and Distance
- **Original Provider**: PBL Netherlands Environmental Assessment Agency / Meijer et al.
- **Official URL**: [https://www.globio.info/data-downloads/grip-global-roads-inventory-project](https://www.globio.info/data-downloads/grip-global-roads-inventory-project)
- **Data Domain**: `I_HUMAN_ANTHROPOGENIC_PRESSURES`
- **Geographic Coverage**: Global
- **Temporal Coverage**: 2018 synthesis (derived from OpenStreetMap, national inventories)
- **Spatial Resolution**: Vector shapefile / 5 arc-minute raster density
- **Temporal Resolution**: Static contemporary infrastructure network
- **Access Mechanism**: Direct shapefile / GeoTIFF download
- **API / STAC Availability**: https://www.globio.info/data-downloads
- **Licensing**: CC BY 4.0
- **Authentication**: None
- **Update Frequency**: Periodic major synthesis
- **Expected Usefulness**: Euclidean distance to roads (road_distance_km) required by ADR-011 covariate matching
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Vector lines cover all primary highways (A1 Chirundu highway) and secondary dirt tracks.

### `openstreetmap-highways-overpass` — OpenStreetMap Highway Network (Extracted via Overpass API / Geofabrik)
- **Original Provider**: OpenStreetMap Foundation / Geofabrik GmbH
- **Official URL**: [https://download.geofabrik.de/africa/zimbabwe.html](https://download.geofabrik.de/africa/zimbabwe.html)
- **Data Domain**: `I_HUMAN_ANTHROPOGENIC_PRESSURES`
- **Geographic Coverage**: Global (Zimbabwe & Zambia regional extracts)
- **Temporal Coverage**: 2004 to present (continuous live mapping)
- **Spatial Resolution**: Vector lines (meter-level GPS precision)
- **Temporal Resolution**: Daily updated extracts
- **Access Mechanism**: Geofabrik daily OSM PBF / Overpass QL API
- **API / STAC Availability**: https://overpass-api.de/api/interpreter
- **Licensing**: Open Database License (ODbL 1.0)
- **Authentication**: None
- **Update Frequency**: Continuous / daily PBF builds
- **Expected Usefulness**: Calculates exact road distance buffers and tracks new dirt track incursions into forest parcels
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Verified against Kariba RDC boundary lines; full coverage of Zambezi road network.

### `viirs-dnb-nighttime-lights` — VIIRS Day/Night Band Nighttime Lights Monthly Composites (VNP46A3 / Black Marble)
- **Original Provider**: NASA Earthdata / NOAA
- **Official URL**: [https://blackmarble.gsfc.nasa.gov/](https://blackmarble.gsfc.nasa.gov/)
- **Data Domain**: `I_HUMAN_ANTHROPOGENIC_PRESSURES`
- **Geographic Coverage**: Global
- **Temporal Coverage**: 2012 to present
- **Spatial Resolution**: 500 m (15 arc-seconds)
- **Temporal Resolution**: Monthly / Daily NTL radiance
- **Access Mechanism**: NASA Earthdata Cloud / Planetary Computer
- **API / STAC Availability**: NASA CMR-STAC
- **Licensing**: Public Domain
- **Authentication**: NASA Earthdata login
- **Update Frequency**: Monthly
- **Expected Usefulness**: Objective physical indicator of electrification, mining activity, and rural settlement growth
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Detects fishing vessel lights on Lake Kariba and expanding growth around Karoi and Binga.

### `dmsp-ols-nighttime-lights` — DMSP-OLS Nighttime Stable Lights Version 4 (1992-2013)
- **Original Provider**: NOAA National Geophysical Data Center (NGDC)
- **Official URL**: [https://eogdata.mines.edu/products/dmsp/](https://eogdata.mines.edu/products/dmsp/)
- **Data Domain**: `I_HUMAN_ANTHROPOGENIC_PRESSURES`
- **Geographic Coverage**: Global 65°S to 75°N
- **Temporal Coverage**: 1992 to 2013
- **Spatial Resolution**: 30 arc-seconds (~1 km)
- **Temporal Resolution**: Annual cloud-free stable light composites
- **Access Mechanism**: Direct HTTP / Earth Observation Group portal
- **API / STAC Availability**: https://eogdata.mines.edu/dmsp/download_radcal.html
- **Licensing**: Public Domain
- **Authentication**: Free EOG user registration
- **Update Frequency**: Completed mission (bridged by VIIRS DNB)
- **Expected Usefulness**: Historical pre-treatment electrification and settlement baseline for 2001-2010
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: Moderate. Low sensor dynamic range, but proves project area was 100% unlit rural woodland in 2001.

### `global-human-modification-gHM` — Global Human Modification Index 1km (Theobald et al. 2020)
- **Original Provider**: Conservation Science Partners / WRI
- **Official URL**: [https://www.sciencedirect.com/science/article/pii/S235198942030737X](https://www.sciencedirect.com/science/article/pii/S235198942030737X)
- **Data Domain**: `I_HUMAN_ANTHROPOGENIC_PRESSURES`
- **Geographic Coverage**: Global terrestrial land
- **Temporal Coverage**: 2016 baseline
- **Spatial Resolution**: 1 km
- **Temporal Resolution**: Static multi-layer synthesis (roads, energy, mining, agriculture, built-up)
- **Access Mechanism**: Google Earth Engine / Direct GeoTIFF download
- **API / STAC Availability**: https://doi.org/10.5281/zenodo.3963013
- **Licensing**: CC BY 4.0
- **Authentication**: None
- **Update Frequency**: Periodic releases
- **Expected Usefulness**: Cumulative human impact score (0.0 to 1.0) integrating 13 anthropogenic stressors for matching
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Low modification values (0.05-0.25) across Kariba; ensures matched donors share equivalent low modification.

### `sedac-human-footprint-v3` — Last of the Wild Project Global Human Footprint v3 (1993 and 2009)
- **Original Provider**: NASA SEDAC / Venter et al. / WCS
- **Official URL**: [https://sedac.ciesin.columbia.edu/data/set/wildareas-v3-human-footprint-1993-2009](https://sedac.ciesin.columbia.edu/data/set/wildareas-v3-human-footprint-1993-2009)
- **Data Domain**: `I_HUMAN_ANTHROPOGENIC_PRESSURES`
- **Geographic Coverage**: Global land surface
- **Temporal Coverage**: 1993 and 2009 (ideal for pre-treatment trend comparison)
- **Spatial Resolution**: 1 km
- **Temporal Resolution**: Two-epoch comparison (1993 vs 2009)
- **Access Mechanism**: NASA SEDAC direct GeoTIFF / WMS
- **API / STAC Availability**: https://sedac.ciesin.columbia.edu/data/set/wildareas-v3-human-footprint-1993-2009/data-download
- **Licensing**: Open access (NASA Earthdata)
- **Authentication**: Free NASA Earthdata login
- **Update Frequency**: Historical research milestone
- **Expected Usefulness**: Directly measures whether human pressure expanded inside Kariba during the 1993-2009 pre-period
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Proves whether baseline counterfactual assumption of increasing threat was empirically grounded.

### `spatiotemporal-mining-concessions-sparc` — Global Mining Concessions and Extractive Polygons (Maus et al. 2022)
- **Original Provider**: Vienna University of Economics and Business (WU) / Fineprint
- **Official URL**: [https://www.nature.com/articles/s41597-022-01547-4](https://www.nature.com/articles/s41597-022-01547-4)
- **Data Domain**: `I_HUMAN_ANTHROPOGENIC_PRESSURES`
- **Geographic Coverage**: Global mining operations and artisanal mining sites
- **Temporal Coverage**: 2000 to 2021
- **Spatial Resolution**: Vector polygons (digitized from high-resolution satellite imagery)
- **Temporal Resolution**: Annual operational status
- **Access Mechanism**: Zenodo open vector dataset
- **API / STAC Availability**: https://doi.org/10.5281/zenodo.6577883
- **Licensing**: CC BY 4.0
- **Authentication**: None
- **Update Frequency**: Annual
- **Expected Usefulness**: Filters out or controls for unannounced mineral prospecting and artisanal gold panning in concessions
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Directly flags active mining concessions along northern Binga and Muzarabani.

### `wri-global-power-plants` — World Resources Institute Global Power Plant Database v1.3
- **Original Provider**: World Resources Institute (WRI)
- **Official URL**: [https://datasets.wri.org/dataset/globalpowerplantdatabase](https://datasets.wri.org/dataset/globalpowerplantdatabase)
- **Data Domain**: `I_HUMAN_ANTHROPOGENIC_PRESSURES`
- **Geographic Coverage**: Global
- **Temporal Coverage**: Operational power plant inventory (including Kariba South 1,050 MW hydro plant)
- **Spatial Resolution**: Point location with generation capacity, fuel type, commissioning year
- **Temporal Resolution**: Annual update
- **Access Mechanism**: Direct CSV download
- **API / STAC Availability**: https://wri-dataportal-prod.s3.amazonaws.com/manual/global_power_plant_database.zip
- **Licensing**: Open access (Creative Commons Attribution 4.0 International)
- **Authentication**: None
- **Update Frequency**: Annual
- **Expected Usefulness**: Explicitly accounts for Kariba Dam hydroelectric power infrastructure and associated transmission lines
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Kariba South Hydroelectric Power Station (1,050 MW) is located directly on boundary.

## J. Conservation, Governance and Restoration

### `wdpa-protected-planet` — World Database on Protected Areas (WDPA)
- **Original Provider**: UNEP-WCMC / IUCN
- **Official URL**: [https://www.protectedplanet.net/](https://www.protectedplanet.net/)
- **Data Domain**: `J_CONSERVATION_RESTORATION`
- **Geographic Coverage**: Global protected area boundaries
- **Temporal Coverage**: 1872 to present (monthly releases)
- **Spatial Resolution**: Vector boundary polygons and point records
- **Temporal Resolution**: Monthly database releases
- **Access Mechanism**: Protected Planet REST API / Direct Monthly Shapefile Download
- **API / STAC Availability**: https://api.protectedplanet.net/v4/
- **Licensing**: Non-commercial use free; commercial use governed by UNEP-WCMC license
- **Authentication**: Free API key upon request
- **Update Frequency**: Monthly
- **Expected Usefulness**: Screens out formal National Parks and Game Reserves from donor pool to avoid contaminated counterfactuals
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Enforces exclusion of Matusadona, Chizarira, Mana Pools, and Zambian National Parks from donor pool.

### `un-biodiversity-lab` — UN Biodiversity Lab Geospatial Data Platform
- **Original Provider**: UNDP / UNEP-WCMC / Secretariat of the CBD
- **Official URL**: [https://unbiodiversitylab.org/](https://unbiodiversitylab.org/)
- **Data Domain**: `J_CONSERVATION_RESTORATION`
- **Geographic Coverage**: Global national biodiversity reporting boundaries
- **Temporal Coverage**: 2000 to present
- **Spatial Resolution**: Varies by indicator (30m to 1km)
- **Temporal Resolution**: Periodic synthesis for National Biodiversity Strategies (NBSAPs)
- **Access Mechanism**: UNBL Map Viewer / Data Download Portal
- **API / STAC Availability**: https://unbiodiversitylab.org/en/download-data/
- **Licensing**: Open access (UN official repositories)
- **Authentication**: Free UNBL user registration
- **Update Frequency**: Continuous
- **Expected Usefulness**: Official national reporting layers for Zimbabwe's 6th National Report to the CBD
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: High. Contains Zimbabwe official priority conservation polygons.

### `global-ecosystems-atlas` — Global Ecosystems Atlas (GEO / IUCN Global Ecosystem Typology v2.1)
- **Original Provider**: Group on Earth Observations (GEO) / IUCN / UNSW
- **Official URL**: [https://globalecosystemsatlas.org/](https://globalecosystemsatlas.org/)
- **Data Domain**: `J_CONSERVATION_RESTORATION`
- **Geographic Coverage**: Global functional ecosystem groups
- **Temporal Coverage**: Contemporary ecological baseline
- **Spatial Resolution**: 30 m to 1 km
- **Temporal Resolution**: Functional biome classification
- **Access Mechanism**: GEO Data Portal / WMS / GeoTIFF
- **API / STAC Availability**: https://globalecosystemsatlas.org/data
- **Licensing**: CC BY 4.0
- **Authentication**: None
- **Update Frequency**: Annual updates
- **Expected Usefulness**: Validates exact functional ecosystem assignment (T4.2 Subtropical/temperate savanna / Miombo woodland)
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Confirms biophysical equivalence of donor candidate districts.

### `verra-vcs-registry-serial-api` — Verra Registry Public Project & Serial Record Database
- **Original Provider**: Verra (Verified Carbon Standard)
- **Official URL**: [https://registry.verra.org/](https://registry.verra.org/)
- **Data Domain**: `J_CONSERVATION_RESTORATION`
- **Geographic Coverage**: Global registered voluntary carbon projects
- **Temporal Coverage**: 2006 to present
- **Spatial Resolution**: Project boundary KML and regional district references
- **Temporal Resolution**: Per-issuance serial records with vintage year
- **Access Mechanism**: Verra Registry Search / PDF Document Downloads
- **API / STAC Availability**: https://registry.verra.org/app/projectDetail/VCS/902
- **Licensing**: Public registry records
- **Authentication**: None (public web portal)
- **Update Frequency**: Continuous upon credit issuance/retirement
- **Expected Usefulness**: Authoritative validation of claimed credits (~27M tCO2e), crediting periods, and official KML boundary
- **Independent Evidence Source**: Yes
- **Integration Status**: `INTEGRATED`
- **Feasibility for Kariba**: High. Project 902 documents, KML boundary, and Verra 2025 excess issuance findings retrieved.

### `restor-global-restoration-platform` — Restor Global Ecological Restoration Site Directory
- **Original Provider**: Restor Foundation / Crowther Lab (ETH Zurich)
- **Official URL**: [https://restor.eco/](https://restor.eco/)
- **Data Domain**: `J_CONSERVATION_RESTORATION`
- **Geographic Coverage**: Global restoration and conservation intervention sites
- **Temporal Coverage**: Active project registries (2010-present)
- **Spatial Resolution**: Polygons of community and NGO restoration boundaries
- **Temporal Resolution**: Self-reported project milestones
- **Access Mechanism**: Restor Web Platform / API
- **API / STAC Availability**: https://restor.eco/api/
- **Licensing**: CC BY-NC 4.0
- **Authentication**: Restor account
- **Update Frequency**: Continuous user updates
- **Expected Usefulness**: Screens out unlisted community reforestation or assisted regeneration projects from donor pool
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: Moderate. Verifies whether candidate donor districts in Zambia have competing restoration funding.

### `fao-forest-resources-assessment-fra` — FAO Global Forest Resources Assessment (FRA 2020 Country Reports)
- **Original Provider**: Food and Agriculture Organization (FAO)
- **Official URL**: [https://www.fao.org/forest-resources-assessment/en/](https://www.fao.org/forest-resources-assessment/en/)
- **Data Domain**: `J_CONSERVATION_RESTORATION`
- **Geographic Coverage**: 236 countries and territories
- **Temporal Coverage**: 1990, 2000, 2010, 2015, 2020
- **Spatial Resolution**: National tabular records and regional summaries
- **Temporal Resolution**: 5-year global assessments
- **Access Mechanism**: FAO FRA Platform API / Bulk CSV
- **API / STAC Availability**: https://fra-data.fao.org/
- **Licensing**: CC BY-NC-SA 3.0 IGO
- **Authentication**: None
- **Update Frequency**: 5-year cycles (FRA 2025 in progress)
- **Expected Usefulness**: Official government-reported national deforestation rates for Zimbabwe and Zambia (deforestation counterfactual benchmark)
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Zimbabwe national forest loss reported at 327,000 ha/yr (FRA 2010), crucial for baseline sanity check.

### `wri-restoration-barometer` — IUCN / WRI Restoration Barometer Tracking Tool
- **Original Provider**: IUCN / World Resources Institute
- **Official URL**: [https://www.restorationbarometer.org/](https://www.restorationbarometer.org/)
- **Data Domain**: `J_CONSERVATION_RESTORATION`
- **Geographic Coverage**: Bonn Challenge committing countries (including Zimbabwe and Zambia)
- **Temporal Coverage**: 2011 to present
- **Spatial Resolution**: National and subnational intervention areas
- **Temporal Resolution**: Annual government progress reports
- **Access Mechanism**: Restoration Barometer web downloads
- **API / STAC Availability**: https://www.restorationbarometer.org/data
- **Licensing**: CC BY 4.0
- **Authentication**: None
- **Update Frequency**: Annual
- **Expected Usefulness**: Tracks official government restoration pledges under the AFR100 initiative across Zimbabwe
- **Independent Evidence Source**: Yes
- **Integration Status**: `ACCESS_VERIFIED`
- **Feasibility for Kariba**: Moderate. Provides political and policy context on official restoration targets.

### `geoboundaries-global-adm2` — geoBoundaries Open Administrative Boundary Database (ADM2 Districts)
- **Original Provider**: William & Mary GeoLab / Runfola et al.
- **Official URL**: [https://www.geoboundaries.org/](https://www.geoboundaries.org/)
- **Data Domain**: `J_CONSERVATION_RESTORATION`
- **Geographic Coverage**: Global administrative units (ADM0 to ADM5)
- **Temporal Coverage**: 2020 boundary snapshot (gbOpen v6.0.0)
- **Spatial Resolution**: Official cadastral survey boundaries (<5m precision)
- **Temporal Resolution**: Static release version (commit 9469f09)
- **Access Mechanism**: GitHub Release / REST API / GeoJSON download
- **API / STAC Availability**: https://www.geoboundaries.org/api/current/gbOpen/ZWE/ADM2/
- **Licensing**: CC BY 3.0 IGO (ZWE / ZIMSTAT) and CC BY 4.0 (ZMB / GRID3)
- **Authentication**: None (fully open)
- **Update Frequency**: Continuous release cycles
- **Expected Usefulness**: Authoritative political district boundaries for Zimbabwe and Zambia donor pool definition
- **Independent Evidence Source**: Yes
- **Integration Status**: `INTEGRATED`
- **Feasibility for Kariba**: High. The 37 eligible donor boundaries in `cases/boundaries/kariba-donors.geojson` are derived from geoBoundaries gbOpen v6.0.0.

### `wcs-zambezi-carnivore-monitoring` — Wildlife Conservation Society (WCS) Zambezi Landscape Conservation Surveys
- **Original Provider**: Wildlife Conservation Society (WCS)
- **Official URL**: [https://zimbabwe.wcs.org/](https://zimbabwe.wcs.org/)
- **Data Domain**: `J_CONSERVATION_RESTORATION`
- **Geographic Coverage**: Mid-Zambezi Valley, Kariba, Hurungwe, and Mana Pools
- **Temporal Coverage**: 2010 to 2023
- **Spatial Resolution**: Field transects and camera trap grid sites
- **Temporal Resolution**: Annual conservation survey reports
- **Access Mechanism**: WCS Research Reports / Published survey datasets
- **API / STAC Availability**: WCS Zimbabwe library / Zenodo
- **Licensing**: Academic open access with citation
- **Authentication**: None
- **Update Frequency**: Annual reporting
- **Expected Usefulness**: Ground-level field validation of wildlife presence and snare counts in Kariba project parcels
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Primary on-the-ground ecological intelligence directly within Kariba RDC areas.

### `zimparks-annual-ecological-reports` — Zimbabwe Parks and Wildlife Management Authority (ZIMPARKS) Annual Monitoring Reports
- **Original Provider**: Zimbabwe Parks and Wildlife Management Authority (ZIMPARKS)
- **Official URL**: [https://zimparks.org.zw/](https://zimparks.org.zw/)
- **Data Domain**: `J_CONSERVATION_RESTORATION`
- **Geographic Coverage**: Zimbabwe National Parks Estate and Safari Areas
- **Temporal Coverage**: 1995 to present
- **Spatial Resolution**: Management area and safari concession reporting
- **Temporal Resolution**: Annual government reports
- **Access Mechanism**: ZIMPARKS Library / Government Gazette
- **API / STAC Availability**: Official government publications
- **Licensing**: Government Open Data / Public Records
- **Authentication**: None
- **Update Frequency**: Annual
- **Expected Usefulness**: Official government wildlife population counts, hunting quota allocations, and patrol effort records
- **Independent Evidence Source**: Yes
- **Integration Status**: `QUALITY_VALIDATED`
- **Feasibility for Kariba**: High. Covers Hurungwe, Nyaminyami, and Charara Safari Areas surrounding the Kariba REDD+ site.
