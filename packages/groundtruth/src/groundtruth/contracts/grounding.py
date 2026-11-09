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

A failure raises :class:`~groundtruth.contracts.errors.GroundingViolationError`. The
report is rejected rather than published with a warning, because a plausible
sentence containing an invented number is more dangerous than no report at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from groundtruth.contracts.errors import GroundingViolationError
from groundtruth.contracts.evidence import EvidenceBundle
from groundtruth.contracts.types import VerdictLabel

# A leading '-' counts as a minus sign only when it does not follow a word
# character, so identifiers like 'donor-031' are not read as the value -31.
NUMBER_PATTERN = re.compile(r"(?<![\w-])-?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?")

URL_PATTERN = re.compile(r"https?://\S+|<[^>\s]+>")

NEGATED_ASSERTION_PATTERNS: tuple[str, ...] = (
    r"not evidence of (?:fraud|wrongdoing|deception)",
    r"not a finding of (?:fraud|wrongdoing|deception)",
    r"(?:(?:is|are|does|do|did|can|cannot) not|never) "
    r"(?:prove|proves|imply|implies|mean|means|establish|show|shows|demonstrate|demonstrates)"
    r"(?:\s+(?:that\s+)?(?:the\s+)?(?:project|intervention)\s+(?:caused|causes|drove|created))?",
    r"not (?:evidence|proof|a finding) (?:of|that) (?:the )?(?:project|intervention) "
    r"(?:caused|causes|drove|created)",
    r"never (?:a finding of|evidence of|proof of)",
    r"is not a probability (?:of|that)",
    r"(?:must|should) not be (?:presented|read|reported) as (?:the |a )?"
    r"(?:definitive|conclusive|certain)?",
)
"""Phrasings that *disclaim* a prohibited assertion rather than making it.

The standard caveats say "not evidence of fraud", which contains the word the
fraud filter looks for. Without this exemption the system would reject its own
mandatory disclaimer, which would be both wrong and quietly catastrophic: the
safe fallback would fire on every correctly-caveated report.
"""

PROHIBITED_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bfraud(?:ulent|ulently)?\b", "alleges fraud"),
    (r"\bscam\b", "alleges a scam"),
    (r"\b(?:grift|hoax|swindle|ponzi|sham)\b", "alleges a scam or hoax"),
    (
        r"\b(?:embezzl\w*|brib\w*|corrupt\w*|kickback\w*|launder\w*|theft|stole)\b",
        "alleges criminal misconduct",
    ),
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
        r"\b(?:project|intervention)\s+(?:caused|causes|drove|created)\b",
        "asserts direct causal attribution beyond observational screening",
    ),
    (
        r"ndvi\s+(?:of\s+)?[\d.]+\s*(?:=|equals|means|is)\s*[\d.]+\s*(?:tco2e?|tonnes? of carbon)",
        "converts a spectral index directly into carbon",
    ),
)

_CARBON_UNIT_PATTERN = re.compile(
    r"\b(?:tonnes?\s+of\s+carbon(?:\s+credits?)?|tons?\s+of\s+carbon(?:\s+credits?)?"
    r"|t\s*co2e?|tonnes?\s+of\s+co2e?|tons?\s+of\s+co2e?"
    r"|carbon\s+credits?|credits?\s+per\s+hectare)\b",
    re.IGNORECASE,
)

_NEGATED_CARBON_UNIT_PATTERN = re.compile(
    r"\b(?:not|no|never|without|cannot\s+be\s+converted\s+(?:to|into))\s+"
    r"(?:in\s+|expressed\s+in\s+|into\s+)?"
    r"(?:tonnes?\s+of\s+carbon|tons?\s+of\s+carbon|t\s*co2e?|carbon\s+credits?"
    r"|credits?\s+per\s+hectare|tonnes?\s+of\s+co2e?|tons?\s+of\s+co2e?)\b",
    re.IGNORECASE,
)

_CONTEXT_INVERSION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:caused|resulted in|led to|suffered|experienced|drove|triggered|accelerated"
        r"|worsened)\b(?![^.]*\b(?:avoided|reduced|prevented|halted|curbed|less)\b)"
        r"[^.]{0,60}\b(?:forest destruction|habitat loss|deforestation|ecocide|ecosystem collapse"
        r"|ecological destruction|canopy loss|severe degradation)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b\d+\.\d+\s*(?:in\s+|of\s+|units?\s+of\s+)?(?:forest destruction|habitat loss"
        r"|deforestation|ecocide|ecosystem collapse|ecological destruction)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:forest destruction|habitat loss|deforestation|ecocide|ecosystem collapse"
        r"|ecological destruction)\s+(?:of|by|at|reaching)\s+\d+\.\d+\b",
        re.IGNORECASE,
    ),
)

_NEGATED_VERDICT_PATTERN = re.compile(
    r"\b(?:not|never|neither|nor|cannot\s+be\s+considered|is\s+not|are\s+not|was\s+not"
    r"|were\s+not|does\s+not|did\s+not|rather\s+than|instead\s+of|whether\s+(?:it\s+is\s+)?)\s+"
    r"(?:fully\s+|partially\s+|deemed\s+|considered\s+)?"
    r"(?:consistent\s+with|confirm\w*|verif\w*|validat\w*|substantiat\w*)",
    re.IGNORECASE,
)

_VERDICT_CONSISTENT_ASSERTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:verdict|outcome|finding|result|screening|analysis|evidence)\s+is\s+consistent\s+"
        r"with\s+(?:the\s+)?(?:developer'?s?\s+)?claim\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bconsistent\s+with\s+(?:the\s+)?(?:developer'?s?\s+)?claim\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bconsistent_with_claim\b", re.IGNORECASE),
    re.compile(
        r"\b(?:confirms?|verifies|verified|validates?|validated|substantiates?)\s+"
        r"(?:the\s+)?(?:developer'?s?\s+)?claim\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:developer'?s?\s+)?claim\s+(?:is|was|has\s+been)\s+(?:fully\s+)?"
        r"(?:verified|confirmed|validated|substantiated)\b",
        re.IGNORECASE,
    ),
)

STRUCTURAL_NUMBER_CONTEXT = re.compile(
    r"(?:19|20)\d{2}|\bsection\b|\bfigure\b|\btable\b", re.IGNORECASE
)

CODE_SPAN = re.compile(r"`([^`]*)`")
PLAIN_NUMBER = re.compile(r"^\s*-?\d[\d,]*(?:\.\d+)?\s*$")


def mask_identifiers(text: str) -> str:
    """Blank out backticked identifiers so their digits are not read as claims.

    Evidence ids (``effect.point_estimate``), provenance fingerprints
    (``268506aa5d746a33``) and source URLs (``.../VCS/902``) are tokens that
    contain digit runs but assert nothing. Scanning them as narrated figures
    produces false violations. A backticked span holding nothing but a plain
    number is still scanned, so a figure cannot be smuggled past the check by
    wrapping it in backticks.
    """
    masked = CODE_SPAN.sub(lambda m: m.group(0) if PLAIN_NUMBER.match(m.group(1)) else " ", text)
    return URL_PATTERN.sub(" ", masked)


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

    scannable_numbers = mask_identifiers(text)
    for match in NUMBER_PATTERN.finditer(scannable_numbers):
        token = match.group(0)
        value = _parse_number(token)
        if value is None:
            continue

        window = scannable_numbers[max(0, match.start() - 30) : match.end() + 30]
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

    lowered = text.lower()

    # Scan for prohibited assertions with disclaimers masked out, so a caveat
    # that *denies* an allegation is not mistaken for making one.
    scannable = lowered
    for pattern in NEGATED_ASSERTION_PATTERNS:
        scannable = re.sub(pattern, " ", scannable)

    prohibited: list[str] = []
    for pattern, description in pol.prohibited_patterns:
        if re.search(pattern, scannable, re.IGNORECASE):
            prohibited.append(description)

    # Unit smuggling check: attaching carbon/credit units to an indicator effect value.
    indicator_values: list[float] = []
    for item in bundle.items:
        if (
            item.id == "effect.point_estimate"
            or item.id.startswith("effect.")
            or item.unit.lower() in {"ndvi", "evi", "nbr", "lai", "fpar", "kndvi", "index"}
        ):
            if isinstance(item.value, (int, float)) and not isinstance(item.value, bool):
                indicator_values.append(float(item.value))
            if item.confidence is not None:
                indicator_values.extend([item.confidence.lower, item.confidence.upper])

    if indicator_values or "carbon.estimated_tco2e" not in bundle:
        for sentence in re.split(r"(?<!\d)\.(?!\d)|[!?;\n]+", scannable_numbers.lower()):
            cleaned_sentence = _NEGATED_CARBON_UNIT_PATTERN.sub(" ", sentence)
            if not _CARBON_UNIT_PATTERN.search(cleaned_sentence):
                continue
            for num_match in NUMBER_PATTERN.finditer(cleaned_sentence):
                num_val = _parse_number(num_match.group(0))
                if num_val is None:
                    continue
                unit_window = cleaned_sentence[
                    max(0, num_match.start() - 35) : num_match.end() + 50
                ]
                if (
                    indicator_values
                    and _CARBON_UNIT_PATTERN.search(unit_window)
                    and _matches_any(num_val, indicator_values, pol.relative_tolerance)
                ):
                    prohibited.append(
                        "converts an indicator value into carbon/credit units without calibration"
                    )
                    break

    # Semantic polarity / context inversion check: positive indicator effect narrated
    # as ecological destruction.
    effect_item = bundle.get("effect.point_estimate")
    if (
        effect_item is not None
        and isinstance(effect_item.value, (int, float))
        and not isinstance(effect_item.value, bool)
        and float(effect_item.value) > 0
        and any(p.search(scannable) for p in _CONTEXT_INVERSION_PATTERNS)
    ):
        prohibited.append("inverts positive indicator effect into ecological destruction")

    # Verdict contradiction guard: narrative contradicts the bundle's screening verdict.
    verdict_label = (
        getattr(bundle.verdict, "label", bundle.verdict) if bundle.verdict is not None else None
    )
    if verdict_label in (VerdictLabel.INCONCLUSIVE, VerdictLabel.DIVERGENT_FROM_CLAIM):
        verdict_scannable = _NEGATED_VERDICT_PATTERN.sub(" ", scannable)
        if any(p.search(verdict_scannable) for p in _VERDICT_CONSISTENT_ASSERTION_PATTERNS):
            prohibited.append("contradicts the bundle's screening verdict")

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
