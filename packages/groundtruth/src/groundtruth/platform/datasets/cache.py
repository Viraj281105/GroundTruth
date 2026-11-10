"""A disk cache for reduced Earth Engine years, addressed by what was reduced.

**Owner: Bhumi.**

ADR-009: cached products are addressed by dataset reference plus spatial and
temporal extent, so a hit is provably the same data rather than the same name.
Here the key is the pinned dataset (version and snapshot included), a hash of the
unit's geometry, the year, and the engine's reduction spec itself. Change any of
them — a new snapshot, an edited boundary, a methodology change — and the key
changes, so a stale entry is never read and nothing has to be invalidated by hand.

Each file stores the **full key**, not only its hash, and a read is a hit only
if the stored key equals the requested one field for field. A truncated, edited
or colliding file is a miss, logged and overwritten, never served.

Only successful reductions are written. A failure is not cached, so an outage
cannot be remembered as an answer.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from groundtruth.contracts.identifiers import spec_hash
from groundtruth.logging import get_logger

logger = get_logger("datasets.cache")

CACHE_FORMAT = 1
"""Bump when the stored value's shape changes; old entries then simply miss."""


def cache_key(**material: Any) -> dict[str, Any]:
    """The key material, normalised through JSON so a stored key compares equal."""
    key = {"format": CACHE_FORMAT, **material}
    normalised: dict[str, Any] = json.loads(json.dumps(key, sort_keys=True, default=str))
    return normalised


class ReductionCache:
    """One JSON file per key under ``directory``."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    def path_for(self, key: Mapping[str, Any]) -> Path:
        """Where the entry for ``key`` lives."""
        return self.directory / f"{spec_hash(dict(key))}.json"

    def get(self, key: Mapping[str, Any]) -> dict[str, Any] | None:
        """The stored value for ``key``, or ``None`` on a miss."""
        path = self.path_for(key)
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            logger.warning("unreadable cache entry; treated as a miss", extra={"path": str(path)})
            return None
        if not isinstance(entry, dict) or entry.get("key") != dict(key):
            logger.warning(
                "cache entry does not match its key; treated as a miss", extra={"path": str(path)}
            )
            return None
        value = entry.get("value")
        return value if isinstance(value, dict) else None

    def put(self, key: Mapping[str, Any], value: Mapping[str, Any]) -> Path:
        """Store ``value`` under ``key``, atomically: a reader sees the old file or the new."""
        path = self.path_for(key)
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"key": dict(key), "value": dict(value)}, sort_keys=True, indent=1)
        fd, tmp = tempfile.mkstemp(dir=self.directory, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return path


__all__ = ["CACHE_FORMAT", "ReductionCache", "cache_key"]
