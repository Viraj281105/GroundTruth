"""Rule-based, multi-claim reading of project text (no language model, no I/O).

Where ``extract_claims`` reads the few quantities GroundTruth can compare with a case figure,
this module reads *every* statement a reviewer would want to see: area, survival rate,
vegetation-index change, carbon, and conclusions that go beyond what remote sensing or the
supplied evidence can show (absolute language, biodiversity or ecosystem recovery, an index
presented as carbon, an effect attributed to the project without a counterfactual).

Honesty rules, binding on this module:

* It never produces a confidence score, a verification verdict, or a comparison figure. A
  status says what *kind* of statement it is and whether any evidence the platform can use has
  been supplied; it is not a judgement about any person or organisation (R2).
* Every statement keeps its original text and character span, so it can be checked against
  the source. Sentences that match no pattern are returned too, never silently dropped.
* An index (NDVI/EVI) is never turned into carbon (R1) and an observed change is never read as
  a project effect (R3); statements that do either are flagged with the reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class StatementKind(StrEnum):
    AREA_HECTARES = "area_hectares"
    SURVIVAL_RATE = "survival_rate"
    VEGETATION_INDEX_CHANGE = "vegetation_index_change"
    CARBON_TCO2E = "carbon_tco2e"
    BIODIVERSITY_RECOVERY = "biodiversity_recovery"
    ECOSYSTEM_RECOVERY = "ecosystem_recovery"
    INDEX_TO_CARBON = "index_to_carbon_conflation"
    CAUSAL_ATTRIBUTION = "causal_attribution"
    UNSUPPORTED_CONCLUSION = "unsupported_conclusion"


class StatementStatus(StrEnum):
    EXTRACTED = "extracted"
    """Read from the text; a platform check exists but no evidence has been supplied here."""
    UNSUPPORTED = "unsupported_by_available_evidence"
    """No evidence the platform can ingest and use could substantiate it as written."""
    OVERCLAIM = "overclaim"
    """Absolute or unqualified wording that no remote-sensing evidence could establish."""


@dataclass(frozen=True)
class ClaimStatement:
    statement_id: str
    kind: StatementKind
    status: StatementStatus
    text: str
    """Verbatim claim text, ``source[start:end]``."""
    start: int
    end: int
    value: float | None
    unit: str | None
    period: str | None
    reason: str
    """Plain-language: why this cannot be substantiated from what is available."""
    evidence_link: str | None
    evidence_gap: str | None
    doc_id: str = "doc"


@dataclass(frozen=True)
class UnrecognisedSentence:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class TextAnalysis:
    statements: list[ClaimStatement] = field(default_factory=list)
    unrecognised: list[UnrecognisedSentence] = field(default_factory=list)


_NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d*\.\d+|\d+)"
_SCALE = r"(?:\s*(million|thousand|m|k)\b)?"
_SCALES = {"million": 1e6, "m": 1e6, "thousand": 1e3, "k": 1e3}
_INDEX = r"(NDVI|EVI|SAVI|NBR|vegetation\s+index|greenness)"

_AREA = re.compile(_NUM + _SCALE + r"\s*(?:hectares?|ha)\b", re.I)
_SURVIVAL = re.compile(_NUM + r"\s*(?:%|percent)", re.I)
_SURVIVAL_CUE = re.compile(r"surviv|alive|establish\w*\s+rate|mortality", re.I)
_INDEX_DELTA = re.compile(
    _INDEX
    + r"\b[^.\d]{0,40}?\b(increased|decreased|rose|fell|improved|declined|grew|dropped|gained"
    r"|lost)\b[^.\d]{0,15}?" + r"([+-]?\d*\.\d+|\d+)\s*(%|percent)?",
    re.I,
)
_INDEX_CHANGE_OF = re.compile(
    _INDEX + r"\b[^.\d]{0,30}?(?:change|difference|delta|gain)\s+of\s+([+-]?\d*\.\d+|\d+)", re.I
)
_NEGATIVE_VERBS = {"decreased", "fell", "declined", "dropped", "lost"}
_CARBON = re.compile(
    _NUM + _SCALE + r"\s*(?:t\s?CO2\s?e?|tonnes?(?:\s+of)?\s+CO2\s?e?|MtCO2e|tCO2e)", re.I
)
_PERIOD = re.compile(
    r"(?:since\s+\d{4}"
    r"|from\s+\d{4}\s+(?:to|through|until)\s+\d{4}"
    r"|between\s+\d{4}\s+and\s+\d{4}"
    r"|(?:after|over|within|during|in\s+the\s+(?:last|past))\s+(?:the\s+(?:first|last)\s+)?"
    r"\d+(?:\.\d+)?\s+(?:years?|months?)"
    r"|in\s+\d{4})",
    re.I,
)
_OVERCLAIM_VERB = re.compile(r"\b(proves?|proven|demonstrates?|confirms?|guarantee[sd]?)\b", re.I)
# "Permanent" is absolute wording about an outcome, except in the forestry term for a re-measured
# field plot ("permanent sample plots", "permanent transects"), which describes a monitoring method.
_PERMANENT = (
    r"permanent(?:ly)?(?!\s+(?:(?:sample|sampling|monitoring|inventory|vegetation|survey)\s+)?"
    r"(?:plots?|transects?|quadrats?)\b)"
)
_OVERCLAIM_WORD = re.compile(
    r"\b(fully\s+(?:recovered|restored|regenerated)|full\s+recovery|completely\s+(?:recovered|"
    r"restored)|guarantee[sd]?|" + _PERMANENT + r"|zero\s+(?:risk|leakage)|no\s+risk|"
    r"100\s*%\s+(?:recovered|restored|success)|irreversibl\w+)\b",
    re.I,
)
_BIODIVERSITY = re.compile(r"\b(biodiversity|species\s+richness|wildlife|fauna|flora)\b", re.I)
_ECOSYSTEM = re.compile(r"\becosystem\w*\b[^.]{0,40}\b(recover\w*|restor\w*|health\w*)", re.I)
_CAUSAL = re.compile(
    r"\b(attributable\s+to|caused\s+by|due\s+to|result\s+of|thanks\s+to)\b[^.]{0,50}"
    r"\b(project|intervention|restoration|programme|program)\b",
    re.I,
)
_RECOVERY = re.compile(r"\b(recover\w*|restor\w*|improv\w*|regenerat\w*)\b", re.I)
# A stated change in a biodiversity measure ("species richness increased by 20 percent") is a
# claim about biodiversity even when no recovery verb is used.
_BIODIVERSITY_CHANGE = re.compile(
    r"\b(increas\w*|rose|risen|rising|grew|grown|doubl\w*|tripl\w*|gain\w*|return\w*|"
    r"declin\w*|decreas\w*|higher|lower)\b",
    re.I,
)
_CARBON_WORD = re.compile(r"\b(carbon|tCO2e?|CO2|sequester\w*|credits?)\b", re.I)

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")

_NO_EVIDENCE = "No evidence has been attached to this analysis."
_INDEX_REASON = (
    "A change in a vegetation index describes greenness, not a project effect or a carbon "
    "amount. It can be compared with observed index series for the area once observations are "
    "ingested; no observations are attached to this analysis."
)


def _sentences(text: str) -> list[tuple[int, int]]:
    """Sentence spans ``(start, end)`` with trailing terminal punctuation excluded."""
    spans: list[tuple[int, int]] = []
    pos = 0
    boundaries = [(m.start(), m.end()) for m in _SENTENCE_END.finditer(text)]
    boundaries.append((len(text), len(text)))
    for b_start, b_end in boundaries:
        seg = text[pos:b_start]
        stripped = seg.strip()
        if stripped:
            s = pos + (len(seg) - len(seg.lstrip()))
            e = s + len(stripped)
            while e > s and text[e - 1] in ".!?":
                e -= 1
            if e > s:
                spans.append((s, e))
        pos = b_end
    return spans


def _float(number: str, scale: str | None = None) -> float:
    v = float(number.replace(",", ""))
    return v * _SCALES[scale.lower()] if scale else v


def _period(sentence: str) -> str | None:
    m = _PERIOD.search(sentence)
    return m.group(0) if m else None


def analyze_text(text: str, doc_id: str = "doc") -> TextAnalysis:
    """Read every recognisable statement in ``text`` with spans; list what was not recognised."""
    statements: list[ClaimStatement] = []
    unrecognised: list[UnrecognisedSentence] = []

    def add(
        kind: StatementKind,
        status: StatementStatus,
        start: int,
        end: int,
        value: float | None,
        unit: str | None,
        period: str | None,
        reason: str,
        gap: str,
    ) -> None:
        statements.append(
            ClaimStatement(
                statement_id=f"S-{len(statements) + 1:02d}",
                kind=kind,
                status=status,
                text=text[start:end],
                start=start,
                end=end,
                value=value,
                unit=unit,
                period=period,
                reason=reason,
                evidence_link=None,
                evidence_gap=gap,
                doc_id=doc_id,
            )
        )

    for s_start, s_end in _sentences(text):
        sent = text[s_start:s_end]
        before = len(statements)
        period = _period(sent)

        # Where a concluding clause begins ("... and proves X"), numeric claims stop before it.
        verb = _OVERCLAIM_VERB.search(sent)
        word = _OVERCLAIM_WORD.search(sent)
        num_end = s_end
        if verb:
            head = text[s_start : s_start + verb.start()]
            cut = re.sub(r"[\s,;]*(?:and|but|which|that)?[\s,;]*$", "", head, flags=re.I)
            if cut.strip():
                num_end = s_start + len(cut)
        num_text = text[s_start:num_end]

        has_index = re.search(_INDEX, sent, re.I) is not None
        has_carbon_word = _CARBON_WORD.search(sent) is not None
        carbon_match = _CARBON.search(num_text)

        # --- area ---------------------------------------------------------------------
        if (m := _AREA.search(num_text)) is not None:
            add(
                StatementKind.AREA_HECTARES,
                StatementStatus.EXTRACTED,
                s_start,
                num_end,
                _float(m.group(1), m.group(2)),
                "ha",
                period,
                "Read from the text only. The stated area can be checked against the project "
                "boundary, but no boundary or case figure is attached to this analysis.",
                _NO_EVIDENCE + " Add the project boundary to check the stated area.",
            )

        # --- vegetation index change ----------------------------------------------------
        idx = _INDEX_DELTA.search(num_text)
        idx2 = None if idx else _INDEX_CHANGE_OF.search(num_text)
        if idx is not None:
            val = _float(idx.group(3).lstrip("+-"))
            if idx.group(2).lower() in _NEGATIVE_VERBS or idx.group(3).startswith("-"):
                val = -val
            add(
                StatementKind.VEGETATION_INDEX_CHANGE,
                StatementStatus.EXTRACTED,
                s_start,
                num_end,
                val,
                "percent_of_index" if idx.group(4) else f"{idx.group(1).lower()}_units",
                period,
                _INDEX_REASON,
                _NO_EVIDENCE + " Ingest observations for the area and period to compare.",
            )
        elif idx2 is not None:
            add(
                StatementKind.VEGETATION_INDEX_CHANGE,
                StatementStatus.EXTRACTED,
                s_start,
                num_end,
                float(idx2.group(2)),
                f"{idx2.group(1).lower()}_units",
                period,
                _INDEX_REASON,
                _NO_EVIDENCE + " Ingest observations for the area and period to compare.",
            )

        # --- survival rate --------------------------------------------------------------
        if _SURVIVAL_CUE.search(num_text) and (m := _SURVIVAL.search(num_text)) is not None:
            add(
                StatementKind.SURVIVAL_RATE,
                StatementStatus.UNSUPPORTED,
                s_start,
                num_end,
                _float(m.group(1)),
                "percent",
                period,
                "Survival is counted on the ground (plot or census surveys). Satellite "
                "observations cannot confirm how many planted seedlings are alive.",
                "No field survival survey is attached. Upload the survey report or plot data "
                "that the figure is based on.",
            )

        # --- carbon ---------------------------------------------------------------------
        if carbon_match is not None:
            conflated = has_index
            add(
                StatementKind.CARBON_TCO2E,
                StatementStatus.OVERCLAIM if conflated else StatementStatus.UNSUPPORTED,
                s_start,
                num_end,
                _float(carbon_match.group(1), carbon_match.group(2)),
                "tCO2e",
                period,
                (
                    "This sentence presents a vegetation index and a carbon amount together. An "
                    "index such as NDVI cannot be converted into tCO2e; carbon needs field "
                    "biomass measurements or an accredited registry record."
                    if conflated
                    else "A carbon amount comes from field biomass measurement and an accredited "
                    "method, or a registry record. Satellite greenness cannot establish it."
                ),
                "No biomass inventory or registry record is attached. Upload the monitoring "
                "report or registry issuance that the figure is based on.",
            )
        elif has_index and has_carbon_word:
            add(
                StatementKind.INDEX_TO_CARBON,
                StatementStatus.OVERCLAIM,
                s_start,
                s_end,
                None,
                None,
                period,
                "A vegetation index is being linked to carbon. NDVI/EVI measure greenness and "
                "cannot be converted to carbon stock or tCO2e.",
                "Carbon needs field biomass measurements or an accredited registry record.",
            )

        # --- conclusions beyond the evidence --------------------------------------------
        c_start = s_start + verb.start() if verb else s_start
        clause = text[c_start:s_end]
        if verb or word:
            if _BIODIVERSITY.search(clause):
                add(
                    StatementKind.BIODIVERSITY_RECOVERY,
                    StatementStatus.OVERCLAIM,
                    c_start,
                    s_end,
                    None,
                    None,
                    period,
                    "Absolute wording ('proves', 'fully recovered') about biodiversity. Species "
                    "recovery needs repeated field surveys against a baseline; satellite "
                    "greenness cannot show it, and no survey is attached.",
                    "No biodiversity survey or monitoring data is attached.",
                )
            elif _ECOSYSTEM.search(clause):
                add(
                    StatementKind.ECOSYSTEM_RECOVERY,
                    StatementStatus.OVERCLAIM,
                    c_start,
                    s_end,
                    None,
                    None,
                    period,
                    "Absolute wording about whole-ecosystem recovery. Remote sensing shows "
                    "vegetation change only and cannot establish full ecosystem recovery.",
                    "No ecological survey data is attached.",
                )
            elif not any(s.kind == StatementKind.INDEX_TO_CARBON for s in statements[before:]):
                add(
                    StatementKind.UNSUPPORTED_CONCLUSION,
                    StatementStatus.OVERCLAIM,
                    c_start,
                    s_end,
                    None,
                    None,
                    period,
                    "Absolute or guaranteed wording. Observations can describe what was "
                    "measured; they cannot prove or guarantee an outcome.",
                    _NO_EVIDENCE,
                )
        elif _BIODIVERSITY.search(sent) and (
            _RECOVERY.search(sent) or _BIODIVERSITY_CHANGE.search(sent)
        ):
            add(
                StatementKind.BIODIVERSITY_RECOVERY,
                StatementStatus.UNSUPPORTED,
                s_start,
                s_end,
                None,
                None,
                period,
                "Biodiversity change needs repeated field surveys against a baseline. "
                "Satellite greenness cannot show it.",
                "No biodiversity survey or monitoring data is attached.",
            )
        elif _ECOSYSTEM.search(sent):
            add(
                StatementKind.ECOSYSTEM_RECOVERY,
                StatementStatus.UNSUPPORTED,
                s_start,
                s_end,
                None,
                None,
                period,
                "Ecosystem recovery needs ecological survey evidence beyond vegetation indices.",
                "No ecological survey data is attached.",
            )

        if _CAUSAL.search(sent):
            add(
                StatementKind.CAUSAL_ATTRIBUTION,
                StatementStatus.UNSUPPORTED,
                s_start,
                s_end,
                None,
                None,
                period,
                "Attributing a change to the project needs a counterfactual (what would have "
                "happened without it) and placebo tests. An observed change alone is not an "
                "effect of the project.",
                "No counterfactual analysis is attached.",
            )

        if len(statements) == before:
            unrecognised.append(UnrecognisedSentence(s_start, s_end, sent))

    return TextAnalysis(statements=statements, unrecognised=unrecognised)
