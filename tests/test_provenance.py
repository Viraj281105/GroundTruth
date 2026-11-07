"""Offline tests for evidence-bundle provenance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from groundtruth.provenance.__main__ import main
from groundtruth.provenance.bundle import build_manifest, canonical_json
from groundtruth.provenance.sign import CosignUnavailableError, sign_blob
from groundtruth.provenance.verify import verify_manifest


def _files(tmp: Path) -> tuple[Path, Path]:
    result = tmp / "result.json"
    result.write_text(json.dumps({"b": 1, "a": [2.5]}))
    data = tmp / "in.csv"
    data.write_text("x\n1\n")
    return result, data


def test_canonical_json_is_order_independent() -> None:
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})


def test_roundtrip_and_tamper(tmp_path: Path) -> None:
    result, data = _files(tmp_path)
    manifest = build_manifest(result, [data], seed=7)
    assert verify_manifest(manifest, result, [data]) == []
    data.write_text("x\n2\n")
    assert "input hash mismatch: in.csv" in verify_manifest(manifest, result, [data])
    manifest["seed"] = 8
    assert "manifest hash mismatch" in verify_manifest(manifest, result, [data])


def test_cli_build_verify(tmp_path: Path) -> None:
    result, data = _files(tmp_path)
    out = tmp_path / "m.json"
    argv = ["build", str(result), "--input", str(data), "--seed", "1", "--out", str(out)]
    assert main(argv) == 0
    assert main(["verify", str(out), str(result), "--input", str(data)]) == 0


def test_sign_without_cosign(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: None)
    with pytest.raises(CosignUnavailableError):
        sign_blob(tmp_path / "m.json", tmp_path / "b.json")
