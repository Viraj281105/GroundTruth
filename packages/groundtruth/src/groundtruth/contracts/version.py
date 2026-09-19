"""Contract versioning.

The contract is the boundary between the analytical engine (Viraj) and the
platform (Bhumi). Either side may be rewritten freely behind it; neither may
change it unilaterally.

Semantics, standard semver:

- **major** — a breaking change. A field is removed or renamed, a type changes,
  or an existing value gains a new meaning. Requires both owners to agree and a
  migration for stored bundles.
- **minor** — an additive change. A new optional field, a new enum member that
  older consumers can ignore. Safe for the engine to ship ahead of the platform.
- **patch** — documentation or validation tightening with no shape change.

Stored evidence records the contract version it was produced under, so a bundle
written months ago can still be read and rendered correctly.
"""

from __future__ import annotations

CONTRACT_VERSION = "1.0.0"
"""Version of the engine/platform contract defined in this package."""

MIN_SUPPORTED_CONTRACT_VERSION = "1.0.0"
"""Oldest stored-bundle contract version the platform can still read."""


def parse_version(version: str) -> tuple[int, int, int]:
    """Parse a semver string into a comparable tuple."""
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"not a semantic version: {version!r}")
    try:
        major, minor, patch = (int(p) for p in parts)
    except ValueError as exc:
        raise ValueError(f"not a semantic version: {version!r}") from exc
    return major, minor, patch


def is_compatible(produced_under: str, consumer: str = CONTRACT_VERSION) -> bool:
    """True if a bundle produced under one version can be read by a consumer.

    Compatible when the major versions match and the consumer is not older than
    the producer at the minor level. A consumer may read bundles written by an
    *older* minor version, because minor changes are additive.
    """
    p_major, p_minor, _ = parse_version(produced_under)
    c_major, c_minor, _ = parse_version(consumer)
    return p_major == c_major and p_minor <= c_minor
