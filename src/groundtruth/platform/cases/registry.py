"""Case registry: loading structured case definitions from ``cases/``.

A case definition is a YAML file describing a real project, its registry claim,
its analysis window, and the donor-search region. Keeping cases as data rather
than code means adding the next project is a pull request against a single file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from groundtruth.contracts.errors import CaseDefinitionError
from groundtruth.contracts.identifiers import DatasetRef
from groundtruth.contracts.request import (
    AnalysisRequest,
    AnalysisWindow,
    ClaimUnderTest,
    DonorSpec,
    EstimationSpec,
    RobustnessSpec,
    UnitRef,
)
from groundtruth.contracts.types import Indicator, MethodologyStandard, ProjectClaim


@dataclass(frozen=True)
class CaseDefinition:
    """A fully specified verification case."""

    case_id: str
    claim: ProjectClaim
    indicator: Indicator
    window: AnalysisWindow
    donor_search_region: str
    donor_pool_size: int = 60
    excluded_donor_ids: tuple[str, ...] = ()
    covariates: tuple[str, ...] = ()
    known_reference: dict[str, Any] = field(default_factory=dict)
    """Published third-party findings used for validation. Never an input to the estimate."""
    ecosystem: str = "unspecified"
    notes: str = ""
    status: str = "scaffolded"
    """``scaffolded`` | ``data-wired`` | ``analysed``. Nothing is ``analysed`` yet."""

    @property
    def is_analysed(self) -> bool:
        """True only once a real, reviewed analysis has been run for this case."""
        return self.status == "analysed"

    def to_request(
        self,
        *,
        data_mode: str = "simulated",
        datasets: tuple[DatasetRef, ...] = (),
        seed: int = 20260101,
        candidates: tuple[UnitRef, ...] = (),
        requested_by: str | None = None,
        min_donors: int | None = None,
    ) -> AnalysisRequest:
        """Build the contract request the engine consumes.

        This is the platform's translation step. The engine never reads a case
        YAML file, a database row or an environment variable: everything it
        needs arrives in this object, which is what makes a run replayable
        months later.

        The ``known_reference`` block is deliberately **not** carried across.
        It records a published third-party finding for post-hoc validation, and
        feeding it to the engine would destroy the independence the whole
        system exists to provide.
        """
        donors = DonorSpec(
            candidates=candidates,
            search_region=self.donor_search_region.strip(),
            pool_size=self.donor_pool_size,
            min_donors=min_donors if min_donors is not None else DonorSpec().min_donors,
            max_donors=max(
                DonorSpec().max_donors,
                min_donors if min_donors is not None else 0,
            ),
            covariates=self.covariates or DonorSpec().covariates,
            excluded_unit_ids=self.excluded_donor_ids,
        )
        return AnalysisRequest(
            case_id=self.case_id,
            project=UnitRef(
                unit_id=self.case_id,
                area_ha=self.claim.project_area_ha,
            ),
            claim=ClaimUnderTest(
                name=self.claim.name,
                country=self.claim.country,
                standard=self.claim.standard.value,
                registry_id=self.claim.registry_id,
                project_area_ha=self.claim.project_area_ha,
                claimed_credits_tco2e=self.claim.claimed_credits_tco2e,
                crediting_period_start=(
                    self.claim.crediting_period_start.isoformat()
                    if self.claim.crediting_period_start
                    else None
                ),
                crediting_period_end=(
                    self.claim.crediting_period_end.isoformat()
                    if self.claim.crediting_period_end
                    else None
                ),
                source_uri=self.claim.claim_source_uri,
            ),
            indicator=self.indicator,
            window=self.window,
            donors=donors,
            estimation=EstimationSpec(),
            robustness=RobustnessSpec(),
            datasets=datasets,
            seed=seed,
            data_mode=data_mode,  # type: ignore[arg-type]
            requested_by=requested_by,
        )


def _require(payload: dict[str, Any], key: str, case_path: Path) -> Any:
    if key not in payload:
        raise CaseDefinitionError(f"{case_path}: missing required key {key!r}")
    return payload[key]


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def load_case(path: Path) -> CaseDefinition:
    """Load and validate one case definition file."""
    if not path.exists():
        raise CaseDefinitionError(f"case definition not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CaseDefinitionError(f"{path}: case definition must be a YAML mapping")

    case_id = str(_require(payload, "case_id", path))
    project = _require(payload, "project", path)
    window_raw = _require(payload, "analysis_window", path)
    analysis = _require(payload, "analysis", path)

    try:
        standard = MethodologyStandard(project.get("standard", "Other"))
    except ValueError as exc:
        raise CaseDefinitionError(f"{path}: unknown standard {project.get('standard')!r}") from exc

    try:
        indicator = Indicator(analysis.get("indicator", "ndvi"))
    except ValueError as exc:
        raise CaseDefinitionError(
            f"{path}: unknown indicator {analysis.get('indicator')!r}"
        ) from exc

    claim = ProjectClaim(
        case_id=case_id,
        name=str(_require(project, "name", path)),
        country=str(project.get("country", "unknown")),
        standard=standard,
        registry_id=project.get("registry_id"),
        project_area_ha=project.get("area_ha"),
        crediting_period_start=_parse_date(project.get("crediting_period_start")),
        crediting_period_end=_parse_date(project.get("crediting_period_end")),
        claimed_credits_tco2e=project.get("claimed_credits_tco2e"),
        claim_source_uri=project.get("source_uri"),
        boundary_path=project.get("boundary_path"),
    )

    try:
        window = AnalysisWindow(
            pre_start=int(_require(window_raw, "pre_start", path)),
            pre_end=int(_require(window_raw, "pre_end", path)),
            post_start=int(_require(window_raw, "post_start", path)),
            post_end=int(_require(window_raw, "post_end", path)),
        )
    except ValueError as exc:
        raise CaseDefinitionError(f"{path}: {exc}") from exc

    return CaseDefinition(
        case_id=case_id,
        claim=claim,
        indicator=indicator,
        window=window,
        donor_search_region=str(analysis.get("donor_search_region", "unspecified")),
        donor_pool_size=int(analysis.get("donor_pool_size", 60)),
        excluded_donor_ids=tuple(analysis.get("excluded_donor_ids", []) or []),
        covariates=tuple(analysis.get("covariates", []) or []),
        known_reference=payload.get("known_reference", {}) or {},
        ecosystem=str(project.get("ecosystem", "unspecified")),
        notes=str(payload.get("notes", "")),
        status=str(payload.get("status", "scaffolded")),
    )


def cases_directory(root: Path | None = None) -> Path:
    """Resolve the cases directory, defaulting to the packaged settings value."""
    if root is not None:
        return root
    from groundtruth.platform.config import get_settings

    return get_settings().cases_dir


def list_cases(root: Path | None = None) -> list[str]:
    """Return the ids of every case definition on disk, sorted."""
    directory = cases_directory(root)
    if not directory.exists():
        return []
    return sorted(p.stem for p in directory.glob("*.yaml"))


def get_case(case_id: str, root: Path | None = None) -> CaseDefinition:
    """Load one case by id.

    Raises:
        CaseDefinitionError: if the case does not exist.
    """
    directory = cases_directory(root)
    path = directory / f"{case_id}.yaml"
    if not path.exists():
        available = ", ".join(list_cases(root)) or "none"
        raise CaseDefinitionError(f"unknown case {case_id!r}. Available cases: {available}")
    case = load_case(path)
    if case.case_id != case_id:
        raise CaseDefinitionError(
            f"{path}: case_id {case.case_id!r} does not match filename {case_id!r}"
        )
    return case


def load_all_cases(root: Path | None = None) -> dict[str, CaseDefinition]:
    """Load every case definition, keyed by id."""
    return {cid: get_case(cid, root) for cid in list_cases(root)}
