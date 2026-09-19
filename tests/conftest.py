"""Shared fixtures."""

from __future__ import annotations

import numpy as np
import pytest

from groundtruth.cases.registry import get_case
from groundtruth.core.evidence import Evidence, EvidenceBundle
from groundtruth.core.provenance import Provenance
from groundtruth.core.types import STANDARD_CAVEATS, VerdictLabel, VerificationVerdict


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(20260101)


@pytest.fixture
def factor_panel(rng: np.random.Generator):
    """A latent-factor panel with a known injected effect.

    Returns ``(outcomes, unit_ids, n_pre, true_effect)`` where ``outcomes`` is
    ``(n_periods, n_units)`` and column 0 is the treated unit.
    """
    n_periods, n_units, n_factors = 22, 25, 3
    factors = rng.normal(size=(n_factors, n_periods)).cumsum(axis=1) * 0.04 + 0.6
    loadings = rng.dirichlet(np.ones(n_factors), size=n_units)
    outcomes = (loadings @ factors).T + rng.normal(0.0, 0.004, size=(n_periods, n_units))
    n_pre = 12
    true_effect = 0.07
    outcomes[n_pre:, 0] += true_effect
    unit_ids = tuple(f"unit-{i:02d}" for i in range(n_units))
    return outcomes, unit_ids, n_pre, true_effect


@pytest.fixture
def null_panel(rng: np.random.Generator):
    """A panel with no treatment effect at all."""
    n_periods, n_units, n_factors = 22, 25, 3
    factors = rng.normal(size=(n_factors, n_periods)).cumsum(axis=1) * 0.04 + 0.6
    loadings = rng.dirichlet(np.ones(n_factors), size=n_units)
    outcomes = (loadings @ factors).T + rng.normal(0.0, 0.004, size=(n_periods, n_units))
    return outcomes, tuple(f"unit-{i:02d}" for i in range(n_units)), 12


@pytest.fixture
def provenance() -> Provenance:
    return Provenance.computed(source="test", method="fixture", stage="causal")


@pytest.fixture
def bundle(provenance: Provenance) -> EvidenceBundle:
    """A small bundle with a verdict, used by the grounding tests."""
    items = (
        Evidence(
            id="effect.point_estimate",
            label="Estimated incremental effect on ndvi",
            value=0.0421,
            unit="ndvi",
            provenance=provenance,
        ),
        Evidence(
            id="placebo.p_value",
            label="Permutation p-value",
            value=0.0385,
            provenance=provenance,
        ),
        Evidence(
            id="matching.n_donors_admitted",
            label="Donors admitted",
            value=32,
            provenance=provenance,
        ),
    )
    verdict = VerificationVerdict(
        label=VerdictLabel.DIVERGENT_FROM_CLAIM,
        rationale="Test verdict.",
        caveats=STANDARD_CAVEATS,
    )
    return EvidenceBundle(case_id="test-case", items=items, verdict=verdict)


@pytest.fixture
def kariba_case():
    return get_case("kariba-redd")
