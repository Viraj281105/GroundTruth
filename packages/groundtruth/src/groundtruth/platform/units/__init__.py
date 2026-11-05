"""ADR-011 unit construction: what one analysis unit is, made executable.

The decision record is ``docs/decisions/ADR-011-unit-of-analysis.md``. This
package implements it and nothing else:

- :mod:`spec` — the fixed thresholds and the ladder, plus the open parameters
  that must be pinned before a run and are never defaulted.
- :mod:`geodesic` — dependency-free area and validity checks for boundaries.
- :mod:`boundary` — loading a committed registry boundary artifact (#2).
- :mod:`rules` — the eligibility rules, structured exclusion reasons, and the
  ladder's single stopping rule.
- :mod:`provider` — the masking port, and its Earth Engine implementation (#23).
- :mod:`run_settings` — the committed open parameters, and the gate that refuses
  a real generation while any of them is undecided.
- :mod:`carbon_projects` — the committed registered-projects snapshot.
- :mod:`manifest` — the unit-set artifact that makes a pool reproducible.
- :mod:`generator` — the pipeline, and a ``DonorCandidateAccess`` adapter.

**What does not run yet, and why that is the correct behaviour.** A real unit set
needs an Earth Engine key, an uploaded road layer, a committed carbon-project
snapshot and several settings that are still undecided, so generation refuses and
names each one rather than returning units that were never measured. Synthetic
donors exist for testing the estimators; they are not a stand-in for a real
candidate pool, and wiring them in here would put fiction upstream of every number
the pipeline produces.
"""

from __future__ import annotations

from groundtruth.platform.units.boundary import RegistryBoundary, load_registry_boundary
from groundtruth.platform.units.carbon_projects import (
    CarbonProjectSnapshot,
    load_carbon_snapshot,
)
from groundtruth.platform.units.generator import (
    Adr011DonorCandidates,
    UnitSet,
    district_unit_ref,
    generate_unit_set,
)
from groundtruth.platform.units.manifest import ManifestContext, UnitSetManifest, build_manifest
from groundtruth.platform.units.provider import (
    EarthEngineUnitConstruction,
    UnitConstructionService,
)
from groundtruth.platform.units.rules import (
    DistrictFacts,
    Exclusion,
    ExclusionCategory,
    LadderOutcome,
    RungRecord,
    Screening,
    climb_ladder,
    evaluate_district,
    screen_rung,
)
from groundtruth.platform.units.run_settings import (
    Blocker,
    RunSettings,
    generation_blockers,
    load_run_settings,
    run_settings_path,
)
from groundtruth.platform.units.spec import (
    ADR,
    LADDER,
    Adr011Thresholds,
    MissingRunParameterError,
    Rung,
    RunParameters,
)

__all__ = [
    "ADR",
    "LADDER",
    "Adr011DonorCandidates",
    "Adr011Thresholds",
    "Blocker",
    "CarbonProjectSnapshot",
    "DistrictFacts",
    "EarthEngineUnitConstruction",
    "Exclusion",
    "ExclusionCategory",
    "LadderOutcome",
    "ManifestContext",
    "MissingRunParameterError",
    "RegistryBoundary",
    "RunParameters",
    "RunSettings",
    "Rung",
    "RungRecord",
    "Screening",
    "UnitConstructionService",
    "UnitSet",
    "UnitSetManifest",
    "build_manifest",
    "climb_ladder",
    "district_unit_ref",
    "evaluate_district",
    "generate_unit_set",
    "generation_blockers",
    "load_carbon_snapshot",
    "load_registry_boundary",
    "load_run_settings",
    "run_settings_path",
    "screen_rung",
]
