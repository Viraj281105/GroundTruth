"""Rule-based extraction of quantitative claims from project-document text.

No language model is involved: patterns are matched with regular expressions and
every claim carries the character span it was read from, so a reviewer can
check it against the source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class ClaimKind(StrEnum):
    """The quantities GroundTruth knows how to look for."""

    BASELINE = "baseline"
    CREDITS_ISSUED = "credits_issued"
    AREA_HECTARES = "area_hectares"
    REDUCTION_PERCENT = "reduction_percent"


@dataclass(frozen=True)
class Claim:
    """One quantitative statement found in a document."""

    kind: ClaimKind
    value: float
    unit: str
    doc_id: str
    start: int
    end: int
    quote: str
    """Verbatim text of the matched span (``text[start:end]``)."""

    def citation(self) -> str:
        """Human-readable source reference."""
        return f"{self.doc_id}[{self.start}:{self.end}]"


_NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_SCALE = r"(?:\s*(million|thousand|m|k)\b)?"
_SCALES = {"million": 1e6, "m": 1e6, "thousand": 1e3, "k": 1e3}
_TCO2 = r"(?:t\s?CO2\s?e?|tonnes?(?:\s+of)?\s+CO2\s?e?|tCO2e|MtCO2e)"

_PATTERNS: tuple[tuple[ClaimKind, str, re.Pattern[str]], ...] = (
    (
        ClaimKind.AREA_HECTARES,
        "ha",
        re.compile(_NUM + _SCALE + r"\s*(?:hectares?|ha)\b", re.IGNORECASE),
    ),
    (
        ClaimKind.REDUCTION_PERCENT,
        "percent",
        re.compile(
            r"(?:reduc\w*|avoid\w*|decreas\w*|lower\w*|cut)[^.\d]{0,60}?"
            + _NUM
            + r"\s*(?:%|percent)",
            re.IGNORECASE,
        ),
    ),
    (
        ClaimKind.REDUCTION_PERCENT,
        "percent",
        re.compile(_NUM + r"\s*(?:%|percent)\s*(?:reduction|decrease|decline|less)", re.IGNORECASE),
    ),
    (
        ClaimKind.CREDITS_ISSUED,
        "credits",
        re.compile(
            _NUM + _SCALE + r"\s*(?:\w+\s){0,2}?(?:credits|VCUs|VERs|offsets)\b"
            r"(?=[^.]{0,60}?(?:issued|generated|verified|awarded)|)",
            re.IGNORECASE,
        ),
    ),
    (
        ClaimKind.BASELINE,
        "tCO2e",
        re.compile(r"baseline[^.\d]{0,80}?" + _NUM + _SCALE + r"\s*" + _TCO2 + r"?", re.IGNORECASE),
    ),
)


def _to_float(number: str, scale: str | None) -> float:
    value = float(number.replace(",", ""))
    if scale:
        value *= _SCALES[scale.lower()]
    return value


def extract_claims(text: str, doc_id: str = "doc") -> list[Claim]:
    """Extract quantitative claims from ``text`` with source spans.

    Credit claims require an "issued/generated/verified" cue in the same
    sentence; a bare "5,000 credits" is ignored to avoid false positives.
    Overlapping matches of the same kind are de-duplicated.
    """
    claims: list[Claim] = []
    seen: set[tuple[ClaimKind, int, int]] = set()
    for kind, unit, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            if kind is ClaimKind.CREDITS_ISSUED:
                sentence_end = text.find(".", m.end())
                tail = text[m.start() : sentence_end if sentence_end != -1 else len(text)]
                head = text[max(0, m.start() - 80) : m.start()].rsplit(".", 1)[-1]
                if not re.search(r"issued|generated|verified|awarded", head + tail, re.I):
                    continue
            if kind is ClaimKind.BASELINE and not re.search(
                r"tco2|co2|tonnes", m.group(0), re.IGNORECASE
            ):
                continue
            groups = m.groups()
            has_scale = kind is not ClaimKind.REDUCTION_PERCENT and len(groups) > 1
            scale = groups[1] if has_scale else None
            value = _to_float(groups[0], scale)
            key = (kind, m.start(), m.end())
            if key in seen:
                continue
            seen.add(key)
            claims.append(
                Claim(
                    kind=kind,
                    value=value,
                    unit=unit,
                    doc_id=doc_id,
                    start=m.start(),
                    end=m.end(),
                    quote=text[m.start() : m.end()],
                )
            )
    claims.sort(key=lambda c: (c.start, c.kind.value))
    return claims
