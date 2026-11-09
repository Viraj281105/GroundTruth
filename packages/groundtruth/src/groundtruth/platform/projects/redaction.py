"""Field-level redaction of response models by project access level.

A field that should only be visible from some level up is declared on the model::

    scene_ids: list[str] | None = Field(None, json_schema_extra=min_level("contribute"))

``redact`` then drops the field (the key is absent, not ``null``) for lower levels. It never
alters a value: whatever a lower level can see is exactly what a higher level sees under the
same key. That is the property the route tests check (the ``view`` keys are a strict subset of
the ``audit`` keys and every shared value is equal).

The ranks mirror the capability table in ``auth.authz``: ``contribute`` is the lowest level
holding ``EVIDENCE_FULL`` and ``audit`` the lowest holding ``DIAGNOSTICS``; a test pins that
correspondence so the two cannot drift apart.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import cache
from typing import Any

from pydantic import BaseModel

from groundtruth.platform.auth.authz import ProjectLevel

MIN_LEVEL_KEY = "min_level"

_RANK: dict[str, int] = {"view": 0, "contribute": 1, "audit": 2, "owner": 3}


def min_level(level: str) -> dict[str, Any]:
    """``json_schema_extra`` marking a field visible only from ``level`` upward."""
    if level not in _RANK or level == "view":
        raise ValueError(f"min_level must be one of contribute, audit, owner; got {level!r}")
    return {MIN_LEVEL_KEY: level}


def _visible(required: str | None, level: ProjectLevel) -> bool:
    return required is None or _RANK[level.value] >= _RANK[required]


@cache
def _has_marks(model_type: type[BaseModel]) -> bool:
    """Whether ``model_type`` or any model nested in its fields declares a ``min_level``."""
    for info in model_type.model_fields.values():
        extra = info.json_schema_extra
        if isinstance(extra, Mapping) and MIN_LEVEL_KEY in extra:
            return True
        for nested in _nested_models(info.annotation):
            if _has_marks(nested):
                return True
    return False


def _nested_models(annotation: Any) -> list[type[BaseModel]]:
    found: list[type[BaseModel]] = []
    stack = [annotation]
    while stack:
        item = stack.pop()
        if isinstance(item, type) and issubclass(item, BaseModel):
            found.append(item)
        stack.extend(getattr(item, "__args__", ()) or ())
    return found


def _apply(value: Any, level: ProjectLevel) -> Any:
    if isinstance(value, BaseModel):
        return redact(value, level) if _has_marks(type(value)) else value
    if isinstance(value, list | tuple):
        return [_apply(v, level) for v in value]
    if isinstance(value, dict):
        return {k: _apply(v, level) for k, v in value.items()}
    return value


def redact(model: BaseModel, level: ProjectLevel) -> dict[str, Any]:
    """``model`` as a dict without the fields its ``level`` may not see.

    Nested models and lists of models are redacted the same way. Values are passed through
    untouched, so the result still needs the usual JSON encoding (``jsonable_encoder``).
    """
    out: dict[str, Any] = {}
    for name, info in type(model).model_fields.items():
        extra = info.json_schema_extra
        required = extra.get(MIN_LEVEL_KEY) if isinstance(extra, Mapping) else None
        if not _visible(required if isinstance(required, str) else None, level):
            continue
        out[name] = _apply(getattr(model, name), level)
    return out
