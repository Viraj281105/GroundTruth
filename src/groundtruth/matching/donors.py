"""Donor-pool construction and covariate matching.

The counterfactual is only as credible as the donor pool. This module builds
that pool explicitly and records why each candidate was admitted or excluded, so
a reviewer can challenge the pool rather than the black box.

Three eligibility rules are applied before any distance is computed:

1. **Spillover exclusion.** Regions inside the project's leakage belt are
   excluded: if the project displaced deforestation into them, they are treated
   units in disguise and would bias the effect upward.
2. **Common support.** Candidates outside the covariate range considered
   plausible for the project are excluded rather than extrapolated over.
3. **Pre-treatment coverage.** Candidates lacking enough clear pre-period
   observations are excluded, because synthetic control weights are fitted on
   the pre-period.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from groundtruth.core.errors import DonorPoolError
from groundtruth.core.types import DonorMatch

DEFAULT_COVARIATES: tuple[str, ...] = (
    "rainfall_mm",
    "elevation_m",
    "slope_deg",
    "road_distance_km",
    "population_density",
)


@dataclass
class MatchingConfig:
    """Parameters controlling donor admission and ranking."""

    covariates: tuple[str, ...] = DEFAULT_COVARIATES
    weights: dict[str, float] = field(default_factory=dict)
    max_donors: int = 50
    min_donors: int = 10
    caliper_sd: float | None = 3.0
    """Exclude candidates further than this many pooled SDs on any covariate."""
    excluded_unit_ids: frozenset[str] = frozenset()
    """Units inside the leakage belt or otherwise contaminated by the treatment."""
    min_pre_observations: int = 4

    def covariate_weights(self) -> np.ndarray:
        """Per-covariate weights as an array, defaulting to equal weighting."""
        return np.asarray([self.weights.get(c, 1.0) for c in self.covariates], dtype=float)


@dataclass(frozen=True)
class DonorPool:
    """The outcome of matching: admitted donors, exclusions, and diagnostics."""

    project_unit_id: str
    matches: tuple[DonorMatch, ...]
    covariates: tuple[str, ...]
    standardised_mean_differences: dict[str, float]

    @property
    def admitted(self) -> tuple[DonorMatch, ...]:
        """Donors that passed every eligibility rule, closest first."""
        return tuple(m for m in self.matches if m.admitted)

    @property
    def excluded(self) -> tuple[DonorMatch, ...]:
        """Candidates that were rejected, with reasons."""
        return tuple(m for m in self.matches if not m.admitted)

    @property
    def unit_ids(self) -> tuple[str, ...]:
        """Ids of admitted donors."""
        return tuple(m.unit_id for m in self.admitted)

    @property
    def worst_balance(self) -> float:
        """Largest absolute standardised mean difference after matching.

        Values above roughly 0.25 are conventionally treated as poor balance and
        should be reported as a limitation of the estimate.
        """
        if not self.standardised_mean_differences:
            return float("nan")
        return max(abs(v) for v in self.standardised_mean_differences.values())

    @property
    def is_balanced(self) -> bool:
        """True if every covariate is balanced within the conventional 0.25 SMD."""
        return bool(self.standardised_mean_differences) and self.worst_balance <= 0.25


def _standardise(
    project: np.ndarray, donors: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Z-score covariates using the pooled donor scale.

    Returns the standardised project vector, standardised donor matrix, and the
    scale used (so degenerate zero-variance covariates can be reported).
    """
    scale = donors.std(axis=0, ddof=1) if donors.shape[0] > 1 else np.ones(donors.shape[1])
    scale = np.where(scale < 1e-12, 1.0, scale)
    centre = donors.mean(axis=0)
    return (project - centre) / scale, (donors - centre) / scale, scale


def standardised_mean_difference(
    project_value: float, donor_values: np.ndarray, pooled_sd: float
) -> float:
    """Cohen-style standardised mean difference between project and donor pool."""
    if pooled_sd < 1e-12:
        return 0.0
    return float((project_value - float(np.mean(donor_values))) / pooled_sd)


def match_donors(
    project_unit_id: str,
    project_covariates: dict[str, float],
    candidate_covariates: dict[str, dict[str, float]],
    config: MatchingConfig | None = None,
    *,
    candidate_pre_observations: dict[str, int] | None = None,
) -> DonorPool:
    """Rank and filter candidate control regions for a project.

    Args:
        project_unit_id: Id of the treated unit.
        project_covariates: Covariate values for the project.
        candidate_covariates: Covariate values per candidate donor.
        config: Matching parameters.
        candidate_pre_observations: Clear pre-period observation counts per
            candidate, used to enforce the coverage rule.

    Returns:
        A :class:`DonorPool` with admitted donors sorted by covariate distance
        and every exclusion recorded with its reason.

    Raises:
        DonorPoolError: if fewer than ``config.min_donors`` candidates survive.
            Refusing to estimate is the correct behaviour here; an estimate
            built on three donors is not defensible.
    """
    cfg = config or MatchingConfig()
    if not candidate_covariates:
        raise DonorPoolError(f"no candidate donors supplied for {project_unit_id!r}")

    missing = [c for c in cfg.covariates if c not in project_covariates]
    if missing:
        raise DonorPoolError(f"project is missing covariates: {missing}")

    usable_ids = [
        uid for uid, cov in candidate_covariates.items() if all(c in cov for c in cfg.covariates)
    ]
    if not usable_ids:
        raise DonorPoolError("no candidate has the full covariate set required for matching")

    project_vec = np.asarray([project_covariates[c] for c in cfg.covariates], dtype=float)
    donor_mat = np.asarray(
        [[candidate_covariates[uid][c] for c in cfg.covariates] for uid in usable_ids],
        dtype=float,
    )
    z_project, z_donors, scale = _standardise(project_vec, donor_mat)
    weights = cfg.covariate_weights()

    deltas = z_donors - z_project
    distances = np.sqrt(np.sum(weights * deltas**2, axis=1))

    matches: list[DonorMatch] = []
    for i, uid in enumerate(usable_ids):
        cov = {c: float(candidate_covariates[uid][c]) for c in cfg.covariates}
        reason: str | None = None

        if uid in cfg.excluded_unit_ids:
            reason = "inside project leakage belt (potential spillover contamination)"
        elif cfg.caliper_sd is not None and np.max(np.abs(deltas[i])) > cfg.caliper_sd:
            worst = cfg.covariates[int(np.argmax(np.abs(deltas[i])))]
            reason = (
                f"outside common support: {worst} differs by "
                f"{abs(deltas[i][int(np.argmax(np.abs(deltas[i])))]):.2f} SD "
                f"(caliper {cfg.caliper_sd:.2f})"
            )
        elif (
            candidate_pre_observations is not None
            and candidate_pre_observations.get(uid, 0) < cfg.min_pre_observations
        ):
            reason = (
                f"insufficient clear pre-treatment observations "
                f"({candidate_pre_observations.get(uid, 0)} < {cfg.min_pre_observations})"
            )

        matches.append(
            DonorMatch(
                unit_id=uid,
                distance=float(distances[i]),
                covariates=cov,
                admitted=reason is None,
                exclusion_reason=reason,
            )
        )

    matches.sort(key=lambda m: (not m.admitted, m.distance))

    admitted = [m for m in matches if m.admitted]
    if len(admitted) > cfg.max_donors:
        capped: list[DonorMatch] = []
        for rank, m in enumerate(admitted):
            if rank < cfg.max_donors:
                capped.append(m)
            else:
                capped.append(
                    m.model_copy(
                        update={
                            "admitted": False,
                            "exclusion_reason": (
                                f"ranked {rank + 1} by covariate distance, beyond the "
                                f"max_donors cap of {cfg.max_donors}"
                            ),
                        }
                    )
                )
        matches = capped + [m for m in matches if not m.admitted]
        admitted = [m for m in matches if m.admitted]

    if len(admitted) < cfg.min_donors:
        raise DonorPoolError(
            f"only {len(admitted)} admissible donors for {project_unit_id!r}; "
            f"{cfg.min_donors} required. Widen the search region or relax the caliper, but "
            "do not estimate on an under-powered pool."
        )

    smd = {
        c: standardised_mean_difference(
            project_covariates[c],
            np.asarray([m.covariates[c] for m in admitted], dtype=float),
            float(scale[j]),
        )
        for j, c in enumerate(cfg.covariates)
    }

    return DonorPool(
        project_unit_id=project_unit_id,
        matches=tuple(matches),
        covariates=cfg.covariates,
        standardised_mean_differences=smd,
    )
