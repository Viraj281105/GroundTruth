"""Pinned Earth Engine datasets, and the sensor decisions agreed under C3.

**Owner: Bhumi.** This module is where a logical sensor becomes a concrete,
versioned :class:`~groundtruth.contracts.identifiers.DatasetRef` (ADR-009).

Earth Engine collections carry no version a client can request: a collection is
reprocessed in place. Two things make the pin real rather than a label:

1. **A snapshot date.** Only scenes whose ``system:version`` (the time Earth
   Engine last wrote the asset) is at or before :data:`SNAPSHOT_DATE` are used, so
   imagery reprocessed later cannot silently change a re-run. The date is a
   constant in code: moving it is a reviewed change, and because it is part of the
   dataset version it moves every request's ``spec_hash``.
2. **A scene fingerprint per year**, recorded in the cache and in provenance, so
   two runs can be shown to have used the same scenes, not just the same name.

Which sensor serves which year is methodology, not plumbing. The service accepts
only a sensor listed in :data:`AGREED_SENSORS`, each with the scope and date it
was agreed with the engine owner.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from groundtruth.contracts.identifiers import DatasetRef

PROVIDER = "google-earth-engine"

SNAPSHOT_DATE = "2026-11-01"
"""Scenes written to Earth Engine after this date (00:00 UTC) are excluded."""

SNAPSHOT_MICROS = int(datetime(2026, 11, 1, tzinfo=UTC).timestamp() * 1_000_000)
""":data:`SNAPSHOT_DATE` in the unit of ``system:version``: microseconds since the epoch."""

PRODUCT_VERSIONS: dict[str, str] = {
    "landsat5": "C02-T1-L2",
    "landsat7": "C02-T1-L2",
    "landsat8": "C02-T1-L2",
    "landsat9": "C02-T1-L2",
    # The harmonized collection has no product version of its own; ADR-009 records
    # the snapshot date instead, and says so rather than implying a stronger pin.
    "sentinel2": "harmonized",
}
"""The provider's own product version, where it has one."""

DATASET_IDS: dict[str, str] = {
    "landsat5": "landsat5-c2-l2",
    "landsat7": "landsat7-c2-l2",
    "landsat8": "landsat8-c2-l2",
    "landsat9": "landsat9-c2-l2",
    "sentinel2": "sentinel2-sr-harmonized",
}

CATALOG_URL = "https://developers.google.com/earth-engine/datasets/catalog/"


@dataclass(frozen=True)
class SensorAgreement:
    """A sensor the engine owner agreed may serve a span of years (C3)."""

    sensor: str
    first_year: int
    last_year: int
    agreed: str
    rationale: str

    def covers(self, year: int) -> bool:
        """True if the agreement covers ``year``."""
        return self.first_year <= year <= self.last_year

    def describe(self) -> str:
        """One line for provenance and error messages."""
        return f"{self.sensor} for {self.first_year}-{self.last_year}, {self.agreed}"


AGREED_SENSORS: dict[str, SensorAgreement] = {
    "landsat7": SensorAgreement(
        sensor="landsat7",
        first_year=2001,
        last_year=2022,
        agreed="agreed with Viraj (C3), 2026-11-03",
        rationale=(
            "One sensor across the whole Kariba window (2001-2022), so the series has no "
            "sensor transition in it. Scenes after the 2003 scan-line-corrector failure have "
            "no-data stripes, which the mask removes; they lower clear-observation counts "
            "rather than bias values. A per-year sensor rule and cross-sensor calibration "
            "(#5) are future work."
        ),
    ),
}
"""The only sensors the observation service will reduce, and for which years."""

CLOUD_FILTER_DECISION = (
    "ObservationSpec.max_cloud_fraction is not applied: no scene is dropped for its cloud "
    "cover, and cloud is removed by the per-pixel masks in the engine's reduction spec only. "
    "Agreed with Viraj (C3), 2026-11-03."
)


def pinned_dataset(sensor: str, collection: str) -> DatasetRef:
    """The versioned reference for one sensor's collection at :data:`SNAPSHOT_DATE`.

    ``retrieved_at`` is left unset here; it belongs to a retrieval, and the
    service records it per year in provenance.
    """
    return DatasetRef(
        dataset_id=DATASET_IDS[sensor],
        version=f"{PRODUCT_VERSIONS[sensor]}@{SNAPSHOT_DATE}",
        provider=PROVIDER,
        asset=collection,
        source_uri=CATALOG_URL + collection.replace("/", "_"),
    )


__all__ = [
    "AGREED_SENSORS",
    "CLOUD_FILTER_DECISION",
    "PROVIDER",
    "SNAPSHOT_DATE",
    "SNAPSHOT_MICROS",
    "SensorAgreement",
    "pinned_dataset",
]
