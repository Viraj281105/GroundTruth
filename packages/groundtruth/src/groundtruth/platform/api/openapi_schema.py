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


def install_openapi(app: FastAPI) -> None:
    """Serve the adjusted schema at ``/openapi.json``, built once and kept."""
    generate: Callable[[], dict[str, Any]] = app.openapi
    built: dict[str, Any] | None = None

    def openapi() -> dict[str, Any]:
        nonlocal built
        if built is None:
            built = require_response_fields(generate())
        return built

    app.openapi = openapi  # type: ignore[method-assign]


def snapshot_text(spec: dict[str, Any]) -> str:
    """The snapshot file's exact contents: stable formatting, one trailing newline."""
    return json.dumps(spec, indent=2, ensure_ascii=False) + "\n"


def write_snapshot(app: FastAPI, path: Path) -> None:
    """Write the served schema to ``path``. LF line endings on every platform."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(snapshot_text(app.openapi()), encoding="utf-8", newline="\n")
