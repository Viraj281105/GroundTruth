# Project boundaries

GeoJSON boundary geometry for each case, sourced from registry project
documents or official shapefiles. A boundary is never redrawn by hand: a
hand-drawn boundary changes the estimate and cannot be audited by anyone else.

| Case | Boundary | Source | Status |
| --- | --- | --- | --- |
| `kariba-redd` | `kariba-redd.geojson` | Verra VCS 902, approved "Project Boundary (KML File)" (`_KML_902.kml`) | Obtained 2026-09-20, **area unreconciled** |
| `southern-cardamom-redd` | — | Verra VCS 1748 | Not obtained |
| `mikoko-pamoja` | — | Plan Vivo registry | Not obtained |

## What ships with a boundary

Three files, so that a reviewer can check the chain rather than trust it:

- `<case>.source.<ext>` — the registry document exactly as downloaded, byte for
  byte, with its hash recorded.
- `<case>.geojson` — the same geometry re-encoded for the pipeline. Any change
  made during re-encoding is listed in the provenance file and must not alter
  the point set.
- `<case>.provenance.json` — where it came from, when, what was checked, what
  failed and what remains unverified.

## Kariba: the area does not reconcile

The registry's own boundary document covers ~1,072,667 ha. The registry's area
field for the same project says 747,801 ha. That is a 43% gap, well past the
~10% tolerance in #2, and it is recorded rather than resolved — no figure has
been adjusted and no polygon has been trimmed to make them agree. A project-area
versus project-zone distinction is the likely explanation and is unconfirmed.

Until it is settled the boundary should not be used to derive the donor area
band, because under
[ADR-011](../../docs/decisions/ADR-011-unit-of-analysis.md) the treated unit's
eligible area is what sets that band.
