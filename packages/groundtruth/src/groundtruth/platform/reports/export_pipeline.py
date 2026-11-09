"""The report export pipeline: a report is verified against its own bundle before it leaves (#38).

**Owner: Bhumi.** Viraj decides what a report contains and how it is caveated (C6); this module
decides nothing about content. It makes four guarantees about whatever is exported:

1. **It passes** :func:`~groundtruth.contracts.grounding.verify_grounding` against its own
   bundle, whoever wrote it. The deterministic report is re-checked too: "grounded by
   construction" is a claim to test at the door, not to assume.
2. **A narration that fails is refused, never substituted.** An export is a deliverable, so a
   narrated report that fails verification stops the export with a structured error. (The
   inline ``report_markdown`` returned by ``/verify`` and ``/runs`` keeps its older behaviour,
   :func:`~groundtruth.platform.reports.narrative.generate_report`: a failed narration falls
   back to the deterministic report, labelled. That is ADR-007; an export does not use it.)
3. **Provenance and the simulated-data warning survive.** A language model may rewrite the
   prose and drop a section, and the grounding check does not require either. So when a narrated
   report lacks the Provenance section, the deterministic one is appended verbatim; when a
   simulated run's report does not say so, the bundle's own warning is put at the top.
4. **It says who wrote it.** ``generator`` is ``deterministic`` or ``genai:<provider>``.

What the grounding check trusts
-------------------------------
:func:`~groundtruth.contracts.grounding.verify_grounding` accepts a number only if it is an
evidence value, an interval bound, a year, or a small integer. That leaves out the thresholds
the engine writes into its own verdict text ("significance level 0.050", "limit 0.30"), so the
deterministic report fails the check for 7 of the 27 cases. The proper fix is in
``contracts/grounding`` (C1/C6) and is not made here.

Meanwhile this pipeline trusts numbers from exactly the fields listed in
:data:`ENGINE_WRITTEN_NUMBER_SOURCES`, and from nowhere else:

* ``verdict.rationale``: the sentence the engine's verdict gate writes, thresholds included.

Not any other string in the bundle (warnings, caveats, notes, provenance parameters), and never
anything a narrator wrote: the policy is built from the bundle *before* narration and the
narrator's text is only ever checked against it.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace

from groundtruth.contracts.errors import GroundTruthError
from groundtruth.contracts.evidence import EvidenceBundle
from groundtruth.contracts.grounding import (
    NUMBER_PATTERN,
    GroundingPolicy,
    GroundingReport,
    mask_identifiers,
    policy_for_bundle,
    verify_grounding,
)
from groundtruth.logging import get_logger
from groundtruth.platform.api.error_envelope import redact_secrets
from groundtruth.platform.reports.exporters import SIMULATED_BANNER, bundle_is_simulated
from groundtruth.platform.reports.narrative import (
    NARRATION_SYSTEM_PROMPT,
    build_narration_prompt,
    render_deterministic,
)

logger = get_logger("reporting.export")

ENGINE_WRITTEN_NUMBER_SOURCES: tuple[str, ...] = ("verdict.rationale",)
"""The only bundle fields whose numbers the export check trusts beyond the evidence values."""

_SOURCE_READERS: dict[str, Callable[[EvidenceBundle], str | None]] = {
    "verdict.rationale": lambda b: b.verdict.rationale if b.verdict is not None else None,
}


class ReportExportError(GroundTruthError):
    """A report could not be exported. The message is safe to show a client."""

    code = "report_export_error"


class NarrationFailedError(ReportExportError):
    """The narration provider failed, so there is no narrated report to verify."""

    code = "narration_failed"


class NarrationNotGroundedError(ReportExportError):
    """The narrated report failed verification against its bundle and was not exported."""

    code = "narration_not_grounded"


class ReportNotGroundedError(ReportExportError):
    """The report that would be exported fails verification: a defect, never shipped."""

    code = "report_not_grounded"


@dataclass(frozen=True)
class ExportedReport:
    """A report that passed verification, and how it was produced."""

    case_id: str
    markdown: str
    generator: str
    """``'deterministic'`` or ``'genai:<provider>'``."""
    grounding: GroundingReport
    simulated: bool
    appended: tuple[str, ...] = ()
    """Sections added by this pipeline to a narrated report: ``provenance``, ``simulated_warning``."""


def engine_written_numbers(bundle: EvidenceBundle) -> tuple[float, ...]:
    """The numbers in :data:`ENGINE_WRITTEN_NUMBER_SOURCES`, sorted and unique."""
    values: set[float] = set()
    for source in ENGINE_WRITTEN_NUMBER_SOURCES:
        text = _SOURCE_READERS[source](bundle)
        if not text:
            continue
        for match in NUMBER_PATTERN.finditer(mask_identifiers(text)):
            try:
                values.add(float(match.group(0).replace(",", "")))
            except ValueError:
                continue
    return tuple(sorted(values))


def export_policy(bundle: EvidenceBundle) -> GroundingPolicy:
    """The grounding policy for an export: the contract's, plus the engine-written numbers.

    Built from the bundle alone, so no narrator can widen it.
    """
    base = policy_for_bundle(bundle)
    return replace(
        base,
        extra_allowed_values=tuple(
            sorted({*base.extra_allowed_values, *engine_written_numbers(bundle)})
        ),
    )


def _has_provenance_section(markdown: str) -> bool:
    return re.search(r"^#{1,6}\s*provenance\b", markdown, re.IGNORECASE | re.MULTILINE) is not None


def _mentions_simulated(markdown: str) -> bool:
    lowered = markdown.lower()
    return "simulated" in lowered or "synthetic" in lowered


def _simulated_notice(bundle: EvidenceBundle) -> str:
    """The bundle's own simulated-data warning, or the standard banner if it carries none."""
    for warning in bundle.warnings:
        if "SIMULATED" in warning.upper():
            return warning
    return SIMULATED_BANNER


def _ensure_required_sections(
    markdown: str, bundle: EvidenceBundle, deterministic: str
) -> tuple[str, tuple[str, ...]]:
    """Put back what a narration may have dropped. Only ever adds existing, grounded content."""
    appended: list[str] = []
    if not _has_provenance_section(markdown):
        marker = deterministic.find("## Provenance")
        if marker >= 0:
            markdown = markdown.rstrip() + "\n\n" + deterministic[marker:].rstrip() + "\n"
            appended.append("provenance")
    if bundle_is_simulated(bundle) and not _mentions_simulated(markdown):
        markdown = f"> **{_simulated_notice(bundle)}**\n\n{markdown}"
        appended.append("simulated_warning")
    return markdown, tuple(appended)


def _narrate(
    bundle: EvidenceBundle, narrator: object, deterministic: str, policy: GroundingPolicy
) -> tuple[str, str]:
    """The narrator's text and generator label, only if it passes verification."""
    try:
        completion = narrator.complete(  # type: ignore[attr-defined]
            NARRATION_SYSTEM_PROMPT, build_narration_prompt(bundle, deterministic)
        )
    except Exception as exc:
        # The provider's own words stay in the log (minus secrets): they can carry a key or a URL.
        logger.warning(
            "narration provider failed for %s: %s",
            bundle.case_id,
            redact_secrets(f"{type(exc).__name__}: {exc}"),
        )
        raise NarrationFailedError(
            "The narration provider failed, so no narrated report was produced."
        ) from None
    report = verify_grounding(completion, bundle, policy)
    if not report.grounded:
        logger.warning("narration rejected for %s: %s", bundle.case_id, report.summary())
        raise NarrationNotGroundedError(
            "The narrated report failed verification against its own evidence bundle and was "
            f"not exported: {report.summary()}"
        )
    return completion, f"genai:{getattr(narrator, 'name', 'unknown')}"


def build_export_report(
    bundle: EvidenceBundle, *, narrator: object | None = None
) -> ExportedReport:
    """The report to export for ``bundle``, verified, or an error that stops the export.

    Args:
        bundle: The evidence bundle the report describes.
        narrator: Optional object with ``complete(system, user) -> str``. When ``None``, the
            deterministic report is exported.

    Raises:
        NarrationFailedError: the narrator raised.
        NarrationNotGroundedError: the narrated text failed verification.
        ReportNotGroundedError: the final report fails verification, which is a defect.
    """
    policy = export_policy(bundle)
    deterministic = render_deterministic(bundle)
    if narrator is None:
        markdown, generator = deterministic, "deterministic"
        appended: tuple[str, ...] = ()
    else:
        narrated, generator = _narrate(bundle, narrator, deterministic, policy)
        markdown, appended = _ensure_required_sections(narrated, bundle, deterministic)

    final = verify_grounding(markdown, bundle, policy)
    if not final.grounded:
        logger.error("report for %s failed its export check: %s", bundle.case_id, final.summary())
        raise ReportNotGroundedError(
            f"The {generator} report for {bundle.case_id!r} failed verification against its own "
            f"evidence bundle and was not exported: {final.summary()}"
        )
    return ExportedReport(
        case_id=bundle.case_id,
        markdown=markdown,
        generator=generator,
        grounding=final,
        simulated=bundle_is_simulated(bundle),
        appended=appended,
    )


__all__ = [
    "ENGINE_WRITTEN_NUMBER_SOURCES",
    "ExportedReport",
    "NarrationFailedError",
    "NarrationNotGroundedError",
    "ReportExportError",
    "ReportNotGroundedError",
    "build_export_report",
    "engine_written_numbers",
    "export_policy",
]
