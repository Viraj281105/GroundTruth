"""Grounding verification for generated narrative text.

The architecture claim "the model explains verified numbers, it never invents
them" is only worth making if it is enforced. This module enforces it.

Three checks run against every piece of generated prose:

1. **Numeric grounding.** Every number in the text must match a value in the
   evidence bundle within tolerance, or appear in an allow-list of structural
   numbers (years, section numbers, percentages of a stated figure).
2. **Prohibited assertions.** The text must not accuse, allege fraud, or state
   a legal conclusion. GroundTruth is a screening tool; it has no standing to
   find wrongdoing.
3. **Required caveats.** The verdict's caveats must survive into the narrative.

A failure raises :class:`~groundtruth.core.errors.GroundingViolationError`. The
report is rejected rather than published with a warning, because a plausible
sentence containing an invented number is more dangerous than no report at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from groundtruth.core.errors import GroundingViolationError
from groundtruth.core.evidence import EvidenceBundle

NUMBER_PATTERN = re.compile(r"-?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?")

PROHIBITED_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bfraud(?:ulent|ulently)?\b", "alleges fraud"),
    (r"\bscam\b", "alleges a scam"),
    (r"\bdeliberate(?:ly)? (?:inflat|overstat|falsif|misrepresent)", "alleges intent"),
    (r"\b(?:lied|lying|deceiv\w*)\b", "alleges deception"),
    (r"\bcriminal\b", "asserts a legal conclusion"),
    (r"\billegal(?:ly)?\b", "asserts a legal conclusion"),
    (r"\bguilty\b", "asserts a legal conclusion"),
    (r"\bproves? that\b", "overstates evidential strength"),
    (r"\bconclusively (?:shows?|demonstrates?|proves?)\b", "overstates evidential strength"),
    (r"\bdefinitiv(?:e|ely)\b", "overstates evidential strength"),
    (r"\bcertainly\b", "overstates evidential strength"),
    (
        r"ndvi\s+(?:of\s+)?[\d.]+\s*(?:=|equals|means|is)\s*[\d.]+\s*(?:tco2e?|tonnes? of carbon)",
        "converts a spectral index directly into carbon",
    ),
)

STRUCTURAL_NUMBER_CONTEXT = re.compile(
    r"(?:19|20)\d{2}|\bsection\b|\bfigure\b|\btable\b", re.IGNORECASE
)


@dataclass
class GroundingPolicy:
    """Tunable rules for what counts as grounded text."""

    relative_tolerance: float = 0.02
    """Allowed relative difference between a narrated number and its evidence value."""

    allow_years: bool = True
    """Permit four-digit years between 1970 and 2100 without an evidence match."""

    allow_small_integers: bool = True
    """Permit integers 0-10, which appear as counts and list markers in prose."""

    extra_allowed_values: tuple[float, ...] = ()
    """Additional literals the narrative may legitimately contain."""

    required_phrases: tuple[str, ...] = ()
    """Substrings that must appear, e.g. the caveats attached to the verdict."""

    prohibited_patterns: tuple[tuple[str, str], ...] = PROHIBITED_PATTERNS


@dataclass
class GroundingReport:
    """The outcome of verifying one piece of narrative text."""

    grounded: bool
    ungrounded_numbers: tuple[str, ...] = ()
    prohibited_findings: tuple[str, ...] = ()
    missing_phrases: tuple[str, ...] = ()
    checked_numbers: int = 0
    matched_numbers: int = 0
    details: list[str] = field(default_factory=list)

    @property
    def grounding_rate(self) -> float:
        """Share of narrated numbers that matched an evidence value."""
        if self.checked_numbers == 0:
            return 1.0
        return self.matched_numbers / self.checked_numbers

    def summary(self) -> str:
        """One-line summary for logs and the hallucination evaluation harness."""
        if self.grounded:
            return (
                f"grounded: {self.matched_numbers}/{self.checked_numbers} numeric claims traced "
                "to evidence"
            )
        problems = []
        if self.ungrounded_numbers:
            problems.append(f"ungrounded numbers {list(self.ungrounded_numbers)}")
        if self.prohibited_findings:
            problems.append(f"prohibited assertions: {list(self.prohibited_findings)}")
        if self.missing_phrases:
            problems.append(f"missing required caveats: {len(self.missing_phrases)}")
        return "ungrounded — " + "; ".join(problems)


def _parse_number(token: str) -> float | None:
    try:
        return float(token.replace(",", ""))
    except ValueError:
        return None


def _matches_any(value: float, candidates: list[float], tolerance: float) -> bool:
    for candidate in candidates:
        scale = max(abs(candidate), abs(value), 1e-9)
        if abs(candidate - value) <= tolerance * scale:
            return True
        # Percentage and per-mille renderings of the same underlying value.
        for factor in (100.0, 0.01):
            scaled = candidate * factor
            if abs(scaled - value) <= tolerance * max(abs(scaled), abs(value), 1e-9):
                return True
    return False


def verify_grounding(
    text: str,
    bundle: EvidenceBundle,
    policy: GroundingPolicy | None = None,
) -> GroundingReport:
    """Check generated ``text`` against ``bundle`` and return a report.

    This function never raises on ungrounded content; use
    :func:`enforce_grounding` when a violation should stop the pipeline.
    """
    pol = policy or GroundingPolicy()
    evidence_values = list(bundle.numeric_values().values())
    evidence_values.extend(pol.extra_allowed_values)
    for item in bundle.items:
        if item.confidence is not None:
            evidence_values.extend([item.confidence.lower, item.confidence.upper])
            evidence_values.append(item.confidence.level)

    ungrounded: list[str] = []
    checked = 0
    matched = 0

    for match in NUMBER_PATTERN.finditer(text):
        token = match.group(0)
        value = _parse_number(token)
        if value is None:
            continue

        window = text[max(0, match.start() - 30) : match.end() + 30]
        if (
            pol.allow_years
            and float(value).is_integer()
            and 1970 <= value <= 2100
            and (len(token) == 4 or STRUCTURAL_NUMBER_CONTEXT.search(window))
        ):
            continue
        if pol.allow_small_integers and float(value).is_integer() and 0 <= value <= 10:
            continue

        checked += 1
        if _matches_any(value, evidence_values, pol.relative_tolerance):
            matched += 1
        else:
            ungrounded.append(token)

    prohibited: list[str] = []
    lowered = text.lower()
    for pattern, description in pol.prohibited_patterns:
        if re.search(pattern, lowered, re.IGNORECASE):
            prohibited.append(description)

    missing = tuple(p for p in pol.required_phrases if p.lower() not in lowered)

    report = GroundingReport(
        grounded=not ungrounded and not prohibited and not missing,
        ungrounded_numbers=tuple(dict.fromkeys(ungrounded)),
        prohibited_findings=tuple(dict.fromkeys(prohibited)),
        missing_phrases=missing,
        checked_numbers=checked,
        matched_numbers=matched,
    )
    if ungrounded:
        report.details.append(
            "These figures appear in the narrative but not in the evidence bundle: "
            + ", ".join(report.ungrounded_numbers)
        )
    return report


def enforce_grounding(
    text: str,
    bundle: EvidenceBundle,
    policy: GroundingPolicy | None = None,
) -> str:
    """Return ``text`` if it is fully grounded, otherwise raise.

    Raises:
        GroundingViolationError: if any check fails.
    """
    report = verify_grounding(text, bundle, policy)
    if not report.grounded:
        raise GroundingViolationError(
            f"generated narrative rejected for case {bundle.case_id!r}: {report.summary()}"
        )
    return text


def policy_for_bundle(bundle: EvidenceBundle) -> GroundingPolicy:
    """Build the policy for a bundle, requiring its verdict caveats to be carried."""
    required: tuple[str, ...] = ()
    if bundle.verdict is not None:
        # Require a distinctive fragment of each caveat rather than the full
        # sentence, so the model may re-flow wording without dropping meaning.
        required = tuple(
            c.split(";")[0].split(",")[0].strip().lower()[:60] for c in bundle.verdict.caveats
        )
    return GroundingPolicy(required_phrases=required)
