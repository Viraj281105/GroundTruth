# GroundTruth: remediation report (user-audit round)

Date: 2026-11-10. Replaces the earlier report of the same name, which is kept at `docs/audits/GROUNDTRUTH_REMEDIATION_REPORT_round1.md`.

## Where the work is

* Branch **`demo/user-audit-fixes`**, started from `remediation/audit-fixes` at `b013b71`.
* Commits on top of `b013b71`:
  * `f3b9948` fix: user-audit remediation (Docker ingestion, palette, case links, dossier, copy)
  * `8fb7102` Merge `origin/main` (15 commits, through PR #90) into the branch
  * `21fee19` fix(docker): ship `security-headers.mjs` in the web image
  * a final commit with the landing-page copy fix, the video tooling and the four reports (see `git log`)
* The branch is 0 commits behind `origin/main` and has not been pushed. `main` itself was not changed.
* Nothing on the original stack (`localhost:3000`, volume `groundtruth_pgdata`) was modified.

## What was fixed (root causes)

Issue ids refer to `GROUNDTRUTH_USER_AUDIT_REPORT.md`.

| ID | Fix | Files | Regression test |
|---|---|---|---|
| U-01 | API and worker share named volumes for uploaded boundaries, documents and ingested observations; the image creates those directories before dropping privileges so volumes inherit the app user's ownership | `docker-compose.yml`, `infrastructure/docker/backend.Dockerfile` | `tests/test_deployment_config.py` (4 tests) |
| U-02 | `ingest` extra (`pystac-client`, `planetary-computer`, `rasterio`) installed in the backend image, plus `libexpat1`; the build fails if the libraries cannot be imported | `packages/groundtruth/pyproject.toml`, `backend.Dockerfile` | same |
| U-03 | `security-headers.mjs` copied into the web image (bug present on `main`) | `infrastructure/docker/web.Dockerfile` | `test_the_web_image_ships_every_local_module_next_config_imports` |
| U-04 | Palette is organisation-aware: searches the organisation's projects with the visitor's session, offers only pages that exist inside the organisation, and tracks recent projects | `palette-core.ts`, `recent-core.ts`, `ShellOverlays.tsx`, `CommandPalette.tsx`, `OrgShell.tsx` | `tests/palette.test.ts` (+7) |
| U-05 | `/cases/<id>[/<page>]` resolves under the visitor's own organisation (session-aware route handler); old sub-pages map to tabs; the fixed Reference redirect is gone | `next.config.mjs`, `src/lib/legacy-case-redirect.ts`, `src/app/(legacy)/open-case/...` | `tests/legacy-case-redirect.test.ts` (6) |
| U-06 | Ingestion guidance reflects stored observations and the viewer's access level: only the owning organisation is told it can request data | `platform/projects/views.py` | `tests/tenancy/test_observation_ingestion.py` (+2) |
| U-07 | Dossier download refreshes the page so the new sealed record appears; file named after the project slug; sealing-record selection follows the current list | `ReportsView.tsx`, `dossier-download.ts`, `VerifyReportForm.tsx`, `ledger.model.ts` | `tests/dossier-download.test.ts` (7) |
| U-08 | "permanent sample plots" is no longer read as an absolute claim; a quantified biodiversity change is recognised and reported as unsupported | `claims/statements.py` | `tests/claims/test_statements.py` (+4) |
| U-09 | Season presets name their dates only; the hint explains that dry months differ by region | `observations.model.ts` | `tests/observations.test.tsx` |
| U-10 | Landing page, FAQ, "what works / not built", welcome tour, banner and the "0 real projects" card now describe the product as it is | `features/home/*`, `lib/tour-core.ts`, `lib/i18n.ts` | `tests/public-copy-and-redirects.test.ts`, `tests/panels/format.test.ts` |
| U-11 | Index values to four decimals (full value in the tooltip); guard identifiers moved into the tooltip | `panels/format.ts`, `IndexSeriesPanel.tsx`, `ClaimVerificationWorkbench.tsx` | `tests/panels/format.test.ts` |

Also done, not a defect fix: an isolated demo stack (`docker-compose.demo.yml`), Playwright user-journey scripts (`apps/web/e2e/demo/`), and the removal of one guarded figure from `GROUNDTRUTH_CORE_WORKFLOW_REPORT.md` that made `test_no_hardcoded_back_calculated_tco2e` fail.

## Merge with `origin/main`

Seven conflicts, all resolved without dropping either side's behaviour: `docker-compose.yml` (my volumes with main's metrics port, healthcheck note and fixed network name), `config.py`, `platform/api/app.py`, `platform/datasets/__init__.py` (both sides' imports and exports), `tests/test_infrastructure_and_security_qa.py` (main's stricter version), and two docs (`demo-flow.md` keeps the real CLI excerpt; `validation.md`). Rebuilding the stack after the merge found U-03.

## Not fixed (and why)

U-12 (HTTP 200 on a not-found page for an unknown project slug: needs a change to how the layout streams), U-13 (map legend says "donor regions" when none are drawn), U-14 (raw evidence reference tokens in recommendations) are cosmetic. U-15 (the reported Evidence Library 500) could not be reproduced. See the audit report. Remaining product limits are in section "Known limitations" below.

## Test results (all run on the merged branch)

| Check | Command | Result |
|---|---|---|
| Frontend unit | `npx vitest run` (apps/web) | **75 files, 746 tests passed** |
| Types / lint | `npx tsc --noEmit`, `npx next lint` | clean |
| Generated API types | `npm run check:api-types`, `npm run check:fixture-fallback` | OK, OK |
| Production build | `npx next build` | compiled (existing autoprefixer note only) |
| Backend lint / types | `ruff check packages tests`, `ruff format --check`, `mypy` | clean (313 files formatted; mypy: 209 source files) |
| Backend suite | `pytest -o addopts= -W ignore` (with `PROJ_DATA`/`PROJ_LIB` set to rasterio's data, see machine note) | **2132 passed, 15 skipped, 0 failed**, exit 0 (11 min 14 s) |
| Browser, all four personas | `e2e/demo/user-audit.mjs <persona>` | every sidebar page and project tab loads, no console errors or failed requests |
| Real workflow in the browser | `e2e/demo/prepare-demo.mjs` and the narrated recording | create, upload, extract, real Sentinel-2 ingestion (6 years), claims, sharing, dossier, ledger, auditor file check all completed |
| Tamper test | edit one `audit_records` row in the isolated database | status `failed`; restored: `verified`, same ledger root |
| Dossier manifest | recompute SHA-256 of all 10 files outside the app | 10 of 10 match |
| Server permissions | direct API calls with funder and auditor sessions | funder: 403 on ingestion, claim, upload, dossier, grant; auditor: 403 except dossier 200; cross-tenant 404 |

Machine note: this computer has a user-level `PROJ_LIB` pointing at the PostGIS `proj.db`, which makes rasterio fail ("DATABASE.LAYOUT.VERSION.MINOR"). Two tests that call rasterio (`tests/data_access/test_generalization_non_kariba.py::test_kasigau_end_to_end_imagery_retrieval_and_reduction`, `test_planetary_computer_stac.py::test_live_planetary_computer_end_to_end_ingestion`) fail with that value and pass when `PROJ_DATA` and `PROJ_LIB` point at `rasterio/proj_data`. They were run that way. Not a code defect; no system setting was changed. Those two tests were skipped before rasterio was installed in the virtual environment.

## Startup commands

Original stack (unchanged behaviour): `docker compose up --build` (web `:3000`, API `:8000`). After this branch it needs `up --build` once, because the images and volumes changed (named volumes `project_boundaries`, `project_documents`, `processed_data`).

Isolated demo stack used for all testing and the recording:

```bash
docker compose -p gtdemo -f docker-compose.yml -f docker-compose.demo.yml up -d --build
# web http://localhost:3100   API http://localhost:8100/docs
# demo credentials (generated, never logged): .demo-secrets/demo-passwords.tsv   (git-ignored)
# reset to a clean seed:  docker compose -p gtdemo -f docker-compose.yml -f docker-compose.demo.yml down -v
```

Demo accounts (`ngo@`, `funder@`, `auditor@`, `government@demo.groundtruth.local`) are seeded by the one-shot `migrate` service because `SEED_DEMO=true`. This is the compose default; a real deployment must set `SEED_DEMO=false`.

Build the demo project through the browser (about two minutes, real Sentinel-2 fetch): `cd apps/web && AUDIT_PASSWORDS_FILE=../../.demo-secrets/demo-passwords.tsv node e2e/demo/prepare-demo.mjs`. Recording and editing commands are in `VIDEO_PRODUCTION_PREFLIGHT_REPORT.md`.

## Demo environment details

Docker Compose project `gtdemo`; Postgres 16 (volume `gtdemo_pgdata`), migrations to `0012`; API, worker and web built from this branch; Chrome (Playwright 1.65.0) 1920x1080; Sentinel-2 L2A from Microsoft Planetary Computer, tile 43QCA.

## Known limitations

1. The satellite values are real measurements but **not validated** against field data or a reference product.
2. A project that started in 2021 cannot have five pre-treatment years from Sentinel-2 (archive starts 2017), and there is no climate or comparison-area ingestion for user projects, so attribution is unavailable and says so.
3. Observation scope is narrow: Sentinel-2 only, one season window per request, one active request per project.
4. The ledger is recomputable but not externally timestamped or signed.
5. The optional language-model assistant (Groq) was not tested: no key.
6. Mobile layout and a manual accessibility pass were not done.
7. The Evidence Library 500 reported on the original stack was not reproduced and is unexplained.
8. The video narration uses a synthetic Windows voice (no neural voice reachable).
9. Seeded Kariba reference data is not used in the video; the demonstration project's boundary and design note are written for the demo and are not a registered project.

## Output locations

* Video: `D:\Hackathons\PCCOEIGC\GroundTruth\GROUNDTRUTH_DEMO_VIDEO.mp4` (plus `.srt`). Large, left untracked on purpose.
* Reports: `GROUNDTRUTH_USER_AUDIT_REPORT.md`, `GROUNDTRUTH_REMEDIATION_REPORT.md`, `VIDEO_PRODUCTION_PREFLIGHT_REPORT.md`, `GROUNDTRUTH_DEMO_NARRATION.md` in the repository root.
