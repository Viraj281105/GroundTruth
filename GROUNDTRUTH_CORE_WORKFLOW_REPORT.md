# GroundTruth: Core Workflow Completion Report

Follows `GROUNDTRUTH_REMEDIATION_REPORT.md`. Branch `remediation/audit-fixes`, base `bdde7e1`.
Methodology and provenance: `docs/science/observation-ingestion-methodology.md`.

## 1. Verdict

**CONDITIONALLY READY for a supervised controlled pilot** of this workflow: create a project with its boundary,
upload documents, request real Sentinel-2 observations, get an honest basic-monitoring assessment, promote
and test claims, and export a traceable, ledger-sealed technical dossier.

**Not ready** for causal attribution, for an independent-audit pilot that relies on the numbers being
*validated*, or for public production. The reasons are in section 8, and the first two matter most:
the observation values are unvalidated against field data, and a user project has no climate series or
comparison areas, so attribution is always "Inconclusive".

What changed since the last report: a user project can now take real satellite observations end to end.
Before, it was stuck at Level 0 with no way forward.

## 2. What was delivered, by phase

| Phase | Result |
|---|---|
| 0 Preserve | Reviewed 79 modified / 56 untracked / 1 deleted files and the full diff: no secrets, one stray artefact (a test boundary written under `cases/boundaries/projects/`; removed, and the directory is now gitignored so user boundaries can never be committed). Migration chain 0007 to 0012 is linear. Work preserved on `remediation/audit-fixes` (commits `c8aa1a0`, `e84a727`, `1474f60`, `950671d`, plus the final one). |
| 3 Scientific integrity | All nine pre-existing failures resolved with no safeguard weakened (section 3). |
| 1 Observation ingestion | Implemented (section 4). Real run verified. |
| 2 Claims | Extracted statements can be reviewed, corrected, promoted and matched against evidence (section 5). |
| 4 PostgreSQL | Migrations, record preservation, ledger, isolation, documents verified on PostgreSQL 16 (section 6). One real PostgreSQL-only bug found and fixed. |
| 5 End to end | NGO, Funder and Auditor journeys run in a browser against the whole stack on PostgreSQL with a real worker and real satellite data (section 7). |

## 3. Phase 3: the nine failing tests

| Failure | Cause | Resolution |
|---|---|---|
| 4 x withdrawn-results guard | `docs/competition/demo-flow.md` documented a console line with the **withdrawn back-calculated figure** (`Claimed Carbon Quantity: 11,600,000 tCO2e`) and other numbers the system never prints (p = 0.0345, 29 placebos). `strategy.md` had lost its explicit withdrawal statement. Two other docs tripped the scan. | Replaced the invented output with an excerpt of the real CLI output; restored the withdrawal wording; reworded the two other lines. **The guard and its allowlist are unchanged.** |
| NDMI cache + Kariba assessment levels (3) | The tests assumed a three-year Kariba cache; the git-ignored cache was re-ingested and now holds one scene. | Tests now assert the outcome the assessment ladder requires for the data actually present (strict Level 0 with the right reasons for one scene; Level 2 behaviour if two or more years exist) and skip when the cache is absent. |
| Gemini narrator | The test let the developer `.env` (`GENAI_MODEL`) leak into `Settings`. | Isolated with `_env_file=None`. |
| Compose/Helm structure | Test expected `--migrate` on the worker; deployment uses a dedicated one-shot `migrate` service that API and worker wait for. | Test now asserts that real contract. |

## 4. Phase 1: observation ingestion

**Workflow.** A project owner (edit access) requests years, season window, cloud limit, indicators (NDVI always;
EVI, NDMI, NBR optional), grid size and scenes per year on the Earth observation tab. The request is validated
against the project's own boundary (years 2017 to now, at most 12; season within one calendar year; cloud 0 to
80 %; 20 to 500 m; at most 30 scenes and about 1.5 million grid cells; one active request per project) and queued.
A **worker process** claims it atomically, runs the existing Planetary Computer pipeline on the project's polygon
(multi-tile mosaic, SCL cloud/shadow mask, processing-baseline offset harmonisation, per-pixel annual median,
zonal mean), stores provenance-checked bundles keyed by the project id, and records the outcome.

* **Status is visible**: waiting / running / finished / partly finished / failed / cancelled, with times, plain
  reasons, a "no worker has picked this up" hint after 5 minutes, and cancel while queued. The page polls itself.
* **Honesty**: `succeeded` only if every requested year has a value and coverage of the project area is at least
  95 %. Otherwise `partial`, naming the years. A year with no usable data stays empty and is never estimated.
  A worker that dies is detected by heartbeat and the request is marked failed (nothing is left "running").
* **Provenance**: per-year scene ids, acquisition dates, tiles, coverage, `scenes_sha256`; per-bundle catalogue,
  grid, method, code version; an audit-ledger record (`observation.ingested`) holding the SHA-256 of each stored
  file. The stepper, readiness, assessment, observation charts and dossier pick the data up unchanged.
* **Operator path**: `groundtruth process-ingestions` runs queued requests synchronously.
* **Tests**: 31 ingestion tests (validation, queue, single-flight, permissions, tenant isolation, success, partial,
  empty, provider outage, unexpected error containment, stale sweep, concurrent claim, ledger, dossier).
  Migration 0011.

## 5. Phase 2: claims to verification

* A document's extracted statements are **candidates**. A person reviews one, may correct the wording, type,
  number, unit or period, and promotes it. Nothing is promoted automatically. Migration 0012.
* The server re-reads the stored document (checking its SHA-256) and verifies the character span is a statement
  the analyser really found; what it read is stored as **immutable `original_*` fields**. Corrections only change
  the tested fields, and the UI shows "the document said X, tested as Y". A claim can be withdrawn (soft delete).
* Each claim is matched against the evidence on file (`claims/evidence_match.py`, pure computation):
  area vs the boundary's geodesic area (+/-5 %); greenness change vs the observed change between two annual values
  (direction, size, coverage, and year-to-year spread disclosed); everything else is **insufficiently evidenced
  with the reason** (survival, trees planted, carbon, biodiversity, ecosystem recovery, causation, absolute wording).
* Outcomes: supported, partially supported, contradicted, insufficiently evidenced. "Supported" is worded as
  "consistent with the evidence"; "not enough evidence to test" is never worded as false. No project-level letter
  grade is produced for a real project's claims.
* **Tests**: 29 matcher tests and 21 API tests (promotion, source preservation, edit, duplicates, unreadable
  documents, tenant isolation, view-level denial, withdrawal, audit, dossier contents).

## 6. Phase 4: PostgreSQL acceptance

Isolated throwaway PostgreSQL 16 container on `127.0.0.1:55432` with an in-memory data directory; the main
database was never touched. Driver installed into a scratch directory, not the project venv.
A small opt-in harness (`tests/pgdb.py`, enabled by `GT_TEST_PG_ADMIN_URL`) gives every DB-backed test its own
fresh database, so the existing suites run unchanged on either database.

| Check | Result |
|---|---|
| Migrations 0001 to 0012 from empty | Success; at head |
| Roll back to 0008 and forward again | Success; new tables and columns removed then restored |
| Existing records across 0009 to 0012 | Users, organisations, projects, a legacy ledger row and its JSON preserved unchanged; the legacy row stays `legacy_unverifiable`; new records chain independently |
| DB-level guarantees | Ledger `(project, sequence)` uniqueness; ingestion status CHECK; cascade delete of documents/ingestions/claims; `SET NULL` on a deleted source document keeps the claim and its original text; timestamps keep their timezone; JSON round-trips |
| Ledger persistence, concurrent writes, tamper detection | Pass (24 ledger tests incl. 24 writes from 8 threads and 12 writes from 6 separate ledger objects racing on one project, modification, deletion, reordering) |
| Project and organisation isolation, document storage | Pass (whole tenancy suite) |

**Command and result**:
`GT_TEST_PG_ADMIN_URL=... pytest tests/tenancy tests/auth tests/test_audit_persistence.py tests/test_postgres_acceptance.py tests/claims` gives **536 passed**.

**A real PostgreSQL-only bug was found and fixed.** The audit-log pagination cursor was the raw ISO timestamp; on
PostgreSQL it contains `+00:00`, and a `+` in a query string decodes to a space, so the next-page request failed for
any client that passed the cursor through unencoded. SQLite's naive timestamps hid it. The cursor is now opaque
base64url, with a regression test.

Not covered: PostgreSQL versions other than 16, multi-process writers under production load (writers were threads
and separate ledger objects), and a managed/replicated deployment.

## 7. Phase 5: end-to-end acceptance (browser)

Whole stack on PostgreSQL: API, a real worker process with the ingestion poller, the production web build.
Own copies of the data and cases directories; no external keys.

**NGO (fresh account).** Registered, created an organisation (with inline validation), created a project with a
boundary near Pune, uploaded a document, deliberately entered a first year of 2010 (clear client-side rejection),
then requested 2021 to 2026, 15 Jan to 15 Mar, 20 % cloud. The worker ran against Planetary Computer and finished
`succeeded`: 6 years, 2 real scenes each (tile 43QCA), area covered 99.4 to 100 %. The stepper moved to 6 of 8,
the assessment to **Level 1 (basic monitoring), confidence Moderate**, attribution **Inconclusive**. Five extracted
statements were promoted through the UI. A dossier was downloaded and sealed.

**Outcomes of the claims** (written before the data was fetched): area supported (1,870 ha boundary vs 1,900 ha,
+1.6 %); greenness change consistent (+0.054 vs 0.05) with a disclosure that the record is not monotonic;
survival, carbon, biodiversity insufficiently evidenced.

**Reproducible and traceable** (checked outside the app):
* each stored bundle's SHA-256 equals the hash in the ledger record;
* three years of NDVI re-derived from the same scene ids by an independent script differ from the stored values by
  -0.003 to -0.006 (1.0 to 1.6 %), across processing baselines 2.12, 5.1 and 5.1x;
* the dossier holds the scene ids, claims with their source wording and outcomes, the request record and a manifest
  whose hashes all match; two downloads from unchanged state are byte-identical;
* altering a ledger record directly in PostgreSQL made the auditor's page show "Integrity check failed" naming the
  record; restoring it returned to verified with the **same ledger root**.

**Funder (view grant, via the NGO's Sharing page).** Reads claims, ingestion status, ledger and the document list;
no edit controls; server refuses with 403 an ingestion request, claim promotion, upload and the technical dossier;
other organisations' projects return 404.
**Auditor (audit grant).** Sees full per-year provenance in the UI, exports the technical dossier, verifies the
ledger and a downloaded file, sees no request form.

**Defects the end-to-end run found, all fixed**: the stepper marked "Reports" done because an observation ingestion
sits in the same ledger; a failing "Portfolio grade F" for claims satellites cannot test; raw UUIDs as claim headings;
the series source named a Google Earth Engine collection instead of Planetary Computer's `sentinel-2-l2a`; the
dossier omitted the claims and the request record; failed ingestions were audited with an invalid outcome value;
and a greenness-change match did not disclose year-to-year variation. Each has a test.

## 8. Remaining limitations (read these)

1. **Values are unvalidated.** Agreement with an independent reimplementation shows the code does what it says,
   not that NDVI is right for a site. No field or reference-product validation was done.
2. **No attribution for user projects.** There is no climate ingestion (CHIRPS is staged for Kariba only) and no
   comparison-area series, so Level 2 and any causal statement are unavailable. Sentinel-2 L2A reaches back only to
   2017, so a project that started in 2021 cannot reach the five pre-treatment years the readiness check requires.
3. **Narrow observation scope**: Sentinel-2 only; one season window per request; 100 m default grid; about 1.5 M
   cells maximum; a season crossing New Year needs two requests; one active request per project; no automatic retry.
4. **A worker must be running.** Without one, a request waits; the UI says so after 5 minutes.
5. **Area claims** are "supported" only as the drawn project area; restored extent is not shown.
6. Candidate guidance text from the extractor is generic (it can say "no observations attached" when a project has
   some). Scene ids appear in the dossier and API, not in the UI table.
7. **Ledger** is recomputable but not externally timestamped or signed; deleting only the newest record is
   detectable only from something that remembers it (a sealed report).
8. **Not verified**: live Groq path (no key); mobile layout; a manual accessibility pass; interactive form paths have
   no jsdom tests (they were exercised once in the browser); PostgreSQL under production load.
9. The seeded Kariba **demo claim suite** still has confident wording; it is under a simulation banner but should be
   rewritten or removed before any external demo. The worker's startup log still prints a stale "observed-data jobs
   fail" warning.
10. **Deployment**: the running Docker stack still serves the old code. Deploying needs a rebuild and migrations
    0009 to 0012 on the real database (the compose `migrate` service does this). Not done, per instructions.

## 9. Test results (exact)

| Check | Command | Result |
|---|---|---|
| Backend, full, SQLite | `pytest -p no:cacheprovider -W ignore` | **1686 passed, 0 failed, 9 skipped** (8 are the PostgreSQL-only tests) |
| Backend on PostgreSQL | `GT_TEST_PG_ADMIN_URL=... pytest tests/tenancy tests/auth tests/test_audit_persistence.py tests/test_postgres_acceptance.py tests/claims` | **536 passed** |
| Frontend | `npx vitest run` (apps/web) | **71 files, 708 tests passed** |
| Types / lint | `npx tsc --noEmit`, `npx next lint`, `ruff check`, `ruff format --check`, `mypy` | all clean (mypy: 193 files) |
| Generated types | `npm run check:api-types`, `check:fixture-fallback` | OK |
| Production build | `npx next build` | succeeds (one harmless CSS autoprefixer note) |

Previously 9 backend tests failed; all pass. No test was deleted or loosened to achieve this; where an expectation
was stale it was rewritten to assert the real contract (section 3).

## 10. Release readiness

| Dimension | Status |
|---|---|
| NGO workflow (project, boundary, documents, observations, basic assessment, claims, report) | CONDITIONALLY READY, supervised |
| Funder / auditor access and report workflow | CONDITIONALLY READY |
| Data integrity (ledger, hashes, tenancy) on PostgreSQL | READY for a pilot; no external anchor |
| Scientific validity of the observation values | NOT VERIFIED (unvalidated) |
| Causal attribution for user projects | NOT READY (not available) |
| Independent-audit pilot | NOT READY until values are validated at the pilot sites |
| Public production | NOT READY |

**Recommendation: controlled pilot (supervised real-project use)**, for documentation, observation and claim
screening only, with these conditions:
1. Deploy deliberately: rebuild, apply 0009 to 0012, run the worker, monitor it, back up the database.
2. Validate the observation values at each pilot site against field data or an independent product before any
   external claim relies on them.
3. Tell pilot users plainly (the product already does) that outputs are screening evidence, not verification,
   and not attribution.
4. Before an audit pilot: add a climate and comparison-area path (or scope attribution out), rewrite or remove the
   Kariba demo claim wording, verify the live Groq path, and do a manual accessibility and mobile pass.
5. Decide whether the ledger needs an external timestamp anchor for your audience.
