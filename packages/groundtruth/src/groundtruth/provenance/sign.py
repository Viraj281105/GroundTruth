"""Sign / verify blobs with Sigstore cosign (keyless OIDC by default)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class CosignUnavailableError(RuntimeError):
    """Raised when the cosign binary is not on PATH."""


def _cosign() -> str:
    exe = shutil.which("cosign")
    if exe is None:
        raise CosignUnavailableError(
            "cosign not found on PATH; install from https://docs.sigstore.dev/cosign/"
        )
    return exe


def sign_blob(path: Path, bundle_out: Path) -> None:
    """Keyless sign: cosign obtains an OIDC token (browser or CI ambient identity)."""
    subprocess.run(
        [_cosign(), "sign-blob", "--yes", "--bundle", str(bundle_out), str(path)], check=True
    )


def verify_blob(path: Path, bundle: Path, identity_regexp: str, issuer: str) -> None:
    """Verify a keyless signature against an expected signer identity and OIDC issuer."""
    subprocess.run(
        [
            _cosign(),
            "verify-blob",
            "--bundle",
            str(bundle),
            "--certificate-identity-regexp",
            identity_regexp,
            "--certificate-oidc-issuer",
            issuer,
            str(path),
        ],
        check=True,
    )
