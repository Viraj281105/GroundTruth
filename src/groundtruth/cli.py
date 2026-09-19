"""Command-line interface.

    groundtruth cases                     list case definitions
    groundtruth show kariba-redd          inspect one case definition
    groundtruth verify kariba-redd        run the pipeline for a case
    groundtruth doctor                    report what is configured and what is not

``verify`` refuses to run against real providers until they are implemented, and
``--synthetic`` makes the simulated-data path explicit rather than a silent
default.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from groundtruth import __version__
from groundtruth.cases.registry import get_case, load_all_cases
from groundtruth.config import get_settings
from groundtruth.core.errors import GroundTruthError
from groundtruth.ingestion.synthetic import (
    SyntheticCovariateProvider,
    SyntheticDonorPoolProvider,
    SyntheticObservationProvider,
)
from groundtruth.logging import configure_logging
from groundtruth.pipeline import PipelineConfig, run_verification

SYNTHETIC_BANNER = (
    "=" * 78
    + "\nSIMULATED DATA RUN\nThis run uses the synthetic fixture provider. The numbers below describe a\n"
    "test fixture and say nothing about any real project.\n"
    + "=" * 78
)


def _cmd_cases(args: argparse.Namespace) -> int:
    cases = load_all_cases()
    if args.json:
        print(
            json.dumps(
                {
                    cid: {
                        "name": c.claim.name,
                        "country": c.claim.country,
                        "standard": c.claim.standard.value,
                        "indicator": c.indicator.value,
                        "status": c.status,
                    }
                    for cid, c in cases.items()
                },
                indent=2,
            )
        )
        return 0
    if not cases:
        print("no case definitions found")
        return 1
    width = max(len(c) for c in cases)
    for cid, case in cases.items():
        print(
            f"{cid:<{width}}  {case.claim.standard.value:<12} {case.indicator.value:<5} "
            f"{case.status:<12} {case.claim.name}"
        )
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    case = get_case(args.case_id)
    print(f"case_id      : {case.case_id}")
    print(f"project      : {case.claim.name} ({case.claim.country})")
    print(f"standard     : {case.claim.standard.value} {case.claim.registry_id or ''}".rstrip())
    print(f"ecosystem    : {case.ecosystem}")
    print(f"area (ha)    : {case.claim.project_area_ha}")
    print(f"indicator    : {case.indicator.value}")
    print(
        f"window       : pre {case.window.pre_start}-{case.window.pre_end} "
        f"({case.window.n_pre_periods}p), post {case.window.post_start}-{case.window.post_end} "
        f"({case.window.n_post_periods}p)"
    )
    print(f"donor region : {case.donor_search_region.strip()}")
    print(f"status       : {case.status}")
    if case.known_reference:
        print("\nknown_reference (third-party, NOT an input to the estimate):")
        for key, value in case.known_reference.items():
            print(f"  {key}: {value}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    settings = get_settings()
    case = get_case(args.case_id)

    if not args.synthetic:
        print(
            "Real Earth-observation providers are not implemented yet, so this case cannot be "
            "verified against real data.\n"
            "Re-run with --synthetic to exercise the pipeline on simulated data, or see "
            "docs/10-roadmap.md milestone M2.",
            file=sys.stderr,
        )
        return 2

    print(SYNTHETIC_BANNER, file=sys.stderr)
    observation = SyntheticObservationProvider(
        seed=settings.random_seed,
        treated_unit_id=case.case_id,
        true_effect=args.true_effect,
        treatment_period=case.window.post_start,
    )
    result = run_verification(
        case,
        observation,
        SyntheticCovariateProvider(seed=settings.random_seed, project_unit_id=case.case_id),
        SyntheticDonorPoolProvider(),
        config=PipelineConfig(min_donors=args.min_donors),
    )

    if args.json:
        print(result.bundle.to_json())
    else:
        print(result.report.markdown)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result.report.markdown, encoding="utf-8")
        bundle_path = out.with_suffix(".bundle.json")
        bundle_path.write_text(result.bundle.to_json(), encoding="utf-8")
        print(f"\nwrote {out} and {bundle_path}", file=sys.stderr)

    return 0


def _cmd_doctor(_: argparse.Namespace) -> int:
    settings = get_settings()
    rows = [
        ("version", __version__),
        ("environment", settings.app_env),
        ("cases found", str(len(load_all_cases()))),
        ("earth observation configured", str(settings.earth_observation_configured)),
        ("earth observation implemented", "no - see docs/10-roadmap.md M2"),
        ("genai provider", settings.genai_provider),
        ("genai configured", str(settings.genai_configured)),
        ("genai narration implemented", "no - deterministic renderer is used"),
        ("synthetic pipeline", "yes"),
    ]
    width = max(len(k) for k, _ in rows)
    for key, value in rows:
        print(f"{key:<{width}} : {value}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="groundtruth",
        description="Independent causal verification for restoration and carbon-credit claims.",
    )
    parser.add_argument("--version", action="version", version=f"groundtruth {__version__}")
    parser.add_argument("--log-level", default=None, help="Override the configured log level.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    cases = subparsers.add_parser("cases", help="List case definitions.")
    cases.add_argument("--json", action="store_true")
    cases.set_defaults(func=_cmd_cases)

    show = subparsers.add_parser("show", help="Show one case definition.")
    show.add_argument("case_id")
    show.set_defaults(func=_cmd_show)

    verify = subparsers.add_parser("verify", help="Run the verification pipeline for a case.")
    verify.add_argument("case_id")
    verify.add_argument(
        "--synthetic",
        action="store_true",
        help="Run against simulated data. Required until real providers are implemented.",
    )
    verify.add_argument(
        "--true-effect",
        type=float,
        default=0.06,
        help="Effect injected into the simulated treated unit, for testing recovery.",
    )
    verify.add_argument("--min-donors", type=int, default=10)
    verify.add_argument("--json", action="store_true", help="Emit the evidence bundle as JSON.")
    verify.add_argument("--out", help="Write the report and bundle to this path.")
    verify.set_defaults(func=_cmd_verify)

    doctor = subparsers.add_parser("doctor", help="Report what is configured and implemented.")
    doctor.set_defaults(func=_cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level or get_settings().log_level)
    try:
        exit_code: int = args.func(args)
        return exit_code
    except GroundTruthError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
