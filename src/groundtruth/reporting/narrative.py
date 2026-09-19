"""Report generation: deterministic rendering, with optional GenAI narration.

The default renderer is a template. It is deterministic, always grounded by
construction, and produces a usable report with no model and no API key. This
matters: the scientific pipeline has no dependency on a language model.

When a GenAI provider is configured, the LLM is offered the evidence bundle and
asked to rewrite the deterministic report for a non-specialist audience. Its
output is then passed through :func:`~groundtruth.reporting.grounding.enforce_grounding`.
If it fails, the deterministic report is used instead. The system degrades to
correct-and-dry, never to fluent-and-wrong.
"""

from __future__ import annotations

from dataclasses import dataclass

from groundtruth.core.evidence import EvidenceBundle
from groundtruth.core.types import VerdictLabel
from groundtruth.logging import get_logger
from groundtruth.reporting.grounding import (
    GroundingReport,
    enforce_grounding,
    policy_for_bundle,
    verify_grounding,
)

logger = get_logger("reporting.narrative")

VERDICT_HEADLINES: dict[VerdictLabel, str] = {
    VerdictLabel.CONSISTENT_WITH_CLAIM: (
        "Independent estimate is consistent with the developer's claim"
    ),
    VerdictLabel.DIVERGENT_FROM_CLAIM: (
        "Independent estimate diverges from the developer's claim — accredited review advised"
    ),
    VerdictLabel.INCONCLUSIVE: (
        "Inconclusive — the available evidence does not support a screening outcome"
    ),
    VerdictLabel.NOT_ASSESSED: "Not assessed",
}


@dataclass(frozen=True)
class Report:
    """A rendered verification report and how it was produced."""

    case_id: str
    markdown: str
    generator: str
    """``'deterministic'`` or ``'genai:<provider>/<model>'``."""
    grounding: GroundingReport | None = None
    fell_back: bool = False
    fallback_reason: str | None = None


def render_deterministic(bundle: EvidenceBundle) -> str:
    """Render the evidence bundle as Markdown with no model involved.

    Grounded by construction: every figure is read directly out of the bundle.
    """
    lines: list[str] = []
    verdict = bundle.verdict

    lines.append(f"# Verification screening report — {bundle.case_id}")
    lines.append("")
    if verdict is not None:
        lines.append(f"**Outcome: {VERDICT_HEADLINES[verdict.label]}**")
        lines.append("")
        lines.append(verdict.rationale)
        lines.append("")

    if bundle.warnings:
        lines.append("## Run warnings")
        lines.append("")
        lines.extend(f"- {w}" for w in bundle.warnings)
        lines.append("")

    lines.append("## Evidence")
    lines.append("")
    lines.append("| Quantity | Value | Unit | Interval | Method | Source |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for item in bundle.items:
        interval = (
            f"[{item.confidence.lower:.4g}, {item.confidence.upper:.4g}] "
            f"({item.confidence.kind})"
            if item.confidence is not None
            else "—"
        )
        lines.append(
            f"| {item.label} | {item.rendered_value()} | {item.unit or '—'} | {interval} | "
            f"{item.provenance.method} | {item.provenance.source} |"
        )
    lines.append("")

    if verdict is not None and verdict.caveats:
        lines.append("## How to read this report")
        lines.append("")
        lines.extend(f"- {c}" for c in verdict.caveats)
        lines.append("")

    lines.append("## Provenance")
    lines.append("")
    for item in bundle.items:
        parts = [f"`{item.id}`: {item.provenance.method} via {item.provenance.source}"]
        if item.provenance.source_uri:
            parts.append(f"<{item.provenance.source_uri}>")
        if item.provenance.inputs:
            parts.append(f"derived from {', '.join(item.provenance.inputs)}")
        parts.append(f"fingerprint `{item.provenance.fingerprint()}`")
        lines.append(f"- " + " — ".join(parts))
    lines.append("")
    return "\n".join(lines)


NARRATION_SYSTEM_PROMPT = """\
You are a technical writer for an independent carbon-credit screening service.

You will receive a JSON evidence bundle produced by a deterministic analytical
pipeline, and a deterministic Markdown report rendered from it. Rewrite the
report so a non-specialist procurement or ESG analyst can act on it.

Hard rules, which are checked automatically after you respond:

1. Every number you write must appear in the evidence bundle. Do not compute new
   numbers, do not round to a different precision, do not annualise, extrapolate
   or convert units.
2. Never state or imply fraud, deception, intent, illegality, or any legal
   conclusion. A divergence between an independent estimate and a developer's
   claim means the claim warrants accredited review. That is all it means.
3. Never describe a vegetation index as an amount of carbon.
4. Never write that anything is proven, definitive, certain or conclusive.
5. Reproduce every caveat from the report's "How to read this report" section.
6. If the outcome is inconclusive, say so plainly. Do not soften it into a
   finding.

Write in plain English, in Markdown, under 700 words.
"""


def build_narration_prompt(bundle: EvidenceBundle, deterministic_markdown: str) -> str:
    """Build the user-side prompt handed to the language model."""
    return (
        "## Evidence bundle (JSON)\n\n"
        f"```json\n{bundle.to_json()}\n```\n\n"
        "## Deterministic report to rewrite\n\n"
        f"{deterministic_markdown}\n"
    )


def generate_report(
    bundle: EvidenceBundle,
    *,
    narrator: object | None = None,
) -> Report:
    """Produce a report, using ``narrator`` only if it can pass grounding checks.

    Args:
        bundle: The verified evidence bundle.
        narrator: Optional object with a ``complete(system, user) -> str`` method
            (see :mod:`groundtruth.reporting.providers`). When ``None``, the
            deterministic report is returned unchanged.

    Returns:
        A :class:`Report`. If narration fails grounding, the deterministic
        report is returned with ``fell_back=True`` and a stated reason.
    """
    deterministic = render_deterministic(bundle)
    if narrator is None:
        return Report(
            case_id=bundle.case_id, markdown=deterministic, generator="deterministic"
        )

    policy = policy_for_bundle(bundle)
    try:
        completion = narrator.complete(  # type: ignore[attr-defined]
            NARRATION_SYSTEM_PROMPT, build_narration_prompt(bundle, deterministic)
        )
    except Exception as exc:  # noqa: BLE001 - any provider failure must degrade safely
        logger.warning("narration provider failed, using deterministic report: %s", exc)
        return Report(
            case_id=bundle.case_id,
            markdown=deterministic,
            generator="deterministic",
            fell_back=True,
            fallback_reason=f"narration provider error: {exc}",
        )

    report = verify_grounding(completion, bundle, policy)
    provider_name = getattr(narrator, "name", "unknown")
    if not report.grounded:
        logger.warning("narration rejected for %s: %s", bundle.case_id, report.summary())
        return Report(
            case_id=bundle.case_id,
            markdown=deterministic,
            generator="deterministic",
            grounding=report,
            fell_back=True,
            fallback_reason=report.summary(),
        )

    enforce_grounding(completion, bundle, policy)
    return Report(
        case_id=bundle.case_id,
        markdown=completion,
        generator=f"genai:{provider_name}",
        grounding=report,
    )
