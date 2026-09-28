# Project boundaries

GeoJSON boundary geometry for each case, sourced from registry project
documents or official shapefiles. A boundary is never redrawn by hand: a
hand-drawn boundary changes the estimate and cannot be audited by anyone else.

| Case | Boundary | Source | Status |
| --- | --- | --- | --- |
| `kariba-redd` | `kariba-redd.geojson` | Verra VCS 902, approved "Project Boundary (KML File)" (`_KML_902.kml`) | Obtained 2026-09-20, area reconciled to 0.5% |
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

## Kariba: three area figures, three different things

The apparent 43% discrepancy was a comparison between a boundary area and a
forest area. The project's own documentation settles it.

| Figure | What it is | Source |
| --- | --- | --- |
| **1,077,930 ha** | The four Rural District Council parcels — what the geometry delineates | Project description p98: "the entire boundaries of the RDCs of 1'077'930 ha". The file's own area attributes sum to 1,077,930.24 ha |
| **784,987 ha** | The *forested* portion (woodland + open woodland at project start) inside those parcels — the VCS accounting area | Project description p4 and p7 Table 1; repeated by the 2013 validation report, the 2020 verification report and the 2022 monitoring report |
| **747,801 ha** | Unexplained. The registry page's "Acres/Hectares" field | Appears in none of the eleven project documents searched |

Our geodesic union of the geometry is 1,072,638 ha — 0.49% below the documented
boundary figure, which is the expected size of a difference between an
ellipsoidal computation and one done in a projected CRS. The forest share
implied by the two documented figures is 72.8%, and the project description
independently quotes 27% for the non-forest remainder.

Nothing was trimmed, scaled or dissolved to produce that agreement. The
registry field is recorded and not used.

**Why this matters downstream.** Under
[ADR-011](../../docs/decisions/ADR-011-unit-of-analysis.md) the treated unit is
the registry boundary intersected with a Hansen-derived baseline-forest mask.
The boundary parcels are the correct input, and the forest extraction happens
from independent data — so the eligible area the pipeline computes becomes an
independent check on the project's own 784,987 ha claim rather than an echo of
it.

## Known geometry defect, left as delivered

Parts 1 and 5 — the Binga and Nyaminyami parcels, which the project description
says share a border — overlap by 0.2886 km² (0.0027% of the total). It is a
digitising sliver: 29 vertices of one fall inside the other, with no shared
vertices. All nine other pairs are disjoint. Area must be taken on the union,
and any zonal computation must dissolve the parts first or the sliver is
counted twice.
