"""Groq-backed project intelligence: narration of retrieved platform context, nothing else.

Guardrails (AGENTS.md R2, R4, R6):

* The model sees only the project's own retrieved records (``context.ProjectContext``). It
  computes nothing: every number in an accepted inference must already appear in those records.
* ``retrieved_facts`` are copied from platform records by the server, never from model text.
  ``inferences`` are the model's, labelled as such, and are dropped when they carry numbers that
  are not in the context or any prohibited assertion (fraud, legal conclusions, ...).
* No key -> ``status: "unavailable"``. Provider error or timeout -> ``status: "error"``. There
  is no static or simulated fallback answer, and ``latency_ms`` is measured around the real
  provider call only (``None`` when no call was made).
* External literature appears only from the small static list below, always flagged
  ``kind="published_literature"`` and never attached to a project fact.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import httpx

from groundtruth.contracts.grounding import (
    NEGATED_ASSERTION_PATTERNS,
    NUMBER_PATTERN,
    PROHIBITED_PATTERNS,
    GroundingPolicy,
    mask_identifiers,
)
from groundtruth.platform.config import get_settings
from groundtruth.platform.intelligence.context import ProjectContext

_log = logging.getLogger("groundtruth.intelligence")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
REQUEST_TIMEOUT_S = 30.0


class IntelligenceMode(StrEnum):
    """Supported intelligence research modes."""

    ENVIRONMENTAL_RESEARCH = "environmental_research"
    POLICY_NEWS_ANALYSIS = "policy_news_analysis"
    PROPOSAL_ANALYSIS = "proposal_analysis"
    CSR_DUE_DILIGENCE = "csr_due_diligence"
    CONTRADICTION_DETECTION = "contradiction_detection"
    STAKEHOLDER_REPORTS = "stakeholder_reports"


GUARDRAIL_NOTICE = (
    "The language model only restates and cautiously interprets this project's own platform "
    "records. It computes nothing: figures not present in those records are removed. Model "
    "inferences are labelled as such and are not verification findings."
)

# Published methodological literature (not project facts). Kept deliberately small, with
# identifiers that can be checked; no numbers are quoted from them.
PUBLISHED_LITERATURE: tuple[dict[str, str], ...] = (
    {
        "kind": "published_literature",
        "title": "Money for nothing? A call for empirical evaluation of biodiversity "
        "conservation investments",
        "authors": "Ferraro, P. J. and Pattanayak, S. K.",
        "venue": "PLoS Biology",
        "year": "2006",
        "doi": "10.1371/journal.pbio.0040105",
        "relevance": "General background on why counterfactual comparison is needed to "
        "attribute conservation outcomes to an intervention.",
    },
    {
        "kind": "published_literature",
        "title": "Overstated carbon emission reductions from voluntary REDD+ projects in the "
        "Brazilian Amazon",
        "authors": "West, T. A. P. et al.",
        "venue": "Proceedings of the National Academy of Sciences",
        "year": "2020",
        "doi": "10.1073/pnas.2004334117",
        "relevance": "General background on baseline choice and additionality in REDD+ "
        "evaluation. Not about this project.",
    },
)
_LITERATURE_TRIGGER = re.compile(
    r"additional|counterfactual|baseline|over-?credit|attribution|causal|leakage", re.IGNORECASE
)


def literature_for(query: str) -> list[dict[str, str]]:
    """The static literature list, only when the question is about attribution methodology."""
    return [dict(x) for x in PUBLISHED_LITERATURE] if _LITERATURE_TRIGGER.search(query) else []


@dataclass(frozen=True)
class _Ungrounded:
    numbers: tuple[str, ...]
    prohibited: tuple[str, ...]


def _parse(token: str) -> float | None:
    try:
        return float(token.replace(",", ""))
    except ValueError:
        return None


def _numbers_in(text: str) -> list[float]:
    out = []
    for m in NUMBER_PATTERN.finditer(mask_identifiers(text)):
        v = _parse(m.group(0))
        if v is not None:
            out.append(v)
    return out


def _close(value: float, candidates: list[float], tol: float) -> bool:
    for c in candidates:
        for scaled in (c, c * 100.0, c * 0.01):
            if abs(scaled - value) <= tol * max(abs(scaled), abs(value), 1e-9):
                return True
    return False


def check_text(text: str, allowed: list[float]) -> _Ungrounded:
    """Numbers in ``text`` absent from ``allowed`` and any prohibited assertions."""
    pol = GroundingPolicy()
    bad: list[str] = []
    scan = mask_identifiers(text)
    for m in NUMBER_PATTERN.finditer(scan):
        token = m.group(0).rstrip(",")
        value = _parse(token)
        if value is None:
            continue
        if float(value).is_integer() and (
            (1970 <= value <= 2100 and len(token) == 4) or 0 <= value <= 10
        ):
            continue
        if not _close(value, allowed, pol.relative_tolerance):
            bad.append(token)
    lowered = text.lower()
    for pattern in NEGATED_ASSERTION_PATTERNS:
        lowered = re.sub(pattern, " ", lowered)
    prohibited = [
        desc for pat, desc in PROHIBITED_PATTERNS if re.search(pat, lowered, re.IGNORECASE)
    ]
    return _Ungrounded(tuple(dict.fromkeys(bad)), tuple(dict.fromkeys(prohibited)))


SYSTEM_PROMPT = (
    "You are the narration layer of GroundTruth, an ecological verification screening tool. "
    "You receive FACTS retrieved from one project's own platform records and a user QUESTION. "
    "Rules: (1) Use only the FACTS. Never use outside knowledge about any place, project, "
    "registry or dataset, and never invent sources or citations. (2) Compute nothing and "
    "convert nothing: do not add, average, extrapolate or convert units; a vegetation index is "
    "never carbon. Any number you write must appear in the FACTS. (3) Never allege or imply "
    "fraud, crime or intent; a divergence only means the project warrants accredited review. "
    "Observed change is not causal effect. (4) If the QUESTION concerns another project, "
    "place, or anything the FACTS do not cover, say so under `unanswerable` and do not "
    'answer it. (5) Reply with JSON only: {"answer": string, "cited_fact_ids": [fact_id], '
    '"inferences": [{"statement": string, "based_on": [fact_id]}], '
    '"unanswerable": [string]}. `answer` is a short plain restatement of what the FACTS say '
    "that bears on the question. `inferences` are cautious interpretations, each citing the "
    "fact_ids it rests on."
)


class GroqIntelligenceService:
    """Calls Groq's OpenAI-compatible chat endpoint with the retrieved project context."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = GROQ_BASE_URL,
        model: str | None = None,
        temperature: float = 0.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._model = model
        self.temperature = temperature
        self._client = client

    # configuration is read at call time so a changed environment is honoured
    @property
    def api_key(self) -> str | None:
        if self._api_key:
            return self._api_key
        secret = getattr(get_settings(), "groq_api_key", None)
        value = secret.get_secret_value() if secret is not None else None
        return value or None

    @property
    def model(self) -> str:
        configured = getattr(get_settings(), "groq_model", None)
        return self._model or (str(configured) if configured else "llama-3.3-70b-versatile")

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def status(self) -> dict[str, Any]:
        """Configuration state only; never the key."""
        ok = self.configured
        return {
            "status": "configured" if ok else "unavailable",
            "configured": ok,
            "reason": None if ok else "GROQ_API_KEY not configured",
            "model": self.model,
            "provider": "groq",
        }

    # ------------------------------------------------------------------ query
    def execute_intelligence_query(
        self,
        query: str,
        context: ProjectContext,
        mode: IntelligenceMode = IntelligenceMode.CSR_DUE_DILIGENCE,
        stakeholder_role: str | None = None,
    ) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        base: dict[str, Any] = {
            "project_id": context.project_id,
            "query": query,
            "mode": str(mode),
            "stakeholder_role": stakeholder_role,
            "model": self.model,
            "status": "ok",
            "reason": None,
            "latency_ms": None,
            "generated_at": generated_at,
            "data_mode": context.data_mode,
            "answer": None,
            "retrieved_facts": [f.to_dict() for f in context.facts],
            "inferences": [],
            "unsupported_conclusions": [],
            "missing_context": list(context.missing),
            "published_literature": literature_for(query),
            "guardrail": {"applied": True, "notice": GUARDRAIL_NOTICE, "dropped": []},
        }
        if not context.sufficient:
            base["status"] = "insufficient_context"
            base["reason"] = "insufficient project context"
            base["answer"] = (
                "Insufficient project context: the platform holds no observed evidence or "
                "processed documents for this project, so no analysis can be given. "
                "See missing_context for what is needed."
            )
            base["unsupported_conclusions"] = [
                "Any conclusion about vegetation change, carbon, additionality or claim "
                "accuracy is unsupported until evidence is added."
            ]
            return base
        key = self.api_key
        if not key:
            base["status"] = "unavailable"
            base["reason"] = "GROQ_API_KEY not configured"
            return base

        user = json.dumps(
            {
                "QUESTION": query,
                "MODE": str(mode),
                "STAKEHOLDER_LENS": stakeholder_role,
                "FACTS": [{"fact_id": f.fact_id, "statement": f.statement} for f in context.facts],
                "KNOWN_MISSING_CONTEXT": context.missing,
            },
            ensure_ascii=False,
        )
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
        }
        client = self._client or httpx.Client(timeout=REQUEST_TIMEOUT_S)
        started = time.perf_counter()
        try:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json=payload,
            )
            base["latency_ms"] = round((time.perf_counter() - started) * 1000.0, 1)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError("model output is not a JSON object")
        except httpx.TimeoutException:
            base["latency_ms"] = round((time.perf_counter() - started) * 1000.0, 1)
            return self._error(base, "The language model provider timed out.")
        except httpx.HTTPStatusError as exc:
            _log.warning("groq http status %s", exc.response.status_code)
            return self._error(base, "The language model provider returned an error.")
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
            if base["latency_ms"] is None:
                base["latency_ms"] = round((time.perf_counter() - started) * 1000.0, 1)
            _log.warning("groq call failed: %s", type(exc).__name__)
            return self._error(
                base, "The language model provider failed or returned unusable output."
            )
        finally:
            if self._client is None:
                client.close()

        self._apply_guardrails(base, parsed, context)
        return base

    @staticmethod
    def _error(base: dict[str, Any], message: str) -> dict[str, Any]:
        base["status"] = "error"
        base["reason"] = message
        return base

    @staticmethod
    def _apply_guardrails(
        base: dict[str, Any], parsed: dict[str, Any], context: ProjectContext
    ) -> None:
        allowed: list[float] = []
        for f in context.facts:
            allowed.extend(_numbers_in(f.statement))
        dropped: list[dict[str, Any]] = base["guardrail"]["dropped"]
        valid_ids = context.fact_ids()

        answer = parsed.get("answer")
        if isinstance(answer, str) and answer.strip():
            res = check_text(answer, allowed)
            if res.numbers or res.prohibited:
                dropped.append(
                    {
                        "part": "answer",
                        "reason": "ungrounded_numbers" if res.numbers else "prohibited_assertion",
                        "ungrounded_numbers": list(res.numbers),
                        "prohibited": list(res.prohibited),
                    }
                )
                base["answer"] = (
                    "The model answer was withheld because it contained figures or assertions "
                    "not supported by the retrieved project records. See retrieved_facts."
                )
            else:
                base["answer"] = answer.strip()
        else:
            base["answer"] = None

        for raw in parsed.get("inferences") or []:
            if not isinstance(raw, dict) or not isinstance(raw.get("statement"), str):
                continue
            stmt = raw["statement"].strip()
            based = [b for b in (raw.get("based_on") or []) if isinstance(b, str)]
            res = check_text(stmt, allowed)
            if res.numbers or res.prohibited or not any(b in valid_ids for b in based):
                dropped.append(
                    {
                        "part": "inference",
                        "reason": (
                            "ungrounded_numbers"
                            if res.numbers
                            else "prohibited_assertion"
                            if res.prohibited
                            else "no_supporting_fact"
                        ),
                        "ungrounded_numbers": list(res.numbers),
                        "prohibited": list(res.prohibited),
                    }
                )
                continue
            base["inferences"].append(
                {
                    "statement": stmt,
                    "label": "model_inference",
                    "based_on": [b for b in based if b in valid_ids],
                }
            )

        for item in parsed.get("unanswerable") or []:
            if isinstance(item, str) and item.strip():
                base["unsupported_conclusions"].append(item.strip())

        cited = {c for c in (parsed.get("cited_fact_ids") or []) if isinstance(c, str)}
        for f in base["retrieved_facts"]:
            f["cited_by_model"] = f["fact_id"] in cited


_GLOBAL_INTELLIGENCE_SERVICE = GroqIntelligenceService()


def get_global_intelligence_service() -> GroqIntelligenceService:
    """Return the shared Groq intelligence service."""
    return _GLOBAL_INTELLIGENCE_SERVICE
