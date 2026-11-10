"""The OpenAPI schema the API serves, and the snapshot the frontend generates types from.

**Owner: Bhumi.**

The frontend never hand-writes a backend shape (C5). Its TypeScript types are generated
from this schema, committed as ``apps/web/src/lib/generated/openapi.json``. The served
``/openapi.json`` and that snapshot are built by the same function, so they cannot differ;
a test checks they are equal, and CI fails when the snapshot is stale.

One adjustment is made to what FastAPI generates. Pydantic marks a field that has a
default as "not required", but FastAPI always *sends* every field of a response model.
Left alone, the generated types would say ``qualifiers`` or ``engine_capabilities`` might
be missing when they never are, and push needless ``undefined`` checks into the UI. So
every property of a schema used **only in responses** is marked required. Two kinds of
schema are left exactly as FastAPI wrote them:

* schemas reachable from a **request** body or parameter, where a default really does
  mean "you may leave this out";
* FastAPI's own validation-error schemas, whose members (``input``, ``ctx``) really are
  sometimes absent.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI

FRAMEWORK_SCHEMAS = frozenset({"HTTPValidationError", "ValidationError"})
"""Written by FastAPI, not by our models. Their optional members are genuinely optional."""

_REF_PREFIX = "#/components/schemas/"


def _refs(node: Any) -> set[str]:
    """Every component schema name referenced anywhere inside ``node``."""
    found: set[str] = set()
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith(_REF_PREFIX):
            found.add(ref[len(_REF_PREFIX) :])
        for value in node.values():
            found |= _refs(value)
    elif isinstance(node, list):
        for value in node:
            found |= _refs(value)
    return found


def _closure(names: set[str], schemas: dict[str, Any]) -> set[str]:
    """``names`` plus every schema they reference, transitively."""
    seen: set[str] = set()
    pending = list(names)
    while pending:
        name = pending.pop()
        if name in seen or name not in schemas:
            continue
        seen.add(name)
        pending.extend(_refs(schemas[name]) - seen)
    return seen


def request_schema_names(spec: dict[str, Any]) -> set[str]:
    """Schemas a client sends: reachable from any request body or parameter."""
    roots: set[str] = set()
    for operations in spec.get("paths", {}).values():
        for operation in operations.values():
            roots |= _refs(operation.get("requestBody", {}))
            roots |= _refs(operation.get("parameters", []))
    return _closure(roots, spec.get("components", {}).get("schemas", {}))


def require_response_fields(spec: dict[str, Any]) -> dict[str, Any]:
    """Mark every property of a response-only schema as required. Returns a new dict."""
    spec = copy.deepcopy(spec)
    schemas: dict[str, Any] = spec.get("components", {}).get("schemas", {})
    leave_alone = request_schema_names(spec) | FRAMEWORK_SCHEMAS
    for name, schema in schemas.items():
        properties = schema.get("properties")
        if name in leave_alone or not properties:
            continue
        schema["required"] = list(properties)
    return spec


VALIDATION_ENVELOPE_PROPERTIES: dict[str, dict[str, Any]] = {
    "code": {"type": "string", "title": "Code", "description": "Always `validation_error`."},
    "message": {"type": "string", "title": "Message", "description": "A one-line summary."},
    "fields": {
        "type": "array",
        "items": {"type": "string"},
        "title": "Fields",
        "description": "The dotted name of every offending field, e.g. `body.area_ha`.",
    },
    "is_refusal": {"type": "boolean", "title": "Is Refusal", "description": "Always false."},
    "request_id": {
        "type": "string",
        "title": "Request Id",
        "description": "Identifier of this request, also in the `X-Request-ID` header.",
    },
}
"""The only members the error envelope adds to FastAPI's ``HTTPValidationError``. All optional."""


def document_error_envelope(spec: dict[str, Any]) -> dict[str, Any]:
    """Describe what the error envelope adds to FastAPI's validation error. Returns a new dict.

    FastAPI writes ``HTTPValidationError`` itself, so the members the envelope adds at run time
    are declared here, from :data:`VALIDATION_ENVELOPE_PROPERTIES`. They stay optional: the
    schema belongs to the framework, and a client must not rely on them being present on an
    error that never reached the API. Nothing FastAPI wrote is changed.
    """
    spec = copy.deepcopy(spec)
    schema = spec.get("components", {}).get("schemas", {}).get("HTTPValidationError")
    if schema is not None:
        schema.setdefault("properties", {}).update(copy.deepcopy(VALIDATION_ENVELOPE_PROPERTIES))
    return spec


# --- documentation (#41) ---------------------------------------------------------------------
#
# Descriptions belong next to the code they describe, and almost all of them are there. These
# tables hold the rest, for code this module may not edit:
#
# * models in ``contracts/`` (the engine boundary, changed only by agreement with Viraj);
# * ``platform/api/app.py`` and ``platform/api/auth.py``, which Viraj's open PR #87 changes.
#
# Each entry only fills a blank: once a description is written in the source, it wins, and the
# entry here can be deleted. When #87 merges, move the ``app.py``/``auth.py`` entries into those
# files (and drop ``include_in_schema=False`` from the exports router in ``app.py``, which makes
# :func:`document_exports` a no-op).

DOCUMENTED_SCHEMAS: dict[str, dict[str, str]] = {
    # contracts/evidence.py
    "Evidence": {
        "value": "The measured value, in `unit`. An index (e.g. NDVI) is never a carbon quantity.",
        "confidence": "The uncertainty interval of the value, when it has one.",
        "provenance": "How the value was produced: method, inputs, parameters and fingerprint.",
    },
    "EvidenceBundle": {
        "case_id": "The case the evidence is about.",
        "schema_version": "Version of the bundle format.",
        "items": "Every evidence item, each with its unit, uncertainty and provenance.",
        "verdict": "The screening verdict, when the engine reached one.",
        "warnings": "Analyst-facing warnings, e.g. that the data is simulated.",
    },
    # contracts/identifiers.py
    "DatasetRef": {"source_uri": "Where the dataset was read from, when recorded."},
    # contracts/result.py
    "RunMetrics": {
        "duration_ms": "Total engine time, in milliseconds.",
        "stage_durations_ms": "Time per engine stage, in milliseconds.",
        "n_units_observed": "Areas observed: the project and its candidate comparisons.",
        "n_donors_admitted": "Comparison areas that passed screening.",
        "n_estimator_fits": "Times the estimator was fitted, placebos included.",
    },
    # contracts/types.py
    "Confidence": {
        "lower": "Lower bound of the interval.",
        "upper": "Upper bound of the interval.",
        "level": "Coverage of the interval, e.g. 0.9 for 90%.",
    },
    "VerificationVerdict": {
        "label": "The screening verdict. A divergence warrants accredited review; never fraud.",
        "rationale": "Why the engine reached the verdict, thresholds included.",
        "caveats": "Statements that must accompany the verdict wherever it is shown.",
        "supporting_evidence_ids": "Evidence items the verdict rests on.",
    },
    # platform/api/auth.py (PR #87)
    "RegisterRequest": {
        "__doc__": "A new account.",
        "email": "Email address; also the sign-in name.",
        "password": "Password, checked against the password policy (`weak_password` if not met).",
    },
    "LoginRequest": {
        "__doc__": "Credentials to sign in with.",
        "email": "Email address.",
        "password": "Password.",
    },
    "ChangePasswordRequest": {
        "__doc__": "Change your password. Every other session of yours is signed out.",
        "current_password": "Your current password.",
        "new_password": "The new password, checked against the password policy.",
    },
    "UpdateUserRequest": {
        "__doc__": "What an administrator may change about an account. Omitted means unchanged.",
        "role": "New platform role: `user`, `dev` or `admin`.",
        "is_active": "False deactivates the account; it can no longer sign in.",
    },
    "MeResponse": {
        "__doc__": "Who you are signed in as, and the organizations you can act for.",
        "auth_required": "Whether this deployment requires sign-in.",
        "registration_open": "Whether `POST /auth/register` accepts new accounts.",
        "user": "Your account, or null when not signed in.",
        "organizations": "Organizations you belong to, with your role in each.",
        "active_organization": "The organization you are acting for; null until you choose one "
        "(automatic when you belong to exactly one).",
    },
}
"""Descriptions for schemas whose source this module may not edit (see the note above)."""

DOCUMENTED_OPERATIONS: dict[tuple[str, str], dict[str, str]] = {
    # platform/api/app.py (PR #87)
    ("get", "/health"): {"summary": "Service status and what the engine can do"},
    ("get", "/cases"): {"summary": "List the cases this deployment knows"},
    ("get", "/cases/{case_id}"): {"summary": "One case in full"},
    ("post", "/cases"): {"summary": "Create a case (sign-in always required)"},
    ("post", "/cases/{case_id}/verify"): {
        "summary": "Run a verification now and wait for the result",
    },
    # platform/api/auth.py (PR #87)
    ("post", "/auth/login"): {
        "description": "Checks the credentials and sets the `gt_session` cookie (HttpOnly, "
        "SameSite=Lax; Secure behind HTTPS). Send that cookie on every later request. A wrong "
        "email or password are indistinguishable (`invalid_credentials`, 401); 5 failures for "
        "one email from one address in 15 minutes are refused with `too_many_attempts` (429, "
        "`Retry-After`)."
    },
    ("get", "/auth/me"): {
        "description": "Your session: the account, your organizations and the active one. "
        "Never an error for a signed-out caller; `user` is then null."
    },
    ("get", "/auth/users"): {"description": "Every account. Platform administrators only (403)."},
    ("patch", "/auth/users/{user_id}"): {
        "description": "Change an account's platform role or deactivate it. Platform "
        "administrators only (403); an unknown user is 404 `user_not_found`."
    },
}
"""Summaries and descriptions for operations whose source this module may not edit."""

PARAMETER_DESCRIPTIONS: dict[str, str] = {
    "case_id": "Case identifier, as listed by `GET /cases`.",
    "run_id": "Run identifier, as returned when the run was submitted or listed.",
    "job_id": "The job's run identifier.",
    "project_id": "Project id or slug.",
    "slug": "Slug of your active organization.",
    "org_slug": "Slug of the organization the grant is for.",
    "user_id": "User id.",
    "z": "Tile zoom level.",
    "x": "Tile column.",
    "y": "Tile row.",
    "limit": "Most items to return on one page.",
    "data_mode": "Only runs on `simulated` or `observed` data.",
}
"""One meaning per path or query parameter name, wherever it appears. Fills blanks only."""


def document_exports(spec: dict[str, Any]) -> dict[str, Any]:
    """Add the CSV and PDF exports to the schema. Returns a new dict.

    ``app.py`` includes their router with ``include_in_schema=False``; they are part of the API
    a consumer uses, so their paths (generated by FastAPI from the router itself) are added
    here. A path the schema already has is left alone, so this is a no-op once ``app.py``
    stops hiding them.
    """
    from fastapi.openapi.utils import get_openapi

    from groundtruth.platform.api.exports import router as exports_router

    spec = copy.deepcopy(spec)
    extra = get_openapi(title="exports", version="0", routes=exports_router.routes)
    for path, item in extra.get("paths", {}).items():
        spec.setdefault("paths", {}).setdefault(path, item)
    schemas = spec.setdefault("components", {}).setdefault("schemas", {})
    for name, schema in extra.get("components", {}).get("schemas", {}).items():
        schemas.setdefault(name, schema)
    return spec


def document_the_rest(spec: dict[str, Any]) -> dict[str, Any]:
    """Fill the blanks from the tables above. Returns a new dict; never overwrites."""
    spec = copy.deepcopy(spec)
    schemas = spec.get("components", {}).get("schemas", {})
    for name, fields in DOCUMENTED_SCHEMAS.items():
        schema = schemas.get(name)
        if schema is None:
            continue
        for field, text in fields.items():
            if field == "__doc__":
                schema.setdefault("description", text)
            elif field in schema.get("properties", {}):
                schema["properties"][field].setdefault("description", text)
    for (method, path), docs in DOCUMENTED_OPERATIONS.items():
        operation = spec.get("paths", {}).get(path, {}).get(method)
        if operation is None:
            continue
        for key, text in docs.items():
            # FastAPI writes a summary from the function name; a written one replaces it.
            if key == "summary" or not operation.get(key):
                operation[key] = text
    for item in spec.get("paths", {}).values():
        for operation in item.values():
            for parameter in operation.get("parameters", []):
                meaning = PARAMETER_DESCRIPTIONS.get(parameter.get("name", ""))
                if meaning and not parameter.get("description"):
                    parameter["description"] = meaning
    return spec


def install_openapi(app: FastAPI) -> None:
    """Serve the adjusted schema at ``/openapi.json``, built once and kept."""
    generate: Callable[[], dict[str, Any]] = app.openapi
    built: dict[str, Any] | None = None

    def openapi() -> dict[str, Any]:
        nonlocal built
        if built is None:
            built = document_the_rest(
                document_error_envelope(require_response_fields(document_exports(generate())))
            )
        return built

    app.openapi = openapi  # type: ignore[method-assign]


def snapshot_text(spec: dict[str, Any]) -> str:
    """The snapshot file's exact contents: stable formatting, one trailing newline."""
    return json.dumps(spec, indent=2, ensure_ascii=False) + "\n"


def write_snapshot(app: FastAPI, path: Path) -> None:
    """Write the served schema to ``path``. LF line endings on every platform."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(snapshot_text(app.openapi()), encoding="utf-8", newline="\n")
