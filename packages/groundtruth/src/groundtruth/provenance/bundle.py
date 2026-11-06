"""Build a canonical-JSON SHA-256 manifest for an evidence bundle."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import groundtruth

SCHEMA = "groundtruth.provenance/1"


def canonical_json(obj: Any) -> bytes:
    """Deterministic JSON: sorted keys, no whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    result_path: Path,
    input_paths: Sequence[Path] = (),
    *,
    seed: int | None = None,
    engine_version: str | None = None,
) -> dict[str, Any]:
    """Return a manifest whose ``manifest_sha256`` covers every other field."""
    result = json.loads(result_path.read_text(encoding="utf-8"))
    body: dict[str, Any] = {
        "schema": SCHEMA,
        "engine_version": engine_version or groundtruth.__version__,
        "seed": seed,
        "result": {
            "name": result_path.name,
            "canonical_sha256": sha256_bytes(canonical_json(result)),
        },
        "inputs": {p.name: sha256_file(p) for p in sorted(input_paths, key=lambda p: p.name)},
    }
    body["manifest_sha256"] = sha256_bytes(canonical_json(body))
    return body
