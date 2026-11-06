"""CLI: ``python -m groundtruth.provenance {build,verify,sign,verify-sig}``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from groundtruth.provenance.bundle import build_manifest, canonical_json
from groundtruth.provenance.sign import CosignUnavailableError, sign_blob, verify_blob
from groundtruth.provenance.verify import verify_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m groundtruth.provenance")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("result", type=Path)
    b.add_argument("--input", type=Path, action="append", default=[])
    b.add_argument("--seed", type=int)
    b.add_argument("--out", type=Path, required=True)
    v = sub.add_parser("verify")
    v.add_argument("manifest", type=Path)
    v.add_argument("result", type=Path)
    v.add_argument("--input", type=Path, action="append", default=[])
    s = sub.add_parser("sign")
    s.add_argument("manifest", type=Path)
    s.add_argument("--bundle", type=Path, required=True)
    vs = sub.add_parser("verify-sig")
    vs.add_argument("manifest", type=Path)
    vs.add_argument("--bundle", type=Path, required=True)
    vs.add_argument("--identity-regexp", required=True)
    vs.add_argument("--issuer", default="https://token.actions.githubusercontent.com")
    args = parser.parse_args(argv)

    try:
        if args.cmd == "build":
            manifest = build_manifest(args.result, args.input, seed=args.seed)
            args.out.write_bytes(canonical_json(manifest) + b"\n")
        elif args.cmd == "verify":
            loaded = json.loads(args.manifest.read_text(encoding="utf-8"))
            problems = verify_manifest(loaded, args.result, args.input)
            for problem in problems:
                print(problem, file=sys.stderr)
            return 1 if problems else 0
        elif args.cmd == "sign":
            sign_blob(args.manifest, args.bundle)
        else:
            verify_blob(args.manifest, args.bundle, args.identity_regexp, args.issuer)
    except CosignUnavailableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
