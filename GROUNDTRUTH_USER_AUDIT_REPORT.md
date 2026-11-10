# GroundTruth: user audit report

Date: 2026-11-10. Branch `demo/user-audit-fixes` (see the remediation report for commits).
Method: the running product was used through a real Chrome browser (Playwright), signing in through the login form and reaching pages by clicking sidebar links, project lists and tabs, as a person does. Source code was read only to find the root cause of something already seen on screen.

## 1. What was running, and what was reproduced

| Item | Finding |
|---|---|
| Stack on `localhost:3000` / `:8000` | Docker Compose project `groundtruth`: `web`, `api`, `worker`, `postgres` up; `migrate` exited 0. Images built 2026-11-10 09:59 IST from `D:\Hackathons\PCCOEIGC\GroundTruth` (compose labels). Database at Alembic revision `0012`. The images carry no commit label, so the exact commit cannot be proven; migrations 0009 to 0012 being applied is consistent with release candidate `b013b71`. |
| Working tree | Branch `remediation/audit-fixes` at `b013b71`, clean at the start. Work moved to a new branch; nothing on the original stack was changed. |
| Access to the original stack | Not possible. Its demo accounts were created earlier and their passwords are not recoverable (the seed prints them once). An unauthenticated request to either reported URL answers 307 to `/login`. |
| Isolated stack used for all testing | `docker-compose.demo.yml`, project name `gtdemo`, web `:3100`, API `:8100`, its own database volume. Seeded fresh; credentials written to a git-ignored file. The original stack, its volume and its containers were never touched. |
| Reported failure 1: `/app/demo-government/projects/kariba/reports` is a 404 | Reproduced as "page not found", and the cause is a wrong URL: the project's slug is `kariba-redd`, not `kariba`. The API logs `GET /projects/kariba -> 404`. `/app/demo-government/projects/kariba-redd/reports` renders. (My request got HTTP 200 carrying the framework's not-found page, because the response is streamed after the layout has started; the browser still shows "not found".) Reaching Reports by clicking Projects, Kariba, Reports works for every role. The pre-2.0 link `/cases/kariba-redd/report` did end in a real 404 for non-Reference users: see U-05. |
| Reported failure 2: `/app/demo-government/evidence-library` is a 500 | **Not reproduced.** On the isolated stack, built from the same source, the page returns 200 and lists all ten dataset sources for all four roles; no 500 appears in the web or API logs. The original stack's API log also shows `GET /evidence-registry 200`. I could not sign in to the original stack to test it directly, so I cannot say what produced the user's 500. |

## 2. User journeys

All steps below were done in the browser against the isolated stack, with real Sentinel-2 data from Microsoft Planetary Computer.

**Restoration NGO.** Signed in; created a project by uploading a hand-drawn boundary near Pune (about 2,018 ha); uploaded a design note; read five extracted statements; requested satellite data for 2021 to 2026 (15 Jan to 15 Mar, at most 20 % cloud, two scenes a year). The worker finished in about a minute: six years observed, coverage at or above 95 % each year, real scene ids from tile 43QCA. Promoted all five statements to claims through the review form. Read the assessment (Level 1, evidence confidence Moderate, attribution Inconclusive), the verification page, and downloaded the dossier. Opened the evidence library.

**CSR team / funder** (view grant given through the NGO's Sharing page). Opened the shared project from the project list; read evidence, claims, ledger. No upload, request or dossier controls are shown. Direct API calls with the funder's session: request ingestion, add claim, upload, dossier export, share project all answered **403**; reading the ledger answered 200; another organisation's project list answered 404.

**Environmental auditor** (audit grant). Read per-year provenance with scene ids; downloaded the dossier; checked the downloaded file against the ledger record that sealed it ("The file is byte-identical to the sealed report and the ledger is intact"). Same direct-call probe: everything 403 except the dossier export (200) and ledger read (200).

**Independent checks.**
* The dossier's `manifest.json` lists 10 files; all 10 SHA-256 values were recomputed outside the app and match.
* One stored ledger record was altered directly in the isolated database: the ledger status changed from `verified` to `failed` ("Integrity check FAILED: the ledger was altered"); restoring the value returned `verified` with the same ledger root.
* The observed greenness change on screen (+0.051) matches the +0.0512 NDVI difference in the stored bundle.

## 3. Issue register

Severity: **High** = blocks or falsifies a demonstration workflow; **Medium** = misleading or broken but recoverable; **Low** = cosmetic.

| ID | Sev | Where / action | Expected | Actual | Root cause | Status |
|---|---|---|---|---|---|---|
| U-01 | High | Earth observation tab, request satellite data (Docker stack) | Worker fetches data for the uploaded boundary | Request ends `failed`, code `no_boundary`: "The project's boundary could not be read." | API and worker are separate containers with separate filesystems. The API wrote the boundary (and documents) to its own container; the worker read its own empty one. The reverse also holds: observations the worker stored would be invisible to the API. | Fixed: shared named volumes for the three runtime directories |
| U-02 | High | Same | Worker can read Sentinel-2 | Would have failed on first import | Backend image did not install `pystac-client`, `planetary-computer`, `rasterio`; rasterio also needs system `libexpat1`, absent from `python:slim` | Fixed: `ingest` extra, `libexpat1`, import check in the build |
| U-03 | High | Web container start after merging `main` | Web serves | Container exits: `ERR_MODULE_NOT_FOUND security-headers.mjs` | `main`'s `next.config.mjs` imports `security-headers.mjs`; the web image copied only `next.config.mjs`. Present on `main` itself. | Fixed + regression test |
| U-04 | Medium | Ctrl+K palette, as the tour tells a new user to | Search finds projects and pages | No results for any project; entries led to pre-2.0 pages; 401 errors in the console | The palette loaded `/cases` (needs no org, refused without the old session) and built links outside `/app/<org>/` | Fixed: organisation-scoped palette; recents work inside orgs |
| U-05 | High | Any `/cases/<id>` link (palette, bookmarks) | Opens the project | 404 "not found" for every organisation except Reference | `next.config.mjs` redirected all case links to `/app/reference/projects/...` | Fixed: session-aware redirect under the visitor's own organisation; old sub-pages mapped to tabs |
| U-06 | Medium | Evidence tab after a successful ingestion | States that observations exist | Kept saying "No satellite observations have been ingested for this project yet" and offered "Request satellite data" to funders and auditors, who get 403 | Message did not look at stored observations or the viewer's access level | Fixed |
| U-07 | Medium | Reports tab, Download dossier | New sealed record appears; saved file is named sensibly | Ledger on the page unchanged until a manual reload; file named after a UUID; the "check a file" form kept a stale record selection | No page refresh after the download sealed a record; selection fixed at first render | Fixed |
| U-08 | Medium | Claim extraction from the design note | Fair reading | "permanent sample plots" (a field-monitoring term) reported as an "Absolute conclusion" overclaim; "bird species richness increased by 20 percent" silently dropped | Overclaim pattern matched any "permanent"; biodiversity pattern needed a recovery verb | Fixed |
| U-09 | Medium | Season presets for a project in India | Neutral labels | "June (dry season in southern Africa)" and "January to March (rainy season in southern Africa)"; the second is the dry season in most of India | Region-specific wording in a global form | Fixed |
| U-10 | Medium | Public pages, welcome tour, footer | Statements true of the product | "No real project has been analysed", "no real satellite data today", "live satellite ingestion not built", while a created project ingests real Sentinel-2 | Copy predates the ingestion workflow | Fixed, with tests that fail if the old claims return |
| U-11 | Low | Observation table, verification page | Readable values | NDVI with sixteen digits; guard shown as `assert_not_index_to_carbon: ...` | Raw values and engine identifiers rendered | Fixed (four decimals, full value in tooltip; identifier in tooltip) |
| U-12 | Low | Unknown project slug | HTTP 404 | HTTP 200 carrying the not-found page | Streamed render | Not fixed |
| U-13 | Low | Dashboard map for a project without comparison areas | Legend matches the map | Legend reads "Dashed: donor regions" though none are drawn | Static legend | Not fixed |
| U-14 | Low | Dashboard recommendations | Evidence references readable | 24 raw `observation:<slug>:<indicator>:<year>` tokens listed | Raw references rendered | Not fixed |
| U-15 | Info | Evidence library 500 | n/a | Not reproduced | n/a | Open; cannot be investigated without access to the original stack |

An earlier version of my crawler flagged two "click failed" lines for a dashboard link that is only present on some layouts; the pages loaded and these are not application errors.

## 4. Things checked and found working

* Sign-in, sign-out, session handling, role-specific dashboards and landing pages for all four demo accounts.
* Every sidebar page and every project tab for all four roles, with no console errors and no failed requests (other than the defects above).
* Boundary validation messages on an empty New project form; boundary stored with a checksum; area computed on an equal-area projection (2,017.5 ha).
* Document upload, checksum, extraction, claim review form ("Adding a claim does not verify it"), withdraw/edit controls present.
* Claim outcomes are correct for the data: area "partly consistent" (boundary shows where, not how much restored); greenness "consistent" (+0.051 vs claimed +0.050); survival, carbon and biodiversity "not enough evidence to test", each with the reason; attribution "Inconclusive" with the missing evidence named.
* Dossier is deterministic: two downloads from unchanged state have identical report hashes.

## 5. Not covered

Field validation of any satellite value; the optional language-model assistant (no key configured); mobile layout and screen-reader behaviour (not tested by hand); load behaviour; the original `:3000` stack's data.
