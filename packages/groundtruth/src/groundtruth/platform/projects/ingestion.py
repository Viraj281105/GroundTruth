"""Satellite observation ingestion for user-defined project boundaries.

A user with edit access asks for observations (years, season window, cloud limit, indicators);
the request is validated against the project's stored boundary and queued. The worker claims it
and runs the existing Planetary Computer pipeline (``ingest_live_aoi_observations``) on the
project's own polygon. The resulting bundles are written to the same provenance-checked cache the
rest of the platform reads, keyed by the project's id, so readiness, assessment, the observation
charts and the dossier pick them up with no special cases and one project can never read
another's.

Honesty rules (R6):

* Nothing is invented. A year with no usable scene, or with the area covered below the threshold,
  stays empty (NaN) and is reported as such; it is never interpolated.
* ``succeeded`` is reserved for runs where every requested year has a value *and* the project
  area is covered above the threshold. Anything less is ``partial`` and says which years.
* Every outcome, including failure, is recorded with a plain-language reason and, for runs that
  stored data, an audit-ledger record naming the SHA-256 of each stored bundle.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from groundtruth.contracts.errors import DataUnavailableError, InsufficientDataError
from groundtruth.platform.audit.ledger import AuditLedger
from groundtruth.platform.config import get_settings
from groundtruth.platform.store.models import ObservationIngestionRow, ProjectRow

_log = logging.getLogger(__name__)

ALLOWED_INDICATORS: tuple[str, ...] = ("ndvi", "evi", "ndmi", "nbr")
DEFAULT_INDICATORS: tuple[str, ...] = ("ndvi", "evi")
FIRST_YEAR = 2017
"""Sentinel-2 Level-2A surface reflectance is not available before 2017."""
MAX_YEARS = 12
MAX_TOTAL_SCENES = 30
"""years x scenes-per-year: every chip is held in memory while a run reduces it."""
MAX_GRID_PIXELS = 1_500_000
MIN_RESOLUTION_M = 20.0
MAX_RESOLUTION_M = 500.0
COVERAGE_THRESHOLD_PCT = 95.0
"""A year whose valid-pixel share of the project area is below this has no value (NaN)."""
ACTIVE_STATUSES = ("queued", "running")

# error codes shown to the user and recorded on the row
E_INVALID = "invalid_request"
E_NO_BOUNDARY = "no_boundary"
E_BUSY = "ingestion_in_progress"
E_NO_SCENES = "no_scenes_found"
E_NO_USABLE = "no_usable_observations"
E_PROVIDER = "provider_unreachable"
E_PROCESSING = "processing_error"
E_INTERRUPTED = "interrupted"
E_DISABLED = "ingestion_disabled"


class IngestionRequestError(ValueError):
    """A request that cannot be accepted; ``code``/``hint`` are safe to show to the user."""

    def __init__(self, code: str, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


@dataclass(frozen=True)
class IngestionParams:
    start_year: int
    end_year: int
    window_start: str
    window_end: str
    max_cloud_cover: float
    indicators: tuple[str, ...]
    resolution_m: float
    max_scenes_per_year: int

    @property
    def years(self) -> list[int]:
        return list(range(self.start_year, self.end_year + 1))

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_year": self.start_year,
            "end_year": self.end_year,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "max_cloud_cover": self.max_cloud_cover,
            "indicators": list(self.indicators),
            "resolution_m": self.resolution_m,
            "max_scenes_per_year": self.max_scenes_per_year,
            "platform": "sentinel-2",
        }


def limits() -> dict[str, Any]:
    """The limits a request is checked against, shown to the user before they submit."""
    return {
        "first_year": FIRST_YEAR,
        "last_year": datetime.now(UTC).year,
        "max_years": MAX_YEARS,
        "max_total_scenes": MAX_TOTAL_SCENES,
        "min_resolution_m": MIN_RESOLUTION_M,
        "max_resolution_m": MAX_RESOLUTION_M,
        "max_grid_pixels": MAX_GRID_PIXELS,
        "coverage_threshold_pct": COVERAGE_THRESHOLD_PCT,
        "indicators": list(ALLOWED_INDICATORS),
        "default_indicators": list(DEFAULT_INDICATORS),
    }


def _parse_mmdd(value: Any, label: str) -> str:
    try:
        text = str(value)
        datetime.strptime(f"2000-{text}", "%Y-%m-%d")  # 2000 is a leap year: 02-29 is valid
        return text
    except ValueError:
        raise IngestionRequestError(
            E_INVALID, f"{label} must be a month and day like 06-01.", "Use the form MM-DD."
        ) from None


def estimate_grid_pixels(bounds: tuple[float, float, float, float], resolution_m: float) -> int:
    """Approximate number of grid cells covering a lon/lat bounding box at ``resolution_m``."""
    minx, miny, maxx, maxy = bounds
    mid_lat = math.radians((miny + maxy) / 2.0)
    width_m = max(maxx - minx, 0.0) * 111_320.0 * max(math.cos(mid_lat), 0.01)
    height_m = max(maxy - miny, 0.0) * 110_540.0
    return int(math.ceil(width_m / resolution_m) * math.ceil(height_m / resolution_m))


def validate_request(
    raw: dict[str, Any], bounds: tuple[float, float, float, float]
) -> IngestionParams:
    """Validate and normalise a request against the project's boundary extent.

    Raises:
        IngestionRequestError: with a code and a hint a non-specialist can act on.
    """
    this_year = datetime.now(UTC).year
    try:
        start = int(raw.get("start_year"))  # type: ignore[arg-type]
        end = int(raw.get("end_year", start))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise IngestionRequestError(
            E_INVALID, "Start and end year must be whole numbers.", None
        ) from None
    if start < FIRST_YEAR or end > this_year:
        raise IngestionRequestError(
            E_INVALID,
            f"Years must be between {FIRST_YEAR} and {this_year}.",
            "Sentinel-2 surface reflectance is not available before 2017.",
        )
    if end < start:
        raise IngestionRequestError(E_INVALID, "The end year is before the start year.", None)
    if end - start + 1 > MAX_YEARS:
        raise IngestionRequestError(
            E_INVALID,
            f"At most {MAX_YEARS} years can be requested at once.",
            "Request a shorter range, then request another range afterwards.",
        )

    w_start = _parse_mmdd(raw.get("window_start", "06-01"), "The season start")
    w_end = _parse_mmdd(raw.get("window_end", "06-30"), "The season end")
    if w_start > w_end:
        raise IngestionRequestError(
            E_INVALID,
            "The season must start before it ends within one calendar year.",
            "A season that crosses New Year must be requested as two separate windows.",
        )

    try:
        cloud = float(raw.get("max_cloud_cover", 25.0))
    except (TypeError, ValueError):
        raise IngestionRequestError(
            E_INVALID, "Maximum cloud cover must be a number.", None
        ) from None
    if not 0.0 <= cloud <= 80.0:
        raise IngestionRequestError(
            E_INVALID,
            "Maximum cloud cover must be between 0 and 80 percent.",
            "Cloudier scenes give unreliable vegetation values.",
        )

    inds_raw = raw.get("indicators") or list(DEFAULT_INDICATORS)
    inds = tuple(dict.fromkeys(str(i).lower() for i in inds_raw))
    bad = [i for i in inds if i not in ALLOWED_INDICATORS]
    if bad or not inds:
        raise IngestionRequestError(
            E_INVALID,
            f"Unsupported indicator(s): {', '.join(bad) or 'none given'}.",
            f"Choose from: {', '.join(ALLOWED_INDICATORS)}.",
        )
    if "ndvi" not in inds:
        inds = ("ndvi", *inds)  # the assessment is built on NDVI; it is always stored

    try:
        res = float(raw.get("resolution_m", 100.0))
        per_year = int(raw.get("max_scenes_per_year", 3))
    except (TypeError, ValueError):
        raise IngestionRequestError(
            E_INVALID, "Resolution and scenes per year must be numbers.", None
        ) from None
    if not MIN_RESOLUTION_M <= res <= MAX_RESOLUTION_M:
        raise IngestionRequestError(
            E_INVALID,
            f"Resolution must be between {MIN_RESOLUTION_M:g} and {MAX_RESOLUTION_M:g} metres.",
            None,
        )
    if per_year < 1:
        raise IngestionRequestError(E_INVALID, "Scenes per year must be at least 1.", None)
    n_years = end - start + 1
    if n_years * per_year > MAX_TOTAL_SCENES:
        raise IngestionRequestError(
            E_INVALID,
            f"{n_years} year(s) x {per_year} scene(s) is more than the {MAX_TOTAL_SCENES} "
            "scenes one request may process.",
            "Request fewer years, or fewer scenes per year.",
        )
    pixels = estimate_grid_pixels(bounds, res)
    if pixels > MAX_GRID_PIXELS:
        raise IngestionRequestError(
            E_INVALID,
            f"The project area is too large to process at {res:g} m resolution "
            f"(about {pixels:,} cells; the limit is {MAX_GRID_PIXELS:,}).",
            "Choose a coarser resolution, or ask an operator to run it.",
        )
    return IngestionParams(start, end, w_start, w_end, cloud, inds, res, per_year)


# --- boundary -----------------------------------------------------------------------------------


def read_boundary_geojson(project: ProjectRow) -> dict[str, Any] | None:
    """The stored boundary as a GeoJSON dict, or ``None`` when it cannot be read."""
    from groundtruth.platform.projects.readiness import _boundary_file

    if not project.boundary_path:
        return None
    file = _boundary_file(project.boundary_path)
    if file is None:
        return None
    try:
        doc = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def boundary_bounds(geojson: dict[str, Any]) -> tuple[float, float, float, float] | None:
    from shapely.geometry import shape
    from shapely.ops import unary_union

    try:
        if geojson.get("type") == "FeatureCollection":
            geoms = [shape(f["geometry"]) for f in geojson["features"]]
        elif geojson.get("type") == "Feature":
            geoms = [shape(geojson["geometry"])]
        else:
            geoms = [shape(geojson)]
        geom = unary_union(geoms)
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    if geom.is_empty:
        return None
    minx, miny, maxx, maxy = geom.bounds
    return float(minx), float(miny), float(maxx), float(maxy)


# --- queue --------------------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def enqueue(
    db: Session, project: ProjectRow, user_id: str | None, raw: dict[str, Any]
) -> ObservationIngestionRow:
    """Validate ``raw`` and queue it. Raises :class:`IngestionRequestError` with a clear reason."""
    if not get_settings().observation_ingestion_enabled:
        raise IngestionRequestError(
            E_DISABLED,
            "Observation ingestion is switched off on this server.",
            "Ask your administrator to enable OBSERVATION_INGESTION_ENABLED.",
        )
    geojson = read_boundary_geojson(project)
    if geojson is None:
        raise IngestionRequestError(
            E_NO_BOUNDARY,
            "This project has no readable boundary.",
            "Upload a boundary first; observations are extracted inside it.",
        )
    bounds = boundary_bounds(geojson)
    if bounds is None:
        raise IngestionRequestError(
            E_NO_BOUNDARY, "The project boundary is empty or invalid.", None
        )
    params = validate_request(raw, bounds)

    active = db.execute(
        sa.select(ObservationIngestionRow.id).where(
            ObservationIngestionRow.project_id == project.id,
            ObservationIngestionRow.status.in_(ACTIVE_STATUSES),
        )
    ).first()
    if active is not None:
        raise IngestionRequestError(
            E_BUSY,
            "An ingestion for this project is already queued or running.",
            "Wait for it to finish, or cancel it if it has not started.",
        )
    row = ObservationIngestionRow(
        id=str(uuid.uuid4()),
        project_id=project.id,
        requested_by=user_id,
        status="queued",
        params=params.to_dict(),
        status_detail="Waiting for the GroundTruth worker to pick this request up.",
        created_at=_now(),
    )
    db.add(row)
    db.flush()
    return row


def cancel_queued(db: Session, row: ObservationIngestionRow) -> bool:
    """Cancel a request that has not started. A running one cannot be interrupted safely."""
    if row.status != "queued":
        return False
    row.status = "cancelled"
    row.status_detail = "Cancelled before it started."
    row.finished_at = _now()
    return True


def claim_next(sessions: sessionmaker[Session], worker_id: str) -> str | None:
    """Atomically move the oldest queued request to ``running``; ``None`` when there is none."""
    with sessions() as db:
        candidates = (
            db.execute(
                sa.select(ObservationIngestionRow.id)
                .where(ObservationIngestionRow.status == "queued")
                .order_by(ObservationIngestionRow.created_at)
                .limit(5)
            )
            .scalars()
            .all()
        )
        for cid in candidates:
            now = _now()
            res = db.execute(
                sa.update(ObservationIngestionRow)
                .where(
                    ObservationIngestionRow.id == cid, ObservationIngestionRow.status == "queued"
                )
                .values(
                    status="running",
                    started_at=now,
                    heartbeat_at=now,
                    worker_id=worker_id,
                    status_detail="Searching for satellite scenes and processing them.",
                )
            )
            db.commit()
            if getattr(res, "rowcount", 0) == 1:
                return str(cid)
    return None


def sweep_stale(sessions: sessionmaker[Session], *, now: datetime | None = None) -> int:
    """Mark ``running`` requests with no heartbeat as failed (their worker died)."""
    now = now or _now()
    cutoff = now - timedelta(minutes=get_settings().ingestion_stale_minutes)
    with sessions() as db:
        rows = (
            db.execute(
                sa.select(ObservationIngestionRow).where(
                    ObservationIngestionRow.status == "running"
                )
            )
            .scalars()
            .all()
        )
        n = 0
        for row in rows:
            beat = row.heartbeat_at or row.started_at or row.created_at
            if beat.tzinfo is None:
                beat = beat.replace(tzinfo=UTC)
            if beat < cutoff:
                row.status = "failed"
                row.error_code = E_INTERRUPTED
                row.status_detail = (
                    "The worker stopped before this finished. Nothing was stored; request it again."
                )
                row.finished_at = now
                n += 1
        db.commit()
        return n


# --- running ------------------------------------------------------------------------------------


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarise(bundles: dict[str, Any], params: IngestionParams) -> dict[str, Any]:
    """What the pipeline measured, per year, with no value or coverage the pipeline did not report."""
    by_year: dict[int, dict[str, Any]] = {y: {"year": y} for y in params.years}
    for ind, bundle in bundles.items():
        for rec in bundle.records:
            slot = by_year.setdefault(rec.year, {"year": rec.year})
            has_value = not math.isnan(rec.value)
            if ind == "ndvi" or "n_scenes" not in slot:
                slot.update(
                    {
                        "n_scenes": rec.n_scenes,
                        "scene_ids": list(rec.scene_ids),
                        "acquisition_dates": list(rec.acquisition_dates),
                        "contributing_tiles": list(rec.contributing_tiles),
                        "aoi_coverage_pct": rec.aoi_coverage_pct,
                        "clear_pixel_fraction": rec.clear_pixel_fraction,
                        "is_spatially_complete": rec.is_spatially_complete,
                    }
                )
            slot.setdefault("values", {})[ind] = None if not has_value else float(rec.value)

    years_out: list[dict[str, Any]] = []
    complete: list[int] = []
    partial: list[int] = []
    empty: list[int] = []
    for y in params.years:
        slot = by_year[y]
        nd = (slot.get("values") or {}).get("ndvi")
        cov = slot.get("aoi_coverage_pct")
        if nd is None:
            state = "no_usable_data"
            empty.append(y)
        elif cov is not None and cov < COVERAGE_THRESHOLD_PCT:
            state = "partial_coverage"
            partial.append(y)
        else:
            state = "observed"
            complete.append(y)
        slot["state"] = state
        years_out.append(slot)

    first = next(iter(bundles.values()))
    prov = first.provenance
    limitations = [
        "Values are annual composites of cloud-masked scenes inside the project boundary, "
        "restricted to the requested season. They describe vegetation greenness, not tree "
        "survival, biodiversity or carbon.",
        "A change between years is an observation, not evidence that the project caused it.",
    ]
    if empty:
        limitations.append(
            "No usable observation could be produced for "
            + ", ".join(map(str, empty))
            + " (no scene met the cloud limit, or the area was not covered). Those years are left "
            "empty and are not estimated."
        )
    if partial:
        limitations.append(
            "Coverage of the project area is below "
            f"{COVERAGE_THRESHOLD_PCT:g}% for " + ", ".join(map(str, partial)) + "."
        )
    return {
        "catalog_url": first.catalog_url,
        "platform": "sentinel-2",
        "collection": "sentinel-2-l2a",
        "bbox": list(first.bbox),
        "years_requested": params.years,
        "years": years_out,
        "coverage": {
            "threshold_pct": COVERAGE_THRESHOLD_PCT,
            "complete_years": complete,
            "partial_years": partial,
            "years_without_data": empty,
        },
        "raster_grid": (prov.parameters or {}).get("raster_grid"),
        "code_version": prov.code_version,
        "method": prov.method,
        "limitations": limitations,
    }


def _classify_exception(exc: BaseException) -> tuple[str, str]:
    """(error_code, plain-language detail). Never includes secrets or stack traces."""
    if isinstance(exc, (DataUnavailableError, InsufficientDataError)):
        return E_NO_SCENES, (
            "No usable Sentinel-2 scenes were found for this area, years and cloud limit. "
            "Try a wider season window, a higher cloud limit, or other years. "
            f"({type(exc).__name__}: {str(exc)[:300]})"
        )
    name = type(exc).__name__
    module = type(exc).__module__
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)) or module.startswith(
        ("httpx", "requests", "urllib3", "pystac_client")
    ):
        return E_PROVIDER, (
            "The satellite data provider (Microsoft Planetary Computer) could not be reached or "
            f"did not answer in time. Nothing was stored; try again later. ({name})"
        )
    if isinstance(exc, ValueError):
        return E_INVALID, f"The request could not be processed: {str(exc)[:300]}"
    return E_PROCESSING, f"Processing failed unexpectedly ({name}). Nothing was stored."


def _heartbeat(sessions: sessionmaker[Session], row_id: str, stop: threading.Event) -> None:
    while not stop.wait(30.0):
        try:
            with sessions() as db:
                db.execute(
                    sa.update(ObservationIngestionRow)
                    .where(ObservationIngestionRow.id == row_id)
                    .values(heartbeat_at=_now())
                )
                db.commit()
        except Exception:  # a missed beat is recoverable; never kill the run for it
            _log.debug("ingestion heartbeat failed", exc_info=True)


def run_ingestion(
    sessions: sessionmaker[Session],
    ingestion_id: str,
    *,
    ingest_fn: Callable[..., dict[str, Any]] | None = None,
    data_dir: Path | None = None,
) -> str:
    """Run one claimed ingestion to completion and record its outcome. Returns the final status.

    Never raises: every failure is recorded on the row with a plain-language reason.
    """
    from groundtruth.data_access.aoi_pipeline import (
        AOIObservationCache,
        ingest_live_aoi_observations,
    )

    fn = ingest_fn or ingest_live_aoi_observations
    root = data_dir if data_dir is not None else get_settings().data_dir
    cache_dir = root / "processed" / "stac_cache"

    with sessions() as db:
        row = db.get(ObservationIngestionRow, ingestion_id)
        project = db.get(ProjectRow, row.project_id) if row else None
        if row is None or project is None:
            return "failed"
        params_raw = dict(row.params)
        project_id, org_id, requested_by = project.id, project.organization_id, row.requested_by
        geojson = read_boundary_geojson(project)
        boundary_hash = (
            f"sha256:{project.boundary_sha256}" if project.boundary_sha256 else "unrecorded"
        )

    def finish(
        status: str,
        *,
        code: str | None,
        detail: str,
        result: dict[str, Any] | None = None,
        ledger_id: str | None = None,
    ) -> str:
        with sessions() as db:
            row = db.get(ObservationIngestionRow, ingestion_id)
            if row is not None:
                row.status = status
                row.error_code = code
                row.status_detail = detail[:1000]
                row.result = result
                row.ledger_record_id = ledger_id
                row.finished_at = _now()
            from groundtruth.platform.audit.service import record_event

            record_event(
                db,
                action="observations.ingest",
                outcome="success" if status in ("succeeded", "partial") else "error",
                actor_user_id=requested_by,
                organization_id=org_id,
                resource_type="project",
                resource_id=project_id,
                details={"ingestion_id": ingestion_id, "status": status, "error_code": code},
            )
            db.commit()
        return status

    if geojson is None:
        return finish(
            "failed", code=E_NO_BOUNDARY, detail="The project's boundary could not be read."
        )
    bounds = boundary_bounds(geojson)
    if bounds is None:
        return finish(
            "failed", code=E_NO_BOUNDARY, detail="The project's boundary is empty or invalid."
        )
    try:
        params = validate_request(params_raw, bounds)
    except IngestionRequestError as exc:
        return finish("failed", code=exc.code, detail=exc.message)

    stop = threading.Event()
    beat = threading.Thread(target=_heartbeat, args=(sessions, ingestion_id, stop), daemon=True)
    beat.start()
    try:
        cache = AOIObservationCache(cache_dir)
        bundles = fn(
            unit_id=project_id,
            aoi_geojson=geojson,
            years=params.years,
            indicators=params.indicators,
            platform="sentinel-2",
            max_cloud_cover=params.max_cloud_cover,
            date_window=(params.window_start, params.window_end),
            max_scenes_per_year=params.max_scenes_per_year,
            tile_id=None,
            resolution_m=params.resolution_m,
            cache=cache,
            multi_tile=True,
            min_coverage_threshold=COVERAGE_THRESHOLD_PCT / 100.0,
        )
    except Exception as exc:
        stop.set()
        code, detail = _classify_exception(exc)
        _log.warning("observation ingestion %s failed: %s", ingestion_id, code, exc_info=True)
        return finish("failed", code=code, detail=detail)
    finally:
        stop.set()

    try:
        result = summarise(bundles, params)
        files: dict[str, dict[str, str]] = {}
        stored: dict[str, str] = {}
        for ind in bundles:
            path = cache.cache_path(project_id, ind)
            digest = _file_sha256(path)
            files[ind] = {"file": path.name, "sha256": digest}
            stored[ind] = f"sha256:{digest}"
        result["stored_bundles"] = files
        result["parameters"] = params.to_dict()
    except Exception as exc:
        code, detail = _classify_exception(exc)
        return finish("failed", code=code, detail=detail)

    cov = result["coverage"]
    if not cov["complete_years"] and not cov["partial_years"]:
        return finish(
            "failed",
            code=E_NO_USABLE,
            detail=(
                "Scenes were searched, but none produced a usable value inside the project "
                "boundary. Try a wider season window or a higher cloud limit."
            ),
            result=result,
        )
    status = (
        "succeeded" if not cov["partial_years"] and not cov["years_without_data"] else "partial"
    )

    ledger_id = None
    try:
        rec = AuditLedger(sessions).record_observation_ingest(
            project_id,
            boundary_geometry_hash=boundary_hash,
            parameters=params.to_dict(),
            stored_bundles=stored,
            findings={
                "ingestion_id": ingestion_id,
                "status": status,
                "coverage": cov,
                "years": [
                    {
                        k: y.get(k)
                        for k in ("year", "state", "n_scenes", "scene_ids", "aoi_coverage_pct")
                    }
                    for y in result["years"]
                ],
                "catalog_url": result["catalog_url"],
            },
            code_version=str(result.get("code_version") or "unknown"),
        )
        ledger_id = rec.record_id
    except Exception:
        _log.exception("could not record ingestion %s in the ledger", ingestion_id)

    if status == "succeeded":
        detail = (
            f"Stored {len(cov['complete_years'])} year(s) of observations for "
            f"{', '.join(params.indicators)}. Coverage of the project area is at or above "
            f"{COVERAGE_THRESHOLD_PCT:g}% in every year."
        )
    else:
        bits = []
        if cov["partial_years"]:
            bits.append("partial coverage in " + ", ".join(map(str, cov["partial_years"])))
        if cov["years_without_data"]:
            bits.append("no usable data in " + ", ".join(map(str, cov["years_without_data"])))
        detail = (
            "Stored what could be measured, but the result is incomplete: "
            + "; ".join(bits)
            + ". Empty years are not estimated."
        )
    if ledger_id is None:
        detail += " This run could not be recorded in the audit ledger."
    return finish(status, code=None, detail=detail, result=result, ledger_id=ledger_id)


def process_pending(
    sessions: sessionmaker[Session],
    worker_id: str,
    *,
    limit: int | None = None,
    ingest_fn: Callable[..., dict[str, Any]] | None = None,
    data_dir: Path | None = None,
) -> int:
    """Claim and run queued requests until none remain (or ``limit``). Returns how many ran."""
    sweep_stale(sessions)
    done = 0
    while limit is None or done < limit:
        rid = claim_next(sessions, worker_id)
        if rid is None:
            break
        run_ingestion(sessions, rid, ingest_fn=ingest_fn, data_dir=data_dir)
        done += 1
    return done


def report_item(row: ObservationIngestionRow) -> dict[str, Any]:
    """One ingestion request as recorded, for the technical dossier (JSON-safe)."""

    def iso(dt: datetime | None) -> str | None:
        return dt.isoformat() if dt else None

    return {
        "ingestion_id": row.id,
        "status": row.status,
        "status_detail": row.status_detail,
        "error_code": row.error_code,
        "parameters": row.params,
        "requested_at": iso(row.created_at),
        "started_at": iso(row.started_at),
        "finished_at": iso(row.finished_at),
        "result": row.result,
        "ledger_record_id": row.ledger_record_id,
    }


class IngestionPoller(threading.Thread):
    """Runs queued ingestions in the background of a worker process until stopped.

    One request runs at a time. A request in progress when :meth:`stop` is called is allowed to
    finish (the caller decides how long to wait); anything abandoned is later marked failed by the
    stale-heartbeat sweep, never left "running" forever.
    """

    def __init__(
        self, sessions: sessionmaker[Session], worker_id: str, poll_seconds: float
    ) -> None:
        super().__init__(name="observation-ingestion-poller", daemon=True)
        self._sessions = sessions
        self._worker_id = worker_id
        self._poll = poll_seconds
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                process_pending(self._sessions, self._worker_id, limit=1)
            except Exception:
                _log.exception("observation ingestion poller error")
            self._stop_event.wait(self._poll)


__all__ = [
    "ACTIVE_STATUSES",
    "ALLOWED_INDICATORS",
    "COVERAGE_THRESHOLD_PCT",
    "IngestionParams",
    "IngestionPoller",
    "IngestionRequestError",
    "cancel_queued",
    "claim_next",
    "enqueue",
    "limits",
    "process_pending",
    "run_ingestion",
    "summarise",
    "sweep_stale",
    "validate_request",
]
