"""ADR-011 unit construction: what one analysis unit is, made executable.

The decision record is ``docs/decisions/ADR-011-unit-of-analysis.md``. This
package implements it and nothing else:

- :mod:`spec` — the fixed thresholds and the ladder, plus the open parameters
  that must be pinned before a run and are never defaulted.
- :mod:`geodesic` — dependency-free area and validity checks for boundaries.
- :mod:`boundary` — loading a committed registry boundary artifact (#2).
- :mod:`rules` — the eligibility rules, structured exclusion reasons, and the
  ladder's single stopping rule.
- :mod:`provider` — the masking port, and the Earth Engine implementation that
  is not written yet (#23, #1/#22).
- :mod:`manifest` — the unit-set artifact that makes a pool reproducible.
- :mod:`generator` — the pipeline, and a ``DonorCandidateAccess`` adapter.

**What does not work yet, and why that is the correct behaviour.** The masking
chain needs pinned Earth Engine assets that no provider supplies today, so
generation raises ``DataUnavailableError`` rather than returning units that were
never measured. Synthetic donors exist for testing the estimators; they are not
a stand-in for a real candidate pool, and wiring them in here would put fiction
upstream of every number the pipeline produces.
"""

from __future__ import annotations

from groundtruth.platform.units.boundary import RegistryBoundary, load_registry_boundary
from groundtruth.platform.units.generator import (
    Adr011DonorCandidates,
    UnitSet,
    generate_unit_set,
)
from groundtruth.platform.units.manifest import UnitSetManifest, build_manifest
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
    "DistrictFacts",
    "EarthEngineUnitConstruction",
    "Exclusion",
    "ExclusionCategory",
    "LadderOutcome",
    "MissingRunParameterError",
    "RegistryBoundary",
    "RunParameters",
    "Rung",
    "RungRecord",
    "Screening",
    "UnitConstructionService",
    "UnitSet",
    "UnitSetManifest",
    "build_manifest",
    "climb_ladder",
    "evaluate_district",
    "generate_unit_set",
    "load_registry_boundary",
    "screen_rung",
]
