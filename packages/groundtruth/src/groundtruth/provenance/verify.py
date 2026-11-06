"""Verify a provenance manifest against the files it describes."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from groundtruth.provenance.bundle import canonical_json, sha256_bytes, sha256_file


def verify_manifest(
    manifest: dict[str, Any], result_path: Path, input_paths: Sequence[Path] = ()
) -> list[str]:
    """Return a list of problems; empty means the bundle verifies."""
    problems: list[str] = []
    body = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    if sha256_bytes(canonical_json(body)) != manifest.get("manifest_sha256"):
        problems.append("manifest hash mismatch")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if sha256_bytes(canonical_json(result)) != manifest.get("result", {}).get("canonical_sha256"):
        problems.append("result hash mismatch")
    expected: dict[str, str] = manifest.get("inputs", {})
    seen = {p.name: p for p in input_paths}
    for name, digest in expected.items():
        if name not in seen:
            problems.append(f"input not provided: {name}")
        elif sha256_file(seen[name]) != digest:
            problems.append(f"input hash mismatch: {name}")
    for name in sorted(seen.keys() - expected.keys()):
        problems.append(f"input not in manifest: {name}")
    return problems
