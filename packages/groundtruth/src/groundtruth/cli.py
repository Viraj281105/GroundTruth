"""Command-line interface.

    groundtruth cases                     list case definitions
    groundtruth show kariba-redd          inspect one case definition
    groundtruth verify kariba-redd        run the pipeline for a case
    groundtruth doctor                    report what is configured and what is not
    groundtruth submit kariba-redd --synthetic   queue a job for the worker
    groundtruth job run_...               show a job's status

``verify`` refuses to run against real providers until they are implemented. The
simulated paths (``--synthetic``, ``--synthetic-fixture``) are explicit opt-ins,
never a silent default, and every output from them is labelled SYNTHETIC.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from groundtruth import __version__
from groundtruth.contracts.errors import DataUnavailableError, GroundTruthError
from groundtruth.contracts.result import EngineStatus
from groundtruth.engine import ENGINE_VERSION, describe_engine, run_analysis
from groundtruth.logging import configure_logging
from groundtruth.platform.cases.registry import get_case, load_all_cases
from groundtruth.platform.config import get_settings
from groundtruth.platform.datasets.access import (
    SYNTHETIC_FIXTURE_CASES,
    SYNTHETIC_KARIBA_FIXTURE_DATASET,
    earth_engine_access,
    real_observation_cases,
    synthetic_access,
    synthetic_fixture_access,
    synthetic_fixture_available,
)
from groundtruth.platform.reports.narrative import generate_report

SYNTHETIC_BANNER = (
    "=" * 78 + "\nSIMULATED DATA RUN\n"
    "This run uses the synthetic fixture provider. The numbers below describe a\n"
    "test fixture and say nothing about any real project.\n" + "=" * 78
)

SYNTHETIC_FIXTURE_BANNER = (
    "=" * 78 + "\nSYNTHETIC FIXTURE RUN - NOT SATELLITE OBSERVATIONS\n"
    "This run replays a precomputed SYNTHETIC series from disk. No imagery was\n"
    "retrieved or processed. Results describe a test fixture, not any real project.\n" + "=" * 78
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

    if args.synthetic_fixture:
        print(SYNTHETIC_FIXTURE_BANNER, file=sys.stderr)
        request = case.to_request(
            data_mode="simulated",
            seed=settings.random_seed,
            min_donors=case.resolve_min_donors(args.min_donors),
            datasets=(SYNTHETIC_KARIBA_FIXTURE_DATASET,),
        )
        try:
            data = synthetic_fixture_access(request)
        except DataUnavailableError as exc:
            print(f"{exc}", file=sys.stderr)
            return 2
        result = run_analysis(request, data)
    elif not args.synthetic:
        request = case.to_request(
            data_mode="observed",
            seed=settings.random_seed,
            min_donors=case.resolve_min_donors(args.min_donors),
        )
        try:
            data = earth_engine_access(request)
        except DataUnavailableError as exc:
            print(
                "Real Earth-observation providers are not implemented yet for this case.\n"
                f"{exc}\n"
                "Re-run with --synthetic (or --synthetic-fixture) to exercise the pipeline on "
                "SYNTHETIC data, or see docs/product/roadmap-detail.md milestone M1.",
                file=sys.stderr,
            )
            return 2
        result = run_analysis(request, data)
    else:
        print(SYNTHETIC_BANNER, file=sys.stderr)
        request = case.to_request(
            data_mode="simulated",
            seed=settings.random_seed,
            min_donors=case.resolve_min_donors(args.min_donors),
        )
        result = run_analysis(request, synthetic_access(request, true_effect=args.true_effect))

    if result.status is not EngineStatus.COMPLETED:
        assert result.error is not None
        kind = "refused" if result.error.is_refusal else "error"
        print(
            f"analysis {kind} [{result.error.code.value}]: {result.error.message}",
            file=sys.stderr,
        )
        if result.error.remediation:
            print(f"  -> {result.error.remediation}", file=sys.stderr)
        return 0 if result.error.is_refusal else 1

    bundle = result.bundle
    assert bundle is not None
    report = generate_report(bundle)

    if args.json:
        print(result.model_dump_json(indent=2))
    else:
        print(report.markdown)

    print(
        f"\nrun_id={result.run_id} spec_hash={result.spec_hash} "
        f"engine={result.engine.engine_version} duration={result.metrics.duration_ms:.0f}ms",
        file=sys.stderr,
    )

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report.markdown, encoding="utf-8")
        result_path = out.with_suffix(".result.json")
        result_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        print(f"wrote {out} and {result_path}", file=sys.stderr)

    return 0


def _job_sessions() -> Any:
    """Sessions on the configured, fully migrated database, or ``None`` after explaining why.

    Imported here, not at the top, so the commands that need no database still work
    without the ``db`` extra installed.
    """
    # These commands only read the schema version; Alembic's INFO chatter (emitted as it
    # loads) is noise here. The worker, which can migrate, keeps it.
    logging.getLogger("alembic").setLevel(logging.WARNING)
    from groundtruth.platform.store import migrate
    from groundtruth.platform.store.database import create_db_engine, create_session_factory

    if not migrate.is_at_head():
        print(
            "the database is not migrated to the latest schema. Run:\n"
            "  python -m apps.worker.main --migrate --exit-when-idle",
            file=sys.stderr,
        )
        return None
    return create_session_factory(create_db_engine())


def _cmd_submit(args: argparse.Namespace) -> int:
    from groundtruth.platform.jobs.queue import JobQueue
    from groundtruth.platform.store.sql import SqlEvidenceStore

    if not args.synthetic:
        print(
            "Real Earth-observation providers are not implemented yet, so a real-data job "
            "would only fail.\nRe-run with --synthetic to queue a simulated run.",
            file=sys.stderr,
        )
        return 2

    settings = get_settings()
    case = get_case(args.case_id)
    sessions = _job_sessions()
    if sessions is None:
        return 2
    print(SYNTHETIC_BANNER, file=sys.stderr)
    SqlEvidenceStore(sessions).upsert_case(case)
    request = case.to_request(
        data_mode="simulated",
        seed=settings.random_seed,
        min_donors=case.resolve_min_donors(args.min_donors),
    )
    submission = JobQueue(sessions).submit(request, requested_by=args.requested_by)

    if args.json:
        print(submission.model_dump_json(indent=2))
        return 0
    how = (
        "an existing result answers this request; nothing new will run"
        if submission.from_cache
        else "an identical job is already in flight"
        if submission.deduplicated
        else "queued; start a worker to run it"
    )
    print(f"run_id={submission.run_id} status={submission.status.value} ({how})")
    return 0


def _cmd_process_ingestions(args: argparse.Namespace) -> int:
    """Run queued observation-ingestion requests now (operator-supervised), then exit."""
    from groundtruth.platform.projects.ingestion import process_pending

    sessions = _job_sessions()
    if sessions is None:
        return 2
    done = process_pending(sessions, f"cli-{os.getpid()}", limit=args.limit)
    print(f"process-ingestions: ran {done} queued request(s)")
    return 0


def _cmd_seed(args: argparse.Namespace) -> int:
    from groundtruth.platform.projects.seed import seed

    sessions = _job_sessions()
    if sessions is None:
        return 2
    settings = get_settings()
    with sessions() as db:
        report = seed(db, cases_dir=settings.cases_dir, demo=args.demo)
        db.commit()
    print(f"seed: created={report.created} existing={report.existing}")
    print(f"seed: backfilled runs={report.backfilled_runs} jobs={report.backfilled_jobs}")
    for email in report.existing_demo_users:
        print(f"demo user exists (password unchanged): {email}")
    if report.demo_users:
        if args.passwords_file:
            _write_credentials(Path(args.passwords_file), report.demo_users)
            print(f"demo credentials written to {args.passwords_file}")
        else:
            print("Demo credentials (shown once; DEVELOPMENT ONLY, never reuse):")
            for email, password in report.demo_users:
                print("  " + email + "\t" + password)
    return 0


def _write_credentials(path: Path, users: list[tuple[str, str]]) -> None:
    """Write ``email<TAB>password`` lines, owner-readable only where the OS supports it."""
    import os

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        for email, password in users:
            handle.write(email + "\t" + password + "\n")
    with contextlib.suppress(OSError):  # not supported on every filesystem
        os.chmod(path, 0o600)


def _cmd_job(args: argparse.Namespace) -> int:
    from groundtruth.platform.jobs.queue import JobQueue

    sessions = _job_sessions()
    if sessions is None:
        return 2
    status = JobQueue(sessions).status(args.run_id)
    if status is None:
        print(f"no run {args.run_id!r}", file=sys.stderr)
        return 1
    if args.json:
        print(status.model_dump_json(indent=2))
        return 0
    if status.is_simulated:
        print("SIMULATED DATA: this run used the synthetic fixture, not observations.")
    rows = [
        ("run_id", status.run_id),
        ("case_id", status.case_id),
        ("status", status.status.value),
        ("engine status", status.engine_status or "-"),
        ("data mode", status.data_mode),
        ("attempts", f"{status.attempts} of {status.max_attempts}" if status.attempts else "-"),
        ("worker", status.locked_by or "-"),
        ("cancel requested", "yes" if status.cancel_requested else "no"),
        ("last error", json.dumps(status.last_error) if status.last_error else "-"),
    ]
    width = max(len(k) for k, _ in rows)
    for key, value in rows:
        print(f"{key:<{width}} : {value}")
    return 0


def _cmd_ingest_stac(args: argparse.Namespace) -> int:
    from groundtruth.data_access.aoi_pipeline import (
        AOIObservationCache,
        ingest_live_aoi_observations,
    )
    from groundtruth.data_access.stac import DEFAULT_STAC_URL

    settings = get_settings()
    case = get_case(args.case_id)
    if not case.claim.boundary_path:
        print(f"error: case {args.case_id!r} has no boundary_path configured", file=sys.stderr)
        return 1
    boundary_file = settings.cases_dir.parent / case.claim.boundary_path
    if not boundary_file.is_file():
        print(f"error: boundary file not found at {boundary_file}", file=sys.stderr)
        return 1

    aoi_geojson = json.loads(boundary_file.read_text(encoding="utf-8"))
    cache_dir = (
        Path(args.cache_dir) if args.cache_dir else (settings.data_dir / "processed" / "stac_cache")
    )
    cache = AOIObservationCache(cache_dir)

    indicators = tuple(args.indicators) if args.indicators else ("ndvi", "evi", "ndmi", "nbr")
    years = [int(y) for y in args.years]

    bundles = ingest_live_aoi_observations(
        unit_id=case.case_id,
        aoi_geojson=aoi_geojson,
        years=years,
        indicators=indicators,
        platform=args.platform,
        max_cloud_cover=args.max_cloud_cover,
        date_window=(args.start_mmdd, args.end_mmdd),
        max_scenes_per_year=args.max_scenes_per_year,
        tile_id=args.tile_id,
        resolution_m=args.resolution_m,
        catalog_url=args.catalog_url or DEFAULT_STAC_URL,
        cache=cache,
    )

    saved_paths = {ind: str(cache.cache_path(case.case_id, ind)) for ind in bundles}
    reloaded_origins = {
        ind: cache.get(case.case_id, ind, require_real=True).data_origin.value for ind in bundles
    }

    primary_bundle = bundles[indicators[0]]
    summary_payload = {
        "case_id": case.case_id,
        "boundary_path": str(boundary_file),
        "aoi_bbox": list(primary_bundle.bbox),
        "catalog_url": primary_bundle.catalog_url,
        "live_data_origin": primary_bundle.data_origin.value,
        "cached_data_origins": reloaded_origins,
        "saved_files": saved_paths,
        "raster_grid": primary_bundle.provenance.parameters.get("raster_grid"),
        "scenes_metadata": primary_bundle.provenance.parameters.get("scenes_metadata"),
        "records_by_year": [r.to_dict() for r in primary_bundle.records],
    }

    if args.json:
        print(json.dumps(summary_payload, indent=2, sort_keys=True))
    else:
        print(f"case_id          : {case.case_id}")
        print(f"catalog_url      : {primary_bundle.catalog_url}")
        print(f"live origin      : {primary_bundle.data_origin.value}")
        print(f"cached origin    : {reloaded_origins[indicators[0]]}")
        print(f"aoi_bbox         : {primary_bundle.bbox}")
        for r in primary_bundle.records:
            print(
                f"year {r.year}        : scenes={r.n_scenes} {list(r.scene_ids)} "
                f"dates={list(r.acquisition_dates)} valid_px={r.n_valid_pixels}/{r.n_total_pixels} "
                f"clear_frac={r.clear_pixel_fraction:.4f} indices={r.indices}"
            )
        for ind, path_str in saved_paths.items():
            print(f"saved [{ind:<4}]     : {path_str}")
    return 0


def _cmd_doctor(_: argparse.Namespace) -> int:
    settings = get_settings()
    capabilities = describe_engine()
    real_cases = real_observation_cases()
    fixture_cases = [cid for cid in SYNTHETIC_FIXTURE_CASES if synthetic_fixture_available(cid)]
    genai_configured = settings.genai_configured
    genai_narration_implemented = (
        "yes"
        if settings.genai_provider in ("anthropic", "gemini")
        else "no - deterministic renderer is used"
    )
    rows = [
        ("version", __version__),
        ("engine version", ENGINE_VERSION),
        ("contract version", capabilities["contract_version"]),
        ("environment", settings.app_env),
        ("cases found", str(len(load_all_cases()))),
        ("earth observation credentials present", str(settings.earth_observation_configured)),
        (
            "earth observation ingestion implemented",
            "no",
        ),
        (
            "real observation data available",
            ", ".join(real_cases) if real_cases else "none (no satellite data for any case)",
        ),
        (
            "synthetic fixtures available",
            (", ".join(fixture_cases) + " (SYNTHETIC - not satellite data)")
            if fixture_cases
            else "none",
        ),
        (
            "biomass-to-carbon calibration",
            "NOT CALIBRATED - no validated parameters shipped; carbon estimates are "
            "INCONCLUSIVE unless a sourced calibration is supplied",
        ),
        ("genai provider", settings.genai_provider),
        ("genai configured", str(genai_configured)),
        ("genai narration implemented", genai_narration_implemented),
        ("synthetic pipeline", "yes (simulated data only; results are labelled SYNTHETIC)"),
    ]
    rows += [
        (f"engine: {name.replace('_', ' ')}", "yes" if ok else "no")
        for name, ok in capabilities["implemented"].items()
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
        "--synthetic-fixture",
        action="store_true",
        help="Replay the precomputed SYNTHETIC benchmark fixture (kariba-redd only). "
        "Not satellite data.",
    )
    verify.add_argument(
        "--true-effect",
        type=float,
        default=0.06,
        help="Effect injected into the simulated treated unit, for testing recovery.",
    )
    verify.add_argument(
        "--min-donors",
        type=int,
        default=None,
        help="Omit to use the case's own floor; a higher value is stricter, a lower one is refused.",
    )
    verify.add_argument("--json", action="store_true", help="Emit the full AnalysisResult as JSON.")
    verify.add_argument("--out", help="Write the report and bundle to this path.")
    verify.set_defaults(func=_cmd_verify)

    submit = subparsers.add_parser(
        "submit", help="Queue an analysis job for a case (needs DATABASE_URL)."
    )
    submit.add_argument("case_id")
    submit.add_argument(
        "--synthetic",
        action="store_true",
        help="Queue a simulated run. Required until real providers are implemented.",
    )
    submit.add_argument(
        "--min-donors",
        type=int,
        default=None,
        help="Omit to use the case's own floor; a higher value is stricter, a lower one is refused.",
    )
    submit.add_argument("--requested-by", default=None)
    submit.add_argument("--json", action="store_true")
    submit.set_defaults(func=_cmd_submit)

    job = subparsers.add_parser("job", help="Show a job's status (needs DATABASE_URL).")
    job.add_argument("run_id")
    job.add_argument("--json", action="store_true")
    job.set_defaults(func=_cmd_job)

    seed_cmd = subparsers.add_parser(
        "seed",
        help="Idempotently import cases as Reference projects (needs DATABASE_URL).",
    )
    seed_cmd.add_argument(
        "--demo",
        action="store_true",
        help="Also create four demo organizations and users (development only).",
    )
    seed_cmd.add_argument(
        "--passwords-file",
        default=None,
        help="With --demo: write email<TAB>password lines here (mode 600) instead of printing.",
    )
    seed_cmd.set_defaults(func=_cmd_seed)

    proc = subparsers.add_parser(
        "process-ingestions",
        help="Run queued satellite-observation requests for user projects now, then exit.",
    )
    proc.add_argument("--limit", type=int, default=None, help="Run at most this many requests.")
    proc.set_defaults(func=_cmd_process_ingestions)

    doctor = subparsers.add_parser("doctor", help="Report what is configured and implemented.")
    doctor.set_defaults(func=_cmd_doctor)

    ingest = subparsers.add_parser(
        "ingest-stac",
        help="Search a live STAC catalog, retrieve real satellite rasters over a case AOI, "
        "apply cloud masking, compute NDVI/EVI/NDMI/NBR, and save to AOIObservationCache.",
    )
    ingest.add_argument("case_id", help="Case slug (e.g. kariba-redd).")
    ingest.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=[2021, 2022, 2023],
        help="Calendar years to ingest.",
    )
    ingest.add_argument(
        "--indicators",
        nargs="+",
        default=["ndvi", "evi", "ndmi", "nbr"],
        help="Spectral indices to compute and cache.",
    )
    ingest.add_argument(
        "--platform",
        default="sentinel-2",
        choices=[
            "sentinel-2",
            "landsat",
            "sentinel-1",
            "sentinel-2-l2a",
            "landsat-c2-l2",
            "sentinel-1-rtc",
        ],
    )
    ingest.add_argument("--max-cloud-cover", type=float, default=25.0)
    ingest.add_argument("--start-mmdd", default="06-01")
    ingest.add_argument("--end-mmdd", default="06-30")
    ingest.add_argument("--max-scenes-per-year", type=int, default=2)
    ingest.add_argument("--tile-id", default="36LTH")
    ingest.add_argument("--resolution-m", type=float, default=100.0)
    ingest.add_argument("--catalog-url", default=None)
    ingest.add_argument("--cache-dir", default=None)
    ingest.add_argument("--json", action="store_true")
    ingest.set_defaults(func=_cmd_ingest_stac)

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
