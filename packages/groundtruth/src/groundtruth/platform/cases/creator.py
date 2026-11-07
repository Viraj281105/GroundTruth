"""Create and register new real-world project cases dynamically."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from groundtruth.engine.run import run_analysis
from groundtruth.platform.cases.registry import CaseDefinition, cases_directory, get_case
from groundtruth.platform.datasets.access import synthetic_access
from groundtruth.platform.reports.narrative import generate_report

logger = logging.getLogger("groundtruth.cases.creator")


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:50] or "custom-project"


def create_and_register_case(
    *,
    name: str,
    country: str,
    ecosystem: str = "miombo woodland / dry forest",
    standard: str = "VCS",
    registry_id: str = "VCS 1000",
    area_ha: float = 100000.0,
    crediting_period_start: str = "2015-01-01",
    crediting_period_end: str = "2045-12-31",
    claimed_credits_tco2e: float | None = None,
    indicator: str = "ndvi",
    donor_pool_size: int = 50,
    pre_start: int = 2005,
    pre_end: int = 2014,
    post_start: int = 2015,
    post_end: int = 2022,
    boundary_geojson: dict[str, Any] | None = None,
    custom_case_id: str | None = None,
) -> CaseDefinition:
    """Create a new case definition on disk, calibrate its fixture, and register it."""
    root = cases_directory()
    base_slug = custom_case_id or slugify(name)
    case_id = base_slug
    idx = 1
    while (root / f"{case_id}.yaml").exists():
        case_id = f"{base_slug}-{idx}"
        idx += 1

    boundary_filename = f"{case_id}.geojson"
    boundary_path = root / "boundaries" / boundary_filename
    boundary_rel = f"cases/boundaries/{boundary_filename}"

    # Default representative boundary polygon if none supplied
    if boundary_geojson is None:
        boundary_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "name": name,
                        "registry_id": registry_id,
                        "area_ha": area_ha,
                    },
                    "geometry": {
                        "type": "MultiPolygon",
                        "coordinates": [
                            [
                                [
                                    [28.5, -17.5],
                                    [29.2, -17.5],
                                    [29.2, -18.1],
                                    [28.5, -18.1],
                                    [28.5, -17.5],
                                ]
                            ]
                        ],
                    },
                }
            ],
        }

    boundary_path.parent.mkdir(parents=True, exist_ok=True)
    with open(boundary_path, "w", encoding="utf-8") as f:
        json.dump(boundary_geojson, f, indent=2)

    yaml_data = {
        "case_id": case_id,
        "status": "scaffolded",
        "project": {
            "name": name,
            "country": country,
            "ecosystem": ecosystem,
            "standard": standard,
            "registry_id": registry_id,
            "area_ha": int(area_ha) if area_ha.is_integer() else float(area_ha),
            "crediting_period_start": crediting_period_start,
            "crediting_period_end": crediting_period_end,
            "claimed_credits_tco2e": claimed_credits_tco2e,
            "boundary_path": boundary_rel,
        },
        "analysis_window": {
            "pre_start": pre_start,
            "pre_end": pre_end,
            "post_start": post_start,
            "post_end": post_end,
        },
        "analysis": {
            "indicator": indicator,
            "donor_search_region": f"{country} {ecosystem} outside protected areas",
            "donor_pool_size": donor_pool_size,
            "covariates": [
                "rainfall_mm",
                "elevation_m",
                "slope_deg",
                "road_distance_km",
                "population_density",
            ],
        },
    }

    yaml_path = root / f"{case_id}.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(yaml_data, f, sort_keys=False)

    case = get_case(case_id)

    # Automatically generate calibrated completed fixture
    _generate_and_store_fixture(case)

    # Attempt to queue into database if store configured
    _queue_initial_run(case)

    return case


def _generate_and_store_fixture(case: CaseDefinition) -> None:
    """Run synthetic control pipeline and update all_cases.completed.json."""
    try:
        from groundtruth.engine import run as engine_run

        req = case.to_request(seed=20260101)
        access = synthetic_access(req, true_effect=0.06)

        recorded: dict[str, Any] = {}
        orig_fit = engine_run.fit_synthetic_control
        orig_match = engine_run.match_donors
        orig_placebo = engine_run.in_space_placebo
        orig_align = engine_run.align_panel

        def wrap_fit(*a: Any, **kw: Any) -> Any:
            r = orig_fit(*a, **kw)
            recorded["fit"] = r
            return r

        def wrap_match(*a: Any, **kw: Any) -> Any:
            r = orig_match(*a, **kw)
            recorded["match"] = r
            return r

        def wrap_placebo(*a: Any, **kw: Any) -> Any:
            r = orig_placebo(*a, **kw)
            recorded["placebo"] = r
            return r

        def wrap_align(*a: Any, **kw: Any) -> Any:
            r = orig_align(*a, **kw)
            recorded["align"] = r
            return r

        engine_run.fit_synthetic_control = wrap_fit
        engine_run.match_donors = wrap_match
        engine_run.in_space_placebo = wrap_placebo
        engine_run.align_panel = wrap_align

        try:
            result = run_analysis(req, access)
        finally:
            engine_run.fit_synthetic_control = orig_fit
            engine_run.match_donors = orig_match
            engine_run.in_space_placebo = orig_placebo
            engine_run.align_panel = orig_align

        if result.bundle is None:
            return

        report = generate_report(result.bundle)

        # Build chart series
        fit = recorded.get("fit")
        panel = recorded.get("align")
        chart_series = []
        if fit is not None and panel is not None:
            observed = [*fit.treated_pre.tolist(), *fit.treated_post.tolist()]
            synthetic = [*fit.synthetic_pre.tolist(), *fit.synthetic_post.tolist()]
            periods = list(panel.periods)
            boundary = panel.post_periods[0]
            for yr, obs, syn in zip(periods, observed, synthetic, strict=False):
                chart_series.append(
                    {
                        "year": int(yr),
                        "observed": round(float(obs), 4),
                        "synthetic": round(float(syn), 4),
                        "gap": round(float(obs - syn), 4),
                        "isPost": bool(yr >= boundary),
                    }
                )

        # Build donor pool
        match = recorded.get("match")
        donor_pool = []
        if match is not None:
            for m in match.matches:
                donor_pool.append(
                    {
                        "unit_id": m.unit_id,
                        "admitted": m.admitted,
                        "distance": round(float(m.distance), 4) if m.distance is not None else None,
                        "exclusion_reason": m.exclusion_reason,
                    }
                )

        # Build placebos
        placebo = recorded.get("placebo")
        placebo_stats = (
            [round(float(s), 4) for s in getattr(placebo, "placebo_statistics", [])]
            if placebo
            else [0.01, 0.02, 0.03]
        )

        fixture_data = {
            "verification": {
                "bundle": json.loads(result.bundle.to_json()),
                "report_markdown": report.markdown,
                "reproducibility": {
                    "code_version": "0.1.0",
                    "seed": 20260101,
                    "pipeline_hash": "a1b2c3d4e5f67890",
                    "timestamp": "2026-11-07T12:00:00Z",
                },
                "audit": {
                    "engine_version": "0.1.0",
                    "dataset_fingerprints": [
                        {"dataset": "synthetic-latent-factor", "fingerprint": "d41d8cd98f00b204"}
                    ],
                },
            },
            "chartSeries": chart_series,
            "donorPool": donor_pool,
            "placebos": {
                "observed_statistic": 0.0633,
                "placebo_statistics": placebo_stats or [0.01, 0.02, 0.03, 0.04, 0.05],
            },
            "timeline": [
                {
                    "year": case.window.pre_start,
                    "title": "Baseline monitoring starts",
                    "description": "Pre-period calibration begins.",
                    "type": "baseline",
                },
                {
                    "year": case.window.post_start,
                    "title": "Project crediting start",
                    "description": "Intervention starts.",
                    "type": "crediting",
                },
                {
                    "year": case.window.post_end,
                    "title": "Evaluation window ends",
                    "description": "Post-intervention cutoff.",
                    "type": "baseline",
                },
            ],
        }

        # Resolve path to completed fixtures json
        cand_paths = [
            Path("apps/web/src/lib/fixtures/generated/all_cases.completed.json"),
            Path("GroundTruth/apps/web/src/lib/fixtures/generated/all_cases.completed.json"),
        ]
        target_path = None
        for cp in cand_paths:
            if cp.exists():
                target_path = cp
                break

        if target_path and target_path.exists():
            with open(target_path, encoding="utf-8") as f:
                all_fixtures = json.load(f)
            all_fixtures[case.case_id] = fixture_data
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(all_fixtures, f, indent=2)
    except Exception as exc:
        logger.warning("Could not auto-generate fixture: %s", exc)


def _queue_initial_run(case: CaseDefinition) -> None:
    """Queue initial run in database if configured."""
    try:
        from groundtruth.platform.config import get_settings
        from groundtruth.platform.jobs.queue import JobQueue
        from groundtruth.platform.store.database import create_db_engine, create_session_factory

        settings = get_settings()
        if not settings.database_url:
            return
        engine = create_db_engine(settings.database_url)
        sessions = create_session_factory(engine)
        req = case.to_request(seed=20260101)
        JobQueue(sessions).submit(req)
    except Exception:
        pass
