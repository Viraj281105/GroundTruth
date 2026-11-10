# Uploading gROADS v1 to Earth Engine

gROADS v1 (CIESIN, 1980–2010) is the agreed road layer for `road_distance_km` (V1, agreed
with Viraj (C4), 2026-11-05). It is not in the Earth Engine catalog, so it has to be
uploaded as an asset in our own Cloud project and pinned by **asset id, source file
sha256 and upload date**.

Do this once your Earth Engine account and project work
(see the Earth Engine setup in [`sources.md`](sources.md), "Credentials").

## Steps

1. **Download the source file.** Go to the dataset's page,
   <https://doi.org/10.7927/H4VD6WCT>, and download the global shapefile. NASA SEDAC
   needs a free Earthdata login. Check its documentation for redistribution limits: a
   private asset in our own project is not redistribution, but publishing it could be.

2. **Record the file's hash** before unpacking it, in PowerShell:
   ```powershell
   (Get-FileHash "$HOME\Downloads\<downloaded-file>.zip" -Algorithm SHA256).Hash.ToLower()
   ```
   Keep the 64-character result: it is `road_source_sha256`.

3. **Upload it as a table asset.** Open <https://code.earthengine.google.com>, go to the
   **Assets** tab, then **New → Shape files**.
   - Select the `.shp`, `.dbf`, `.shx` and `.prj` files (or the `.zip`).
   - Set the asset id to `projects/<your-project-id>/assets/groads_v1`.
   - Click **Upload**. The **Tasks** tab shows progress. A global road layer can take a
     long time.

4. **Let the service account read it.** On the asset, click **Share**, and add the service
   account's email address with **Reader** access.

5. **Fill in the three pinned settings** in `cases/run_parameters/kariba-redd.yaml`:
   ```yaml
   road_source: groads-v1
   road_asset: projects/<your-project-id>/assets/groads_v1
   road_source_sha256: <the 64-character hash from step 2>
   road_upload_date: YYYY-MM-DD   # the day the upload task finished
   ```

6. **Commit that file.** Never commit the shapefile or the key.

`road_distance_scale_m` and `road_search_radius_km` in the same file are separate open
questions for Viraj, not part of the upload.

## What the pin records

The `DatasetRef` for roads becomes:

```
dataset_id: groads-v1
version:    v1+sha256:<hash>;uploaded=<date>;ref=1980-2010
asset:      projects/<your-project-id>/assets/groads_v1
```

The version goes into the unit-set manifest and into `spec_hash`. Re-uploading a different
file changes the hash, so results cached under the old file are not reused.

## If the upload proves impossible

Viraj agreed one fallback: **current OpenStreetMap roads, treated as a time-invariant
access proxy.** It is never used silently. To use it:

- set `road_source: osm-current`, with an uploaded OSM extract as the asset;
- give the reason in `road_fallback_reason` (the script refuses without one);
- record the departure in [`docs/science/limitations.md`](../science/limitations.md).

Present-day roads are post-treatment, which is the error #23 exists to avoid, so this is
a recorded weakness rather than an equivalent choice.
