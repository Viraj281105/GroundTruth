"""Scientific Evidence Registry for environmental observations and data sources.

This registry is the single source of truth for *what GroundTruth can honestly say about
each dataset*. It is consumed by ``GET /evidence-registry`` and by ``GET /health``.

Truthfulness rules (AGENTS.md R6/R7, "fail closed"):

- ``is_operational_integration`` is True only for a source with an automated ingestion path
  in code (``ingestion_mode == automated_operational``) that has been validated
  (``validation_status == validated``) and is not blocked. Nothing else may claim it.
- A quality or completeness number is reported only when it was measured from data that was
  actually retrieved (``quality_measured``); otherwise it is ``None``. No invented numbers.
- ``retrieval_timestamp`` / ``content_hash`` are ``None`` when nothing was retrieved. Where a
  local artefact exists, its hash is computed from the file at import time.
- Synthetic benchmarks are ``synthetic_simulated`` and are never usable for real analysis.
- ``assert_dataset_allowed_for_production`` is the gate real-data analysis paths must call.

Lifecycle phases:
- DISCOVERED: catalogued; no retrieval and no ingestion code exercised.
- ACCESSIBLE: endpoint reachable / partial retrieval; not an integrated, validated dataset.
- INTEGRATED: data is staged locally (manually or automatically) and readable by the platform.
- VALIDATED: scientifically validated for causal use (requires ``validation_status=validated``).
- QUARANTINED: rejected for integrity failures or fabrication; never loadable.

Privacy: the registry holds public reference metadata only (providers, licences, coverage,
hashes of public artefacts). It contains no tenant, project or user data.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from groundtruth.contracts.errors import DataUnavailableError


class SourceLifecycle(StrEnum):
    """Explicit lifecycle phase of an environmental data source."""

    DISCOVERED = "discovered"
    ACCESSIBLE = "accessible"
    INTEGRATED = "integrated"
    VALIDATED = "validated"
    QUARANTINED = "quarantined"


class IngestionMode(StrEnum):
    """How (and whether) data from a source actually reaches the platform."""

    AUTOMATED_OPERATIONAL = "automated_operational"
    MANUAL_STAGING = "manual_staging"
    CURATED_VECTOR = "curated_vector"
    ACCESSIBLE_UNVALIDATED = "accessible_unvalidated"
    SCAFFOLDED = "scaffolded"
    QUARANTINED = "quarantined"
    SYNTHETIC_SIMULATED = "synthetic_simulated"


class ValidationStatus(StrEnum):
    """Whether the source's data has been validated for analytical use."""

    VALIDATED = "validated"
    UNVALIDATED = "unvalidated"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


class ModalityType(StrEnum):
    """Sensor or observation modality."""

    OPTICAL_SURFACE_REFLECTANCE = "optical_surface_reflectance"
    GRIDDED_METEOROLOGY = "gridded_meteorology"
    SURFACE_TEMPERATURE = "surface_temperature"
    SPATIAL_VECTOR_POLYGONS = "spatial_vector_polygons"
    SPACEBORNE_LIDAR = "spaceborne_lidar"
    SYNTHETIC_APERTURE_RADAR = "synthetic_aperture_radar"
    SYNTHETIC_BENCHMARK = "synthetic_benchmark"
    AIR_GAPPED_QUARANTINE = "air_gapped_quarantine"


class ProductionAnalysisBlockedError(DataUnavailableError, PermissionError):
    """A dataset is not permitted to feed production (real-data) analysis."""


@dataclass(frozen=True)
class ProcessingStep:
    """A single deterministic transformation applied to raw source data."""

    step_name: str
    algorithm: str
    parameters: dict[str, Any]
    output_variable: str
    timestamp: str | None


_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_REPO_ROOT = Path(__file__).resolve().parents[6]


@dataclass(frozen=True)
class EvidenceSource:
    """Registry entry for an environmental observation feed, with truthful classification."""

    source_id: str
    title: str
    provider: str
    source_url: str
    dataset_identifier: str
    version: str
    license: str
    permitted_usage: str
    modality: ModalityType
    spatial_coverage: str
    temporal_coverage_start: str
    temporal_coverage_end: str
    spatial_resolution: str
    temporal_resolution: str
    acquisition_date: str | None
    retrieval_timestamp: str | None  # None => never retrieved
    processing_history: list[ProcessingStep]
    data_quality_score: float | None  # 0-100, only if quality_measured
    completeness_percentage: float | None  # 0-100, only if quality_measured
    missingness_summary: str
    content_hash: str | None  # sha256 of a real local artefact, else None
    lifecycle: SourceLifecycle
    is_operational_integration: bool
    sutva_compliant: bool
    quarantine_reason: str | None = None
    ingestion_mode: IngestionMode = IngestionMode.SCAFFOLDED
    notes: str = ""
    validation_status: ValidationStatus = ValidationStatus.UNVALIDATED
    validation_evidence: str = "none"
    blocked_for_production_analysis: bool = True
    blocked_reason: str | None = None
    quality_measured: bool = False
    quality_note: str = "Not measured: no quality metric has been computed from ingested data."
    retrieval_status: str = "not_retrieved"  # "retrieved" | "not_retrieved"
    retrieval_provenance: str | None = None
    content_hash_scope: str | None = None
    retrieved_temporal_coverage: str | None = None
    local_artifact_paths: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        mode = IngestionMode(self.ingestion_mode)  # rejects stale/unknown vocabulary
        ValidationStatus(self.validation_status)
        if self.is_operational_integration and not (
            mode == IngestionMode.AUTOMATED_OPERATIONAL
            and self.validation_status == ValidationStatus.VALIDATED
            and not self.blocked_for_production_analysis
        ):
            raise ValueError(
                f"{self.source_id}: is_operational_integration requires automated_operational "
                "ingestion, validation_status=validated and not blocked."
            )
        if (self.lifecycle == SourceLifecycle.QUARANTINED) != (mode == IngestionMode.QUARANTINED):
            raise ValueError(f"{self.source_id}: quarantine lifecycle and mode must agree.")
        if self.modality == ModalityType.SYNTHETIC_BENCHMARK and mode != (
            IngestionMode.SYNTHETIC_SIMULATED
        ):
            raise ValueError(f"{self.source_id}: synthetic data must be synthetic_simulated.")
        if (
            mode
            in (
                IngestionMode.SCAFFOLDED,
                IngestionMode.QUARANTINED,
                IngestionMode.SYNTHETIC_SIMULATED,
                IngestionMode.ACCESSIBLE_UNVALIDATED,
            )
            and not self.blocked_for_production_analysis
        ):
            raise ValueError(f"{self.source_id}: mode {mode.value} must be blocked.")
        if self.blocked_for_production_analysis and not self.blocked_reason:
            raise ValueError(f"{self.source_id}: blocked source needs a blocked_reason.")
        if (
            self.lifecycle == SourceLifecycle.VALIDATED
            and self.validation_status != ValidationStatus.VALIDATED
        ):
            raise ValueError(f"{self.source_id}: validated lifecycle needs validation_status.")
        if self.validation_status == ValidationStatus.VALIDATED and (
            not self.validation_evidence or self.validation_evidence.lower() == "none"
        ):
            raise ValueError(f"{self.source_id}: validated status needs validation_evidence.")
        if (
            self.data_quality_score is not None or self.completeness_percentage is not None
        ) and not self.quality_measured:
            raise ValueError(f"{self.source_id}: unmeasured quality numbers are not allowed.")
        if self.retrieval_timestamp is not None and self.retrieval_status != "retrieved":
            raise ValueError(f"{self.source_id}: retrieval_timestamp requires retrieved status.")
        if self.content_hash is not None and not _SHA256_RE.match(self.content_hash):
            raise ValueError(f"{self.source_id}: content_hash must be a real sha256 digest.")

    def to_dict(self) -> dict[str, Any]:
        """Convert entry to JSON-serializable dictionary."""
        data = asdict(self)
        data["local_artifact_paths"] = list(self.local_artifact_paths)
        data["artifacts_present"] = self.artifacts_present()
        return data

    def artifacts_present(self) -> bool | None:
        """True/False if the declared local artefacts exist; None if none are declared."""
        if not self.local_artifact_paths:
            return None
        return all((_REPO_ROOT / p).is_file() for p in self.local_artifact_paths)


# ---------------------------------------------------------------------------
# Helpers that read REAL local artefacts (never fabricate)
# ---------------------------------------------------------------------------


def _sha256_of(rel_path: str) -> str | None:
    path = _REPO_ROOT / rel_path
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _json_of(rel_path: str) -> dict[str, Any]:
    try:
        loaded = json.loads((_REPO_ROOT / rel_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _retrieved(timestamp: str | None) -> str:
    return "retrieved" if timestamp else "not_retrieved"


_STAC_CACHE = "data/processed/stac_cache/kariba-redd__ndvi.json"
_CLIMATE_CACHE = "data/processed/climate_cache/kariba_chirps_climate.json"
_DONOR_GEOJSON = "cases/boundaries/kariba-donors.geojson"
_DONOR_PROVENANCE = "cases/boundaries/kariba-donors.provenance.json"
_SYNTH_FIXTURE = "data/synthetic_fixtures/kariba_synthetic_benchmark.json"


def _build_initial_registry() -> list[EvidenceSource]:
    stac = _json_of(_STAC_CACHE)
    stac_retrieved = (stac.get("provenance") or {}).get("retrieved_at") if stac else None
    climate = _json_of(_CLIMATE_CACHE)
    climate_retrieved = climate.get("retrieved_at") if climate else None
    csrc = climate.get("sources", {}) if climate else {}
    chirps_meta = csrc.get("chirps_v2_monthly", {})
    power_meta = csrc.get("nasa_power_merra2_monthly", {})
    donors_prov = _json_of(_DONOR_PROVENANCE)
    donors_retrieved = donors_prov.get("retrieved_at")

    chirps_req = chirps_meta.get("total_months_requested")
    chirps_got = chirps_meta.get("total_months_retrieved")
    chirps_missing = chirps_meta.get("missing_months_after_upstream", [])
    chirps_completeness = (
        round(100.0 * chirps_got / chirps_req, 1) if chirps_req and chirps_got else None
    )
    power_req = 516 if power_meta else None
    power_got = power_meta.get("total_months_retrieved")
    power_completeness = (
        round(100.0 * power_got / power_req, 1) if power_req and power_got else None
    )

    return [
        EvidenceSource(
            source_id="sentinel-2-msi-l2a",
            title="Copernicus Sentinel-2 MSI Level-2A Surface Reflectance (Planetary Computer STAC)",
            provider="ESA / Copernicus via Microsoft Planetary Computer",
            source_url="https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a",
            dataset_identifier="sentinel-2-l2a",
            version="Processing baseline 05.10 (as pinned in platform.datasets.access)",
            license="CC-BY 4.0 / Copernicus Open Access",
            permitted_usage="Commercial and academic use with attribution.",
            modality=ModalityType.OPTICAL_SURFACE_REFLECTANCE,
            spatial_coverage="Provider: global land. Retrieved: Kariba AOI, MGRS tile 36LTH only.",
            temporal_coverage_start="2015-06-23",
            temporal_coverage_end="present (rolling provider archive)",
            spatial_resolution="10-20 m native; cached reduction on a 200 m grid",
            temporal_resolution="~5-day constellation revisit (provider)",
            acquisition_date="2023-06-30" if stac else None,
            retrieval_timestamp=stac_retrieved,
            processing_history=(
                [
                    ProcessingStep(
                        step_name="SCL cloud/shadow masking and zonal reduction",
                        algorithm="Per-scene SCL mask, per-pixel annual median, zonal clear-pixel mean",
                        parameters={"mask_type": "scl", "resolution_m": 200.0},
                        output_variable="Annual zonal NDVI/EVI/NDMI/NBR (1 scene)",
                        timestamp=stac_retrieved,
                    )
                ]
                if stac
                else []
            ),
            data_quality_score=None,
            completeness_percentage=None,
            missingness_summary=(
                "Only one scene (2023-06-30, tile 36LTH) has been ingested for the Kariba AOI; "
                "the 2001-2022 pre/post panel has NOT been extracted (see "
                "docs/data/DONOR_REAL_DATA_COVERAGE_REPORT.md). Temporal completeness is not "
                "measurable."
            ),
            content_hash=_sha256_of(_STAC_CACHE),
            content_hash_scope=_STAC_CACHE if stac else None,
            lifecycle=SourceLifecycle.ACCESSIBLE,
            is_operational_integration=False,
            sutva_compliant=False,
            ingestion_mode=IngestionMode.ACCESSIBLE_UNVALIDATED,
            validation_status=ValidationStatus.UNVALIDATED,
            validation_evidence=(
                "none for scientific use. Plumbing only: tests/data_access/"
                "test_planetary_computer_stac.py and test_aoi_pipeline.py exercise the STAC "
                "client; no validation of extracted values."
            ),
            blocked_for_production_analysis=True,
            blocked_reason=(
                "Real extraction is pending: one 2023 scene for one tile exists, no "
                "multi-year panel or donor rasters (Task 5B audit)."
            ),
            quality_measured=False,
            quality_note="No dataset-level quality score has been measured.",
            retrieval_status=_retrieved(stac_retrieved),
            retrieval_provenance=(
                f"CLI `groundtruth ingest-stac` (manual invocation) wrote {_STAC_CACHE}"
                if stac
                else None
            ),
            retrieved_temporal_coverage="2023 (single scene 2023-06-30)" if stac else None,
            local_artifact_paths=(_STAC_CACHE,) if stac else (),
            notes=(
                "Ingestion code exists (data_access/stac.py, aoi_pipeline.py, CLI ingest-stac) "
                "but runs only on manual invocation and has produced a single scene. Not an "
                "automated operational integration."
            ),
        ),
        EvidenceSource(
            source_id="chirps-monthly-v2",
            title="CHIRPS v2.0 Monthly 0.05 degree Gridded Precipitation",
            provider="Climate Hazards Center, UC Santa Barbara (via Digital Earth Africa S3 mirror)",
            source_url="https://data.chc.ucsb.edu/products/CHIRPS-2.0/",
            dataset_identifier=chirps_meta.get("dataset_id", "UCSB-CHC/CHIRPS/v2.0/monthly"),
            version="2.0",
            license="Creative Commons Attribution 4.0 (CHIRPS data policy)",
            permitted_usage="Scientific and commercial use with citation (Funk et al. 2015).",
            modality=ModalityType.GRIDDED_METEOROLOGY,
            spatial_coverage="Provider: 50S-50N. Retrieved: Kariba spatial window only.",
            temporal_coverage_start="1981-01-01",
            temporal_coverage_end="present (provider archive)",
            spatial_resolution="0.05 degrees (~5.5 km)",
            temporal_resolution="Monthly",
            acquisition_date=None,
            retrieval_timestamp=climate_retrieved,
            processing_history=(
                [
                    ProcessingStep(
                        step_name="Zonal precipitation extraction and SPI",
                        algorithm="Zonal mean; Gamma-fit SPI (data_access/climate.py)",
                        parameters={"baseline_period": "1981-2010", "interpolation_applied": False},
                        output_variable="Monthly precipitation (mm), SPI-3/6/12",
                        timestamp=climate_retrieved,
                    )
                ]
                if climate
                else []
            ),
            data_quality_score=None,
            completeness_percentage=chirps_completeness,
            missingness_summary=(
                f"{chirps_got}/{chirps_req} months retrieved; missing {chirps_missing} "
                "(not interpolated)."
                if climate
                else "Climate bundle not present in this deployment."
            ),
            content_hash=_sha256_of(_CLIMATE_CACHE),
            content_hash_scope=(
                f"{_CLIMATE_CACHE} (combined CHIRPS + NASA POWER bundle)" if climate else None
            ),
            lifecycle=SourceLifecycle.INTEGRATED if climate else SourceLifecycle.DISCOVERED,
            is_operational_integration=False,
            sutva_compliant=False,
            ingestion_mode=IngestionMode.MANUAL_STAGING if climate else IngestionMode.SCAFFOLDED,
            validation_status=ValidationStatus.UNVALIDATED,
            validation_evidence=(
                "none for scientific validation. tests/engine/test_climate_integration.py "
                "checks the loader/SPI maths on the staged bundle only."
            ),
            blocked_for_production_analysis=not climate,
            blocked_reason=(
                None if climate else "Climate bundle absent; no climate ingestion script in repo."
            ),
            quality_measured=chirps_completeness is not None,
            quality_note=(
                "completeness = months retrieved / months requested, measured from the staged "
                "bundle; no accuracy/bias quality score computed."
            ),
            retrieval_status=_retrieved(climate_retrieved),
            retrieval_provenance=(
                f"One-off staged retrieval recorded in {_CLIMATE_CACHE}; the retrieval script is "
                "not in this repository (no automated pipeline)."
                if climate
                else None
            ),
            retrieved_temporal_coverage=(
                chirps_meta.get("temporal_coverage_requested") if climate else None
            ),
            local_artifact_paths=(_CLIMATE_CACHE,) if climate else (),
            notes=(
                "Covariate only (rainfall/SPI). Staged manually; there is no automated climate "
                "ingestion path. Usable as an unvalidated covariate input, not as validated evidence."
            ),
        ),
        EvidenceSource(
            source_id="nasa-power-temperatures",
            title="NASA POWER (MERRA-2) Monthly Agroclimatology Temperature (T2M, T2M_MAX, T2M_MIN)",
            provider="NASA Langley Research Center POWER Project",
            source_url="https://power.larc.nasa.gov",
            dataset_identifier=power_meta.get("dataset_id", "NASA-POWER/MERRA-2/monthly-AG"),
            version="POWER monthly regional API (version not recorded in bundle)",
            license="NASA open data policy (public)",
            permitted_usage="Free for scientific and commercial use with acknowledgement.",
            modality=ModalityType.SURFACE_TEMPERATURE,
            spatial_coverage="Provider: global. Retrieved: Kariba spatial window only.",
            temporal_coverage_start="1981-01-01",
            temporal_coverage_end="present (provider archive)",
            spatial_resolution="0.5 x 0.625 degrees (MERRA-2 native)",
            temporal_resolution="Monthly",
            acquisition_date=None,
            retrieval_timestamp=climate_retrieved,
            processing_history=[],
            data_quality_score=None,
            completeness_percentage=power_completeness,
            missingness_summary=(
                f"{power_got}/{power_req} months retrieved; "
                f"missing months: {power_meta.get('missing_months', [])}."
                if power_meta
                else "Climate bundle not present in this deployment."
            ),
            content_hash=_sha256_of(_CLIMATE_CACHE),
            content_hash_scope=(
                f"{_CLIMATE_CACHE} (combined CHIRPS + NASA POWER bundle)" if climate else None
            ),
            lifecycle=SourceLifecycle.INTEGRATED if power_meta else SourceLifecycle.DISCOVERED,
            is_operational_integration=False,
            sutva_compliant=False,
            ingestion_mode=(
                IngestionMode.MANUAL_STAGING if power_meta else IngestionMode.SCAFFOLDED
            ),
            validation_status=ValidationStatus.UNVALIDATED,
            validation_evidence=(
                "none for scientific validation. tests/engine/test_climate_integration.py "
                "exercises the loader only."
            ),
            blocked_for_production_analysis=not power_meta,
            blocked_reason=(
                None if power_meta else "Climate bundle absent; no ingestion script in repo."
            ),
            quality_measured=power_completeness is not None,
            quality_note="completeness = months retrieved / 516 requested; no accuracy score.",
            retrieval_status=_retrieved(climate_retrieved),
            retrieval_provenance=(
                f"One-off staged retrieval recorded in {_CLIMATE_CACHE}; script not in repo."
                if power_meta
                else None
            ),
            retrieved_temporal_coverage=(
                power_meta.get("temporal_coverage_requested") if power_meta else None
            ),
            local_artifact_paths=(_CLIMATE_CACHE,) if power_meta else (),
            notes="Auxiliary temperature covariate. Manually staged; no automated ingestion path.",
        ),
        EvidenceSource(
            source_id="geoboundaries-adm2-zimbabwe",
            title="geoBoundaries gbOpen ADM2 Districts (Zimbabwe and Zambia donor candidates)",
            provider="geoBoundaries / William & Mary geoLab (authority: ZIMSTAT, UN OCHA ROSEA)",
            source_url="https://www.geoboundaries.org",
            dataset_identifier="geoBoundaries gbOpen ZWE/ZMB ADM2 (curated Kariba donor file)",
            version="gbOpen v6.0.0 (commit 9469f09)",
            license="CC BY 3.0 IGO (ZWE) / CC BY 4.0 (ZMB)",
            permitted_usage="Attribution required (Runfola et al. 2020).",
            modality=ModalityType.SPATIAL_VECTOR_POLYGONS,
            spatial_coverage="50 candidate ADM2 districts (Zimbabwe, Zambia) around Kariba",
            temporal_coverage_start="2020-01-01",
            temporal_coverage_end="2020-12-31",
            spatial_resolution="Vector polygons (simplified release)",
            temporal_resolution="Static snapshot (year represented: 2020)",
            acquisition_date=None,
            retrieval_timestamp=donors_retrieved,
            processing_history=[
                ProcessingStep(
                    step_name="Donor eligibility audit",
                    algorithm="Spatial exclusion buffer and overlap screening",
                    parameters={
                        k: v
                        for k, v in (donors_prov.get("summary_counts") or {}).items()
                        if k in ("total_candidates_evaluated", "eligible_total", "excluded_total")
                    },
                    output_variable="eligible_for_donor_pool flags",
                    timestamp=donors_retrieved,
                )
            ]
            if donors_prov
            else [],
            data_quality_score=None,
            completeness_percentage=None,
            missingness_summary=(
                "50 of 51 candidates have verified geometry (1 unverified); 37 eligible, 14 "
                "excluded per the boundary audit."
                if donors_prov
                else "Donor boundary file not present."
            ),
            content_hash=_sha256_of(_DONOR_GEOJSON),
            content_hash_scope=_DONOR_GEOJSON if donors_prov else None,
            lifecycle=SourceLifecycle.INTEGRATED if donors_prov else SourceLifecycle.DISCOVERED,
            is_operational_integration=False,
            sutva_compliant=bool(donors_prov),
            ingestion_mode=(
                IngestionMode.CURATED_VECTOR if donors_prov else IngestionMode.SCAFFOLDED
            ),
            validation_status=ValidationStatus.VALIDATED
            if donors_prov
            else ValidationStatus.UNVALIDATED,
            validation_evidence=(
                "cases/boundaries/kariba-donors.provenance.json (status verified, artifact "
                "sha256) and tests/data_access/test_task5_real_data_integrity.py::"
                "test_donor_pool_audit_records. Validates geometry provenance only, not "
                "vegetation data."
                if donors_prov
                else "none"
            ),
            blocked_for_production_analysis=not donors_prov,
            blocked_reason=None if donors_prov else "Donor boundary file absent.",
            quality_measured=False,
            quality_note="Counts are audit results, not a quality score.",
            retrieval_status=_retrieved(donors_retrieved),
            retrieval_provenance=(
                "Curated vector file with per-country upstream download URLs and source "
                f"sha256 in {_DONOR_PROVENANCE}"
                if donors_prov
                else None
            ),
            retrieved_temporal_coverage="2020 boundary snapshot" if donors_prov else None,
            local_artifact_paths=(_DONOR_GEOJSON, _DONOR_PROVENANCE) if donors_prov else (),
            notes=(
                "Curated, version-pinned vector boundaries (not an automated ingestion). "
                "Defines the spatially eligible donor pool only."
            ),
        ),
        EvidenceSource(
            source_id="gedi-l4a-footprint-biomass",
            title="GEDI Level 4A Footprint Aboveground Biomass Density",
            provider="NASA / University of Maryland (ORNL DAAC)",
            source_url="https://daac.ornl.gov/GEDI/guides/GEDI_L4A_AGB_Density_V2_1.html",
            dataset_identifier="NASA/GEDI/002/GEDI04_A_v002",
            version="V2.1 (provider; not retrieved)",
            license="NASA Earthdata open data policy",
            permitted_usage="Open scientific and commercial use with citation.",
            modality=ModalityType.SPACEBORNE_LIDAR,
            spatial_coverage="Provider: 51.6N-51.6S sampled orbit tracks. Nothing retrieved.",
            temporal_coverage_start="2019-04-18",
            temporal_coverage_end="present (provider archive)",
            spatial_resolution="25 m footprint",
            temporal_resolution="Orbital track sampling",
            acquisition_date=None,
            retrieval_timestamp=None,
            processing_history=[],
            data_quality_score=None,
            completeness_percentage=None,
            missingness_summary="No GEDI shots have been retrieved or staged in this repository.",
            content_hash=None,
            lifecycle=SourceLifecycle.DISCOVERED,
            is_operational_integration=False,
            sutva_compliant=False,
            ingestion_mode=IngestionMode.SCAFFOLDED,
            validation_status=ValidationStatus.UNVALIDATED,
            validation_evidence="none",
            blocked_for_production_analysis=True,
            blocked_reason="Catalogue entry only: no ingestion code and no staged data exist.",
            notes=(
                "Previously reported as integrated with 1,420 shots; no such artefact or code "
                "exists in the repository, so the claim was withdrawn."
            ),
        ),
        EvidenceSource(
            source_id="synthetic-kariba-benchmark",
            title="SYNTHETIC Kariba Restoration Benchmark Fixture (simulated, not observations)",
            provider="GroundTruth (offline generated)",
            source_url="https://github.com/groundtruth/benchmarks/kariba-v2",
            dataset_identifier="GROUNDTRUTH/BENCHMARK/KARIBA/SYNTHETIC",
            version=str(
                (_json_of(_SYNTH_FIXTURE).get("dataset_ref") or {}).get("version", "unknown")
            ),
            license="Project-internal benchmark fixture",
            permitted_usage="Pipeline exercising, methodological benchmarking and regression "
            "tests ONLY. Never evidence about a real project.",
            modality=ModalityType.SYNTHETIC_BENCHMARK,
            spatial_coverage="Simulated units (not real geography measurements)",
            temporal_coverage_start="2001-01-01",
            temporal_coverage_end="2022-12-31",
            spatial_resolution="Simulated zonal series",
            temporal_resolution="Annual",
            acquisition_date=None,
            retrieval_timestamp=None,
            processing_history=[],
            data_quality_score=None,
            completeness_percentage=None,
            missingness_summary="Synthetic by construction; completeness/quality are meaningless "
            "for real-world evidence and are not reported.",
            content_hash=_sha256_of(_SYNTH_FIXTURE),
            content_hash_scope=_SYNTH_FIXTURE if _sha256_of(_SYNTH_FIXTURE) else None,
            lifecycle=SourceLifecycle.INTEGRATED,
            is_operational_integration=False,
            sutva_compliant=False,
            ingestion_mode=IngestionMode.SYNTHETIC_SIMULATED,
            validation_status=ValidationStatus.NOT_APPLICABLE,
            validation_evidence="not applicable: simulated data carries data_mode=synthetic (R7)",
            blocked_for_production_analysis=True,
            blocked_reason="Synthetic simulated data; permitted only in explicit synthetic "
            "benchmark mode, never for real-data analysis.",
            quality_measured=False,
            quality_note="Not applicable to simulated data.",
            retrieval_status="not_retrieved",
            retrieval_provenance="Generated offline; no external retrieval.",
            local_artifact_paths=(_SYNTH_FIXTURE,),
            notes="SYNTHETIC / SIMULATED. Output derived from it must show the simulation banner.",
        ),
        EvidenceSource(
            source_id="quarantined-legacy-landsat-cache",
            title="QUARANTINED fabricated Landsat multi-tile cache (Task 5B P0-1)",
            provider="GroundTruth internal build script (fabricated values)",
            source_url="https://planetarycomputer.microsoft.com/dataset/landsat-c2-l2",
            dataset_identifier="data/processed/_quarantine_task5b_fabricated/landsat_cache",
            version="quarantined",
            license="Not applicable (not real data)",
            permitted_usage="PROHIBITED for any analysis. Retained only as audit evidence.",
            modality=ModalityType.AIR_GAPPED_QUARANTINE,
            spatial_coverage="Kariba AOI (claimed; fabricated)",
            temporal_coverage_start="2001-01-01",
            temporal_coverage_end="2022-12-31",
            spatial_resolution="n/a",
            temporal_resolution="Annual (fabricated)",
            acquisition_date=None,
            retrieval_timestamp=None,
            processing_history=[],
            data_quality_score=None,
            completeness_percentage=None,
            missingness_summary="Values were hand-typed, never extracted from rasters.",
            content_hash=None,
            lifecycle=SourceLifecycle.QUARANTINED,
            is_operational_integration=False,
            sutva_compliant=False,
            quarantine_reason=(
                "Independent Task 5B audit finding P0-1: fabricated values labelled as real "
                "satellite observations (docs/audits/INDEPENDENT_TASK_5B_AUDIT.md)."
            ),
            ingestion_mode=IngestionMode.QUARANTINED,
            validation_status=ValidationStatus.FAILED,
            validation_evidence=(
                "Failed independent audit; see data/processed/_quarantine_task5b_fabricated/README.md"
            ),
            blocked_for_production_analysis=True,
            blocked_reason="Quarantined: fabricated values. Refused fail-closed.",
            quality_measured=False,
            quality_note="Not applicable: data is not real.",
            notes="Hard refusal; no pipeline may load this cache.",
        ),
        EvidenceSource(
            source_id="alos2-palsar-sar-mosaic",
            title="JAXA ALOS-2 PALSAR-2 Annual 25 m SAR Mosaic",
            provider="Japan Aerospace Exploration Agency (JAXA EORC)",
            source_url="https://www.eorc.jaxa.jp/ALOS/en/dataset/palsar_e.htm",
            dataset_identifier="JAXA/ALOS/PALSAR-2/MOSAIC/25m",
            version="not retrieved",
            license="JAXA data policy (check terms before use)",
            permitted_usage="Per JAXA ALOS data policy; not yet reviewed for this deployment.",
            modality=ModalityType.SYNTHETIC_APERTURE_RADAR,
            spatial_coverage="Provider: global. Nothing retrieved.",
            temporal_coverage_start="2015-01-01",
            temporal_coverage_end="present (provider archive)",
            spatial_resolution="25 m",
            temporal_resolution="Annual",
            acquisition_date=None,
            retrieval_timestamp=None,
            processing_history=[],
            data_quality_score=None,
            completeness_percentage=None,
            missingness_summary="No PALSAR mosaics have been retrieved or staged.",
            content_hash=None,
            lifecycle=SourceLifecycle.DISCOVERED,
            is_operational_integration=False,
            sutva_compliant=False,
            ingestion_mode=IngestionMode.SCAFFOLDED,
            blocked_for_production_analysis=True,
            blocked_reason="Catalogue entry only: no ingestion code and no staged data exist.",
            notes="Previously reported as integrated manual staging; no artefact exists.",
        ),
        EvidenceSource(
            source_id="sentinel-1-grd-c-band",
            title="Copernicus Sentinel-1 C-Band SAR GRD",
            provider="ESA / Copernicus",
            source_url="https://dataspace.copernicus.eu",
            dataset_identifier="COPERNICUS/S1_GRD",
            version="not retrieved",
            license="CC-BY 4.0 / Copernicus Open Access",
            permitted_usage="Environmental monitoring and commercial use with attribution.",
            modality=ModalityType.SYNTHETIC_APERTURE_RADAR,
            spatial_coverage="Provider: global land (IW mode). Nothing retrieved.",
            temporal_coverage_start="2014-10-03",
            temporal_coverage_end="present (provider archive)",
            spatial_resolution="~10 m pixel spacing",
            temporal_resolution="6-12 day revisit (provider)",
            acquisition_date=None,
            retrieval_timestamp=None,
            processing_history=[],
            data_quality_score=None,
            completeness_percentage=None,
            missingness_summary="No Sentinel-1 scenes retrieved; SAR pipeline is scaffolded only.",
            content_hash=None,
            lifecycle=SourceLifecycle.DISCOVERED,
            is_operational_integration=False,
            sutva_compliant=False,
            ingestion_mode=IngestionMode.SCAFFOLDED,
            blocked_for_production_analysis=True,
            blocked_reason="Scaffolded catalogue entry: terrain correction and speckle "
            "filtering are not implemented.",
            notes="Discovered catalogue entry only.",
        ),
        EvidenceSource(
            source_id="landsat-c2-l2-sr",
            title="USGS Landsat Collection 2 Level-2 Surface Reflectance (Planetary Computer STAC)",
            provider="USGS / NASA via Microsoft Planetary Computer",
            source_url="https://planetarycomputer.microsoft.com/dataset/landsat-c2-l2",
            dataset_identifier="landsat-c2-l2",
            version="Collection 2 (platform pin 2.0)",
            license="USGS / US Government public domain",
            permitted_usage="Free for commercial and scientific use.",
            modality=ModalityType.OPTICAL_SURFACE_REFLECTANCE,
            spatial_coverage="Provider: global. Retrieved: scene-availability metadata only "
            "for the Kariba AOI and 37 donors.",
            temporal_coverage_start="1999-04-15",
            temporal_coverage_end="present (provider archive)",
            spatial_resolution="30 m",
            temporal_resolution="8-16 day revisit (provider)",
            acquisition_date=None,
            retrieval_timestamp=None,
            processing_history=[],
            data_quality_score=None,
            completeness_percentage=None,
            missingness_summary=(
                "Scene-availability audits exist (data/processed/*_landsat_coverage_audit.json) "
                "but no Landsat raster values have been extracted; the earlier fabricated cache "
                "is quarantined."
            ),
            content_hash=None,
            lifecycle=SourceLifecycle.ACCESSIBLE,
            is_operational_integration=False,
            sutva_compliant=False,
            ingestion_mode=IngestionMode.ACCESSIBLE_UNVALIDATED,
            validation_status=ValidationStatus.UNVALIDATED,
            validation_evidence=(
                "none for values. tests/data_access/test_task5_real_data_integrity.py checks "
                "scene-availability audit records only."
            ),
            blocked_for_production_analysis=True,
            blocked_reason=(
                "No raster extraction; cross-sensor calibration to Sentinel-2 is not "
                "implemented (engine capability cross_sensor_calibration=false); SLC-off gaps."
            ),
            retrieval_provenance="Scene metadata only; see coverage audit JSON files.",
            notes="Endpoint accessible; values not extracted. Blocked from production analysis.",
        ),
    ]


class EvidenceRegistry:
    """Registry managing the truthful classification of environmental evidence sources."""

    def __init__(self, sources: list[EvidenceSource] | None = None) -> None:
        initial = sources if sources is not None else _build_initial_registry()
        self._sources: dict[str, EvidenceSource] = {s.source_id: s for s in initial}

    def list_sources(
        self,
        lifecycle: SourceLifecycle | None = None,
        operational_only: bool = False,
    ) -> list[EvidenceSource]:
        """List registered evidence sources with optional lifecycle filtering."""
        results = list(self._sources.values())
        if lifecycle is not None:
            results = [s for s in results if s.lifecycle == lifecycle]
        if operational_only:
            results = [s for s in results if s.is_operational_integration]
        return results

    def get_source(self, source_id: str) -> EvidenceSource | None:
        """Retrieve a specific source by its unique ID."""
        return self._sources.get(source_id)

    def register_source(self, source: EvidenceSource) -> None:
        """Register or update an evidence source."""
        self._sources[source.source_id] = source

    def assert_operational(self, source_id: str) -> EvidenceSource:
        """Ensure a source is an operational integration; fail closed otherwise."""
        source = self.get_source(source_id)
        if not source:
            raise KeyError(f"Evidence source '{source_id}' is not in the registry.")
        if source.lifecycle == SourceLifecycle.QUARANTINED:
            raise PermissionError(
                f"Source '{source_id}' is QUARANTINED ({source.quarantine_reason}). Access refused fail-closed."
            )
        if source.lifecycle in (SourceLifecycle.DISCOVERED, SourceLifecycle.ACCESSIBLE):
            raise PermissionError(
                f"Source '{source_id}' has lifecycle '{source.lifecycle}'. Discovered and accessible datasets cannot enter production analytical pipelines without integration and validation."
            )
        if not source.is_operational_integration:
            raise ValueError(
                f"Source '{source_id}' is catalogued as {source.lifecycle} "
                f"(ingestion_mode={source.ingestion_mode}) but is NOT an operational integration."
            )
        return source

    def assert_dataset_allowed_for_production(self, source_id: str) -> EvidenceSource:
        """Gate for real-data analysis: raise ProductionAnalysisBlockedError unless permitted.

        Blocks unknown, quarantined, synthetic, scaffolded, accessible-but-unvalidated,
        failed-validation and explicitly blocked sources, and any source whose declared
        local artefacts are missing.
        """
        source = self.get_source(source_id)
        if source is None:
            raise ProductionAnalysisBlockedError(
                f"Dataset '{source_id}' is not in the evidence registry; refused fail-closed."
            )
        if source.lifecycle == SourceLifecycle.QUARANTINED:
            raise ProductionAnalysisBlockedError(
                f"Dataset '{source_id}' is QUARANTINED ({source.quarantine_reason}); refused."
            )
        if source.ingestion_mode == IngestionMode.SYNTHETIC_SIMULATED:
            raise ProductionAnalysisBlockedError(
                f"Dataset '{source_id}' is synthetic/simulated and cannot feed real-data analysis."
            )
        if source.blocked_for_production_analysis or source.validation_status == (
            ValidationStatus.FAILED
        ):
            raise ProductionAnalysisBlockedError(
                f"Dataset '{source_id}' is blocked for production analysis "
                f"(ingestion_mode={source.ingestion_mode}): {source.blocked_reason}"
            )
        if source.artifacts_present() is False:
            raise ProductionAnalysisBlockedError(
                f"Dataset '{source_id}' local artefacts are missing: "
                f"{', '.join(source.local_artifact_paths)}."
            )
        return source

    def get_summary_statistics(self) -> dict[str, Any]:
        """Lifecycle and truthfulness counters, derived only from the entries."""
        all_sources = list(self._sources.values())
        measured = [
            s.completeness_percentage
            for s in all_sources
            if s.quality_measured and s.completeness_percentage is not None
        ]

        def count(mode: IngestionMode) -> int:
            return sum(1 for s in all_sources if s.ingestion_mode == mode)

        return {
            "total_registered": len(all_sources),
            "discovered": sum(1 for s in all_sources if s.lifecycle == SourceLifecycle.DISCOVERED),
            "accessible": sum(1 for s in all_sources if s.lifecycle == SourceLifecycle.ACCESSIBLE),
            "integrated": sum(1 for s in all_sources if s.lifecycle == SourceLifecycle.INTEGRATED),
            "validated": sum(1 for s in all_sources if s.lifecycle == SourceLifecycle.VALIDATED),
            "quarantined": sum(
                1 for s in all_sources if s.lifecycle == SourceLifecycle.QUARANTINED
            ),
            "operational_count": sum(1 for s in all_sources if s.is_operational_integration),
            "usable_for_production_count": sum(
                1 for s in all_sources if not s.blocked_for_production_analysis
            ),
            "blocked_count": sum(1 for s in all_sources if s.blocked_for_production_analysis),
            "synthetic_count": count(IngestionMode.SYNTHETIC_SIMULATED),
            "ingestion_mode_counts": {m.value: count(m) for m in IngestionMode},
            # Mean over sources whose completeness was actually measured; None if none were.
            "average_completeness": (round(sum(measured) / len(measured), 1) if measured else None),
            "completeness_measured_count": len(measured),
        }

    def earth_observation_implemented(self) -> bool:
        """True only if a real (non-synthetic) optical source is an operational integration."""
        return any(
            s.is_operational_integration and s.modality == ModalityType.OPTICAL_SURFACE_REFLECTANCE
            for s in self._sources.values()
        )


# Global registry singleton instance
_GLOBAL_EVIDENCE_REGISTRY = EvidenceRegistry()


def get_global_evidence_registry() -> EvidenceRegistry:
    """Return the global scientific evidence registry."""
    return _GLOBAL_EVIDENCE_REGISTRY


def assert_dataset_allowed_for_production(source_id: str) -> EvidenceSource:
    """Module-level production gate over the global registry."""
    return _GLOBAL_EVIDENCE_REGISTRY.assert_dataset_allowed_for_production(source_id)
