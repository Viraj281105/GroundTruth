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

CASE_STATUSES: tuple[str, ...] = ("scaffolded", "data-wired", "analysed")
"""The statuses a case may have. Mirrors ``store.models.CASE_STATUSES``, which the database
enforces; a test keeps the two equal, since this module must load without SQLAlchemy."""

ERROR_INVALID_CASE = "invalid_case"
ERROR_STATUS_REQUIRES_REVIEW = "case_status_requires_review"
ERROR_MIN_DONORS_BELOW_FLOOR = "min_donors_below_case_floor"


class CaseValidationError(CaseDefinitionError):
    """A case, or a request about one, is invalid in a way the caller can fix.

    Carries a stable ``code``, the offending ``field`` where there is one, and a ``hint`` that
    says what to do. The API turns it into a structured 422 instead of a bare 500.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = ERROR_INVALID_CASE,
        field: str | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.field = field
        self.hint = hint

    def describe(self) -> str:
        """The message, led by the field name when there is one."""
        return f"{self.field}: {self.message}" if self.field else self.message


def check_creatable_status(status: str | None) -> None:
    """Refuse any status a case may not be created with.

    Cases made through the API start as ``scaffolded``. ``analysed`` needs a reviewed run
    (coordination point C7, issue #4), and nothing in the code can establish that yet, so it
    is refused here and again by :class:`CaseDefinition` itself.

    Raises:
        CaseValidationError: for anything but an omitted status or ``scaffolded``.
    """
    if status is None or status == "scaffolded":
        return
    if status == "analysed":
        raise CaseValidationError(
            "a case cannot be created as 'analysed': that status needs a run reviewed by both "
            "owners (coordination point C7, issue #4), and no such review exists yet",
            code=ERROR_STATUS_REQUIRES_REVIEW,
            field="status",
            hint="Omit status. New cases start as 'scaffolded'.",
        )
    raise CaseValidationError(
        f"status {status!r} cannot be set when creating a case",
        field="status",
        hint="Omit status. New cases start as 'scaffolded'.",
    )


@dataclass(frozen=True)
class CaseDefinition:
    """A fully specified verification case."""

    case_id: str
    claim: ProjectClaim
    indicator: Indicator
    window: AnalysisWindow
    donor_search_region: str
    donor_pool_size: int = 60
    min_donors: int | None = None
    """Admitted-donor floor for this case. ``None`` means the contract default."""
    max_donors: int | None = None
    """Admitted-donor cap for this case. ``None`` means the contract default."""
    excluded_donor_ids: tuple[str, ...] = ()
    covariates: tuple[str, ...] = ()
    known_reference: dict[str, Any] = field(default_factory=dict)
    """Published third-party findings used for validation. Never an input to the estimate."""
    ecosystem: str = "unspecified"
    notes: str = ""
    status: str = "scaffolded"
    """``scaffolded`` | ``data-wired`` | ``analysed``. Nothing is ``analysed`` yet."""

    def __post_init__(self) -> None:
        """The one guard on a case's status.

        Every way a case comes to exist (the YAML loader, ``create_and_register_case``, the
        database upsert and project seeding, which build from a loaded case) constructs this
        class, so the rule cannot be bypassed by taking a different path.
        """
        if self.status not in CASE_STATUSES:
            raise CaseValidationError(
                f"unknown status {self.status!r}; expected one of {list(CASE_STATUSES)}",
                field="status",
                hint="Check the spelling; 'analysed' is the British spelling used here.",
            )
        if self.status == "analysed":
            # Always refused for now (D2). Accepting it needs a review record both owners have
            # agreed the format of, and a real run to point it at; observed runs are still 501.
            raise CaseValidationError(
                f"case {self.case_id!r} cannot have status 'analysed': that status needs a run "
                "reviewed by both owners (coordination point C7, issue #4), and no real run "
                "exists to review yet",
                code=ERROR_STATUS_REQUIRES_REVIEW,
                field="status",
                hint="Use 'scaffolded' or 'data-wired'.",
            )

    def resolve_min_donors(self, requested: int | None) -> int | None:
        """The ``min_donors`` a request should use: the case's own unless it asks for more.

        The case's floor is its pre-registered refusal rule. A request may ask for a *higher*
        floor, which only makes the run stricter; a *lower* one is how a refusal gets forced
        into a number, so it is refused. ``None`` means the request did not say.

        Raises:
            CaseValidationError: if ``requested`` is below the case's own floor.
        """
        if requested is None:
            return None
        if self.min_donors is not None and requested < self.min_donors:
            raise CaseValidationError(
                f"min_donors={requested} is below this case's floor of {self.min_donors}. "
                "The floor is the case's pre-registered refusal rule, and a request may raise "
                "it but not lower it",
                code=ERROR_MIN_DONORS_BELOW_FLOOR,
                field="min_donors",
                hint=f"Omit min_donors to use {self.min_donors}, or send a higher value.",
            )
        return requested

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

        ``min_donors`` overrides the case's own floor, which overrides the
        contract default. The cap is raised to meet the floor rather than letting
        the contract reject a request whose floor is above it.
        """
        defaults = DonorSpec()
        case_min = self.min_donors if self.min_donors is not None else defaults.min_donors
        case_max = self.max_donors if self.max_donors is not None else defaults.max_donors
        floor = min_donors if min_donors is not None else case_min
        donors = DonorSpec(
            candidates=candidates,
            search_region=self.donor_search_region.strip(),
            pool_size=self.donor_pool_size,
            min_donors=floor,
            max_donors=max(case_max, floor),
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


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def load_case(path: Path) -> CaseDefinition:
    """Load and validate one case definition file."""
    if not path.exists():
        raise CaseDefinitionError(f"case definition not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return case_from_payload(payload, path)


def case_from_payload(payload: Any, path: Path) -> CaseDefinition:
    """Validate a parsed case definition. ``path`` only labels the error messages.

    Split out of :func:`load_case` so a case can be checked, down to its status, before
    anything is written to disk.
    """
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

    try:
        return CaseDefinition(
            case_id=case_id,
            claim=claim,
            indicator=indicator,
            window=window,
            donor_search_region=str(analysis.get("donor_search_region", "unspecified")),
            donor_pool_size=int(analysis.get("donor_pool_size", 60)),
            min_donors=_optional_int(analysis.get("min_donors")),
            max_donors=_optional_int(analysis.get("max_donors")),
            excluded_donor_ids=tuple(analysis.get("excluded_donor_ids", []) or []),
            covariates=tuple(analysis.get("covariates", []) or []),
            known_reference=payload.get("known_reference", {}) or {},
            ecosystem=str(project.get("ecosystem", "unspecified")),
            notes=str(payload.get("notes", "")),
            status=str(payload.get("status", "scaffolded")),
        )
    except CaseValidationError as exc:
        # Name the file: the status guard fires in the constructor, which cannot know it.
        raise CaseValidationError(
            f"{path}: {exc.message}", code=exc.code, field=exc.field, hint=exc.hint
        ) from exc


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
