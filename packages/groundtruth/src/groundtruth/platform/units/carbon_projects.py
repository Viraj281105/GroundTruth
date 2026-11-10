"""The committed registered-carbon-projects snapshot (B3).

ADR-011: *which registered projects are known is a pinned fact, not a search.* The
snapshot, its download date and the resulting list of excluded districts are
committed before the pool is generated. Generation refuses without this file, and
this repository does not ship one: it is real data to be obtained, not something to
fill with a plausible value (R6). ``cases/carbon_projects/README.md`` documents the
exact format.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from groundtruth.contracts.errors import DataUnavailableError
from groundtruth.platform.config import REPO_ROOT
from groundtruth.platform.datasets.ee_mask import geometry_file_fingerprint
from groundtruth.platform.datasets.resilience import PermanentError
from groundtruth.platform.units.spec import UNIT_ID_PREFIX

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_UNIT_ID = re.compile(rf"^{UNIT_ID_PREFIX}:\d+$")


@dataclass(frozen=True, slots=True)
class CarbonProject:
    """One registered project, with its geometry where one exists."""

    project_id: str
    name: str
    geometry_path: str | None


@dataclass(frozen=True, slots=True)
class CarbonProjectSnapshot:
    """A pinned registry snapshot, as committed."""

    path: Path
    content_sha256: str
    snapshot_date: str
    source_uri: str
    source_file_sha256: str
    projects: tuple[CarbonProject, ...]
    excluded_districts: tuple[str, ...]

    def recipe_entries(self, *, exclude: str | None = None) -> list[dict[str, str]]:
        """Projects with geometry, as a mask recipe holds them: path and hash.

        Args:
            exclude: The case under test, left out of the treated unit's subtraction.

        Raises:
            DataUnavailableError: if a named geometry file cannot be read.
        """
        entries = []
        for project in self.projects:
            if project.geometry_path is None or project.project_id == exclude:
                continue
            try:
                fingerprint = geometry_file_fingerprint(project.geometry_path)
            except PermanentError as exc:
                raise DataUnavailableError(str(exc)) from None
            entries.append({"path": project.geometry_path, "blake2b": fingerprint})
        return entries


def _text(raw: dict[str, Any], key: str, where: str) -> str:
    value = raw.get(key)
    if value is None or not str(value).strip():
        raise DataUnavailableError(f"{where}: {key!r} is required")
    return str(value).strip()


def load_carbon_snapshot(path: str | Path) -> CarbonProjectSnapshot:
    """Load and check the committed snapshot.

    Raises:
        DataUnavailableError: if the file is missing or malformed. Generation refuses,
            because an empty project list would look exactly like "no project here".
    """
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = REPO_ROOT / resolved
    if not resolved.is_file():
        raise DataUnavailableError(
            f"no carbon-project snapshot at {path}. ADR-011 requires the registry snapshot and "
            "the excluded districts to be committed before the pool is generated; see "
            "cases/carbon_projects/README.md for the format."
        )
    raw_bytes = resolved.read_bytes()
    where = str(path)
    try:
        raw = yaml.safe_load(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError):
        raise DataUnavailableError(f"{where} is not valid YAML") from None
    if not isinstance(raw, dict):
        raise DataUnavailableError(f"{where} must be a YAML mapping")

    snapshot_date = _text(raw, "snapshot_date", where)
    try:
        date.fromisoformat(snapshot_date)
    except ValueError:
        raise DataUnavailableError(f"{where}: snapshot_date must be YYYY-MM-DD") from None
    source_sha = _text(raw, "source_file_sha256", where).lower()
    if not _SHA256.fullmatch(source_sha):
        raise DataUnavailableError(f"{where}: source_file_sha256 must be 64 hex characters")

    entries = raw.get("projects")
    if not isinstance(entries, list) or not entries:
        raise DataUnavailableError(
            f"{where}: 'projects' must list the registered projects in the search region"
        )
    projects = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise DataUnavailableError(f"{where}: every project must be a mapping")
        geometry_path = entry.get("geometry_path")
        projects.append(
            CarbonProject(
                project_id=_text(entry, "project_id", where),
                name=_text(entry, "name", where),
                geometry_path=str(geometry_path) if geometry_path else None,
            )
        )

    excluded = []
    for entry in raw.get("excluded_districts") or []:
        unit_id = _text(entry, "unit_id", where) if isinstance(entry, dict) else ""
        if not _UNIT_ID.fullmatch(unit_id):
            raise DataUnavailableError(
                f"{where}: excluded_districts entries need a unit_id like {UNIT_ID_PREFIX}:40765"
            )
        _text(entry, "project_id", where)
        excluded.append(unit_id)

    return CarbonProjectSnapshot(
        path=resolved,
        content_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        snapshot_date=snapshot_date,
        source_uri=_text(raw, "source_uri", where),
        source_file_sha256=source_sha,
        projects=tuple(projects),
        excluded_districts=tuple(sorted(set(excluded))),
    )


__all__ = ["CarbonProject", "CarbonProjectSnapshot", "load_carbon_snapshot"]
