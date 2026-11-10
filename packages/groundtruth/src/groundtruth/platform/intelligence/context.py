"""Retrieve the real, project-scoped context the intelligence route may reason over.

Everything here is read from records the platform already holds for one project (readiness,
evidence inventory, assessment, uploaded documents). Nothing is computed or invented: a missing
artifact becomes an entry in ``missing`` and never a default value. The result is plain data, so
the Groq service needs no database and tests can build a context directly.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi.encoders import jsonable_encoder

if TYPE_CHECKING:
    from groundtruth.platform.store.models import ProjectRow

_log = logging.getLogger("groundtruth.intelligence")

_MAX_TEXT = 320
_PROCESSED_DOC_STATES = frozenset(
    {"processed", "ready", "extracted", "text_extracted", "indexed", "parsed"}
)


@dataclass(frozen=True)
class ContextFact:
    """One statement taken verbatim from a platform record, with where it came from."""

    fact_id: str
    statement: str
    source: str  # platform record reference, e.g. "platform:readiness#cloud_cover"
    kind: str  # project | readiness | evidence_inventory | assessment | document

    def to_dict(self) -> dict[str, str]:
        return {
            "fact_id": self.fact_id,
            "statement": self.statement,
            "source": self.source,
            "kind": self.kind,
        }


@dataclass
class ProjectContext:
    project_id: str
    project_name: str
    data_mode: str
    facts: list[ContextFact] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    sufficient: bool = False
    """True only when observed evidence (or a processed document) exists for the project."""

    def fact_ids(self) -> set[str]:
        return {f.fact_id for f in self.facts}


def _clip(text: Any) -> str:
    s = " ".join(str(text).split())
    return s if len(s) <= _MAX_TEXT else s[: _MAX_TEXT - 3] + "..."


def list_project_documents(project_id: str) -> list[dict[str, Any]]:
    """Uploaded documents for ``project_id``, or ``[]`` when no database is configured."""
    engine = None
    try:
        from groundtruth.platform.config import get_settings
        from groundtruth.platform.projects import documents as project_docs
        from groundtruth.platform.store.database import create_db_engine, create_session_factory

        if not get_settings().database_url:
            return []
        engine = create_db_engine()
        with create_session_factory(engine)() as db:
            return [
                project_docs.document_dict(row)
                for row in project_docs.list_documents(db, project_id)
            ]
    except Exception:
        return []
    finally:
        if engine is not None:
            engine.dispose()


def _safe(label: str, missing: list[str], build: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return build()
    except Exception as exc:
        _log.warning("intelligence context: %s unavailable (%s)", label, type(exc).__name__)
        missing.append(f"{label} could not be read for this project.")
        return {}


def build_project_context(
    project: ProjectRow,
    access_level: Any,
    data_dir: Path,
    *,
    documents: list[dict[str, Any]] | None = None,
) -> ProjectContext:
    """Collect the project's own records, redacted to what ``access_level`` may see."""
    # imported here: the api package imports this module's service at import time
    from groundtruth.platform.projects import views
    from groundtruth.platform.projects.assessment import build_project_assessment
    from groundtruth.platform.projects.redaction import redact

    ctx = ProjectContext(
        project_id=project.id,
        project_name=project.name,
        data_mode=views.data_mode_of(project),
    )
    pid = project.id
    ctx.facts.append(
        ContextFact(
            "project",
            _clip(
                f"Project '{project.name}' in {project.country}; ecosystem {project.ecosystem}; "
                f"intervention {project.intervention}; treatment start year "
                f"{project.treatment_start_year}; data mode {ctx.data_mode}."
            ),
            f"platform:project#{pid}",
            "project",
        )
    )
    level = getattr(access_level, "value", access_level)

    # --- readiness ---
    readiness = _safe(
        "Readiness",
        ctx.missing,
        lambda: jsonable_encoder(
            redact(views.build_readiness(project, level, data_dir), access_level)
        ),
    )
    for c in readiness.get("criteria", []):
        ctx.facts.append(
            ContextFact(
                f"readiness.{c['id']}",
                _clip(
                    f"Readiness criterion '{c['name']}': status {c['status']}; observed "
                    f"{c.get('observed_value')}; required {c.get('required')}."
                ),
                f"platform:readiness#{c['id']}",
                "readiness",
            )
        )
        if c.get("status") != "met" and c.get("evidence_needed"):
            ctx.missing.append(_clip(f"{c['name']}: {c['evidence_needed']}"))

    # --- evidence inventory ---
    inv = _safe(
        "Evidence inventory",
        ctx.missing,
        lambda: jsonable_encoder(
            redact(views.build_inventory(project, level, data_dir), access_level)
        ),
    )
    if inv:
        if inv.get("status") == "available":
            ctx.sufficient = True
        else:
            ctx.missing.append(
                _clip(f"No observed evidence stored: {inv.get('reason') or 'none recorded'}.")
            )
        ctx.facts.append(
            ContextFact(
                "inventory.summary",
                _clip(
                    f"Evidence inventory status {inv.get('status')}; kinds "
                    f"{', '.join(inv.get('kinds') or []) or 'none'}; climate series "
                    f"{inv.get('climate_status')}."
                ),
                f"platform:evidence-inventory#{pid}",
                "evidence_inventory",
            )
        )
        for ind in inv.get("indicators", []):
            if ind.get("status") != "available":
                continue
            years = ind.get("years") or []
            span = f"{min(years)} to {max(years)}" if years else "no years"
            ctx.facts.append(
                ContextFact(
                    f"inventory.{ind['indicator']}",
                    _clip(
                        f"Indicator {ind['indicator']}: {ind.get('n_records')} annual records, "
                        f"{span}; sensors {', '.join(ind.get('sensors') or []) or 'unrecorded'}; "
                        f"source {ind.get('source')}."
                    ),
                    f"platform:evidence-inventory#{ind['indicator']}",
                    "evidence_inventory",
                )
            )
        if inv.get("climate_status") != "available" and inv.get("climate_reason"):
            ctx.missing.append(_clip(f"Climate series: {inv['climate_reason']}"))

    # --- assessment ---
    asm = _safe(
        "Assessment",
        ctx.missing,
        lambda: jsonable_encoder(
            redact(
                views.build_assessment(
                    build_project_assessment(project, data_dir=data_dir), project, level
                ),
                access_level,
            )
        ),
    )
    if asm:
        ctx.facts.append(
            ContextFact(
                "assessment.level",
                _clip(
                    f"Assessment level {asm.get('level')} ({asm.get('level_name')}); evidence "
                    f"confidence {asm.get('evidence_confidence')}."
                ),
                f"platform:assessment#{pid}",
                "assessment",
            )
        )
        for d in asm.get("dimensions", []):
            ctx.facts.append(
                ContextFact(
                    f"assessment.{d['id']}",
                    _clip(f"{d['title']}: status {d['status']}. {d.get('finding', '')}"),
                    f"platform:assessment#{d['id']}",
                    "assessment",
                )
            )
        att = asm.get("attribution") or {}
        if att:
            ctx.facts.append(
                ContextFact(
                    "assessment.attribution",
                    _clip(f"Attribution verdict {att.get('verdict')}. {att.get('limitation', '')}"),
                    "platform:assessment#attribution",
                    "assessment",
                )
            )

    # --- documents (optional integration) ---
    docs = documents if documents is not None else list_project_documents(pid)
    if not docs:
        ctx.missing.append("No project documents have been uploaded.")
    for i, d in enumerate(docs):
        status = str(d.get("status") or "unknown")
        doc_id = str(d.get("id") or i)
        ctx.facts.append(
            ContextFact(
                f"document.{doc_id}",
                _clip(
                    f"Document '{d.get('filename') or doc_id}' ({d.get('document_type') or d.get('kind') or 'type unrecorded'}), "
                    f"status {status}. Its contents are not available to the model."
                ),
                f"platform:document#{doc_id}",
                "document",
            )
        )
        if status.lower() in _PROCESSED_DOC_STATES:
            ctx.sufficient = True
    return ctx
