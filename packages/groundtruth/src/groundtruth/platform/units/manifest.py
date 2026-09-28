"""The unit-set manifest: ADR-011's reproducibility requirement, as a file.

``spec_hash`` does not cover unit construction. When the platform resolves
candidates through ``DonorCandidateAccess``, nothing about *how* those units
were built enters the request — not the thresholds, not the buffer, not the
projection, not the rung. Two runs that built different units from the same
rules would share a hash and appear to have reproduced each other, which is
worse than an unreproducible number because it is an unreproducible number
wearing a reproducibility check.

The manifest closes that hole. It is written under ``data/manifests/``, pinned
as a ``DatasetRef`` like any other input so that it enters the request and
therefore the hash, and it carries everything ADR-011's "Reproducibility
requirements" table lists: the boundary and its hash, every input ref with its
reference period, every threshold and parameter as executed, the belt, the
counts at every rung climbed, the pool parameters, per-unit geometry hashes and
eligible areas, and the exclusions that fired before matching ever saw a
candidate.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from groundtruth.contracts.identifiers import DatasetRef, spec_hash
from groundtruth.contracts.version import CONTRACT_VERSION
from groundtruth.platform.units.boundary import RegistryBoundary
from groundtruth.platform.units.rules import DistrictFacts, Exclusion, RungRecord
from groundtruth.platform.units.spec import ADR, Adr011Thresholds, RunParameters

MANIFEST_DIR = Path("data/manifests")

REFERENCE_PERIODS: dict[str, str] = {
    "gaul-2015-level2": "administrative geography as of 2014-2015 (frozen edition)",
    "resolve-ecoregions-2017": "biogeographic classification, effectively time-invariant",
    "hansen-gfc": "canopy cover in the year 2000",
    "jrc-global-surface-water": "1984-2021 full record",
    "wdpa": "designations filtered to <= 2000; boundaries as currently held",
    "registered-carbon-projects": "projects registered up to the pinned snapshot date",
}
"""Reference period of the *variable*, which is not the release date.

ADR-011 is explicit that only the first decides whether an input is
pre-treatment. Hansen's 2023 release carries a year-2000 band; GSW's occurrence
band spans the analysis window whatever its version string says.
"""


@dataclass(frozen=True, slots=True)
class UnitSetManifest:
    """A generated unit set, described so a third party can rebuild it."""

    case_id: str
    adr: str
    generated_at: str
    contract_version: str
    engine_version: str
    git_sha: str | None

    boundary_path: str
    boundary_sha256: str
    boundary_area_km2: float
    treated_eligible_area_km2: float

    thresholds: dict[str, Any]
    run_parameters: dict[str, Any]
    dataset_refs: list[dict[str, Any]]
    dataset_reference_periods: dict[str, str]

    rung_records: list[dict[str, Any]]
    rung_used: int

    units: list[dict[str, Any]]
    exclusions: list[dict[str, Any]]

    geometry_notes: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        """Deterministic JSON: sorted keys, fixed separators, trailing newline."""
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    @property
    def content_hash(self) -> str:
        """Hash of everything except the generation timestamp.

        Two runs of the same specification over the same pinned inputs produce
        the same hash; only the clock differs. That makes the manifest usable as
        a reproducibility check rather than just a log.
        """
        payload = {k: v for k, v in asdict(self).items() if k != "generated_at"}
        return spec_hash(payload)

    def as_dataset_ref(self) -> DatasetRef:
        """The manifest as a pinned input, so it reaches ``spec_hash``."""
        return DatasetRef(
            dataset_id="adr011-unit-set",
            version=self.content_hash,
            provider="groundtruth",
            asset=str(MANIFEST_DIR / f"{self.case_id}-unit-set.json"),
            retrieved_at=self.generated_at,
        )

    def write(self, directory: str | Path = MANIFEST_DIR) -> Path:
        """Write the manifest under ``data/manifests/``.

        Returns:
            The path written.
        """
        out_dir = Path(directory)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{self.case_id}-unit-set.json"
        path.write_text(self.to_json(), encoding="utf-8", newline="\n")
        return path


def build_manifest(
    *,
    boundary: RegistryBoundary,
    treated_eligible_area_km2: float,
    thresholds: Adr011Thresholds,
    parameters: RunParameters,
    dataset_refs: tuple[DatasetRef, ...],
    rung_records: tuple[RungRecord, ...],
    rung_used: int,
    units: tuple[DistrictFacts, ...],
    exclusions: tuple[Exclusion, ...],
    engine_version: str,
    git_sha: str | None = None,
) -> UnitSetManifest:
    """Assemble the manifest from a completed generation run."""
    geometry_notes: list[str] = []
    if boundary.report.overlaps:
        shared = sum(o.area_km2 for o in boundary.report.overlaps)
        geometry_notes.append(
            f"registry boundary has {len(boundary.report.overlaps)} overlapping part pair(s) "
            f"totalling {shared:.4f} km2; area computed on the union, geometry left as delivered"
        )
    if boundary.report.clockwise_exterior_rings:
        geometry_notes.append(
            "exterior rings were clockwise in the source and are stored counter-clockwise "
            "per RFC 7946; the point sets are unchanged"
        )

    return UnitSetManifest(
        case_id=boundary.case_id,
        adr=ADR,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        contract_version=CONTRACT_VERSION,
        engine_version=engine_version,
        git_sha=git_sha,
        boundary_path=str(boundary.path).replace("\\", "/"),
        boundary_sha256=boundary.content_sha256,
        boundary_area_km2=round(boundary.boundary_area_km2, 4),
        treated_eligible_area_km2=round(treated_eligible_area_km2, 4),
        thresholds=asdict(thresholds),
        run_parameters=asdict(parameters),
        dataset_refs=[r.model_dump(mode="json") for r in dataset_refs],
        dataset_reference_periods=dict(REFERENCE_PERIODS),
        rung_records=[asdict(r) for r in rung_records],
        rung_used=rung_used,
        units=[
            {
                "unit_id": u.unit_id,
                "adm2_code": u.adm2_code,
                "country": u.country,
                "eligible_area_km2": round(u.eligible_area_km2, 4),
                "forest_share_in_target_ecoregions": round(u.forest_share_in_target_ecoregions, 6),
                "fragments": u.fragments,
                "geometry_hash": u.geometry_hash,
            }
            for u in units
        ],
        exclusions=[
            {"unit_id": e.unit_id, "category": e.category.value, "reason": e.reason}
            for e in exclusions
        ],
        geometry_notes=geometry_notes,
    )
