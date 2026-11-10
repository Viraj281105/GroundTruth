# Registered carbon-project snapshots

**Status: NOT YET OBTAINED.** No snapshot is committed. The unit-set generation script
refuses to run without one, because an empty project list would look exactly like
"there are no other projects here", and those two statements are very different.

ADR-011: *which registered projects are known is a pinned fact, not a search.* The
consolidated registry snapshot, its download date and the list of excluded districts
are committed **before the pool is generated**. Deciding afterwards that a district
"probably contains a project" is exactly the discretion the ADR removes, in either
direction.

## The file you need to create

Create `cases/carbon_projects/kariba-redd.yaml`, then set
`carbon_project_snapshot: cases/carbon_projects/kariba-redd.yaml` in
`cases/run_parameters/kariba-redd.yaml`.

```yaml
# All four of these are required.
snapshot_date: "YYYY-MM-DD"        # the day the source file was downloaded
source_uri: "https://..."          # where it was downloaded from
source_file_sha256: "<64 hex>"     # sha256 of the downloaded file, unmodified

# Every registered project in the search region (ZWE, ZMB, MOZ, MWI, TZA).
# At least one entry is required, and Kariba itself must be listed.
projects:
  - project_id: "VCS 902"          # must match the case's registry_id to be excluded
    name: "Kariba REDD+ Project"   # from its own subtraction on the treated unit
    geometry_path: cases/boundaries/kariba-redd.geojson   # one Polygon or MultiPolygon
  - project_id: "..."
    name: "..."
    geometry_path: null            # no public geometry: see excluded_districts

# Districts excluded whole, because a project with no geometry falls inside them.
# "Inside" means the registry's own point location falls in the district, not a
# judgement about where a project probably is (ADR-011). May be empty, but only if
# that is true: list every project without geometry that has a known location.
excluded_districts:
  - unit_id: "gaul2015:12345"      # gaul2015:<ADM2_CODE>
    project_id: "..."
```

Geometry paths are relative to the repository root, and each must hold exactly one
Polygon or MultiPolygon.

## Where the data comes from

ADR-011 names the Berkeley Carbon Trading Project's consolidated database as the
source. Its own table warns that **public geometry is largely unavailable**, so most
projects will have `geometry_path: null`. Whether the database gives a usable point
location for each project has not been checked; if it does not, the registry page of
each project in the search region is the next place to look.

A project that nobody knows about still contaminates the pool undetected. ADR-011
records that as an accepted limitation, and this file does not remove it.
