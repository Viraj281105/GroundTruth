# GroundTruth — Remediation Report

> Superseded for current status by `GROUNDTRUTH_CORE_WORKFLOW_REPORT.md` (observation ingestion, claim promotion, PostgreSQL acceptance, end-to-end results). This report records the first remediation round.

Source: independent black-box audit of the running app (2026-11-09, `GroundTruth_Audit_Report.md`).
Base commit `bdde7e1` on branch `viraj`. **Nothing has been committed**; all changes are in the working tree.

## 1. Verdict

**Internal testing / supervised demonstration only. Not yet a controlled pilot for real projects.**

Everything the audit found that was *fabricated, broken or misleading* has been fixed and re-tested in a real browser. The product is now honest: an empty organization shows nothing invented, "sealed" means a real recomputable record, dead links and crashes are gone, and unavailable features say so.

What stops it being a pilot is not a defect but a **missing capability**: a user cannot get real satellite observations into a project from the app (only an operator CLI can, for configured reference cases). An NGO can create a project, upload a boundary and documents, and get an honest "not assessable", but cannot take it past Level 0. See §7.

## 2. Issues from the audit — outcome

| ID | Sev | Issue | Outcome | How verified |
|---|---|---|---|---|
| D1 | P0 | "Merkle root" was SHA-256 of empty input / placeholder patterns | **Fixed.** Ledger rewritten: real Merkle tree + hash chain over persisted records; reports bound to ledger by SHA-256 of the exact file | 24 ledger tests, 12 API tests, browser |
| D2 | P0 | Hardcoded Kariba results (24 claims, 58.4%, 246k tCO₂e, "100% sealed") shown to empty orgs | **Fixed.** Assessments, Reports, Intelligence, Evidence Library rebuilt on real data with empty states | Browser: new org shows only empty states |
| D3 | P1 | Evidence Library crash (`.substring` of undefined) + hardcoded fallback list with fake hashes | **Fixed.** Root cause: view read fields the API never sent. Fallback list deleted | Browser |
| D4 | P1 | Verification Workbench HTTP 500 for new projects | **Fixed.** Backend returned unscoped Kariba data and page fetched without cookies; now scoped, honest empty state | Browser, 92 backend tests |
| D5/D6 | P1 | All Download/Inspect links 404 | **Fixed.** Dead links removed; org Reports lists real projects and links to the project Reports tab, where the dossier download works | Browser |
| D7 | P1 | No document upload / ingestion controls | **Fixed (with a stated limit).** Upload, list, download, extract, delete, with honest status. Satellite ingestion is *not* available and the UI says so | Browser, 15 tests |
| D8 | P1 | Intelligence did nothing; hardcoded "184.2 ms" | **Fixed.** Real service, project-scoped, facts vs inferences separated, latency only if measured, honest "unavailable" | Browser (unavailable path), mocked-provider tests. **Live Groq NOT VERIFIED** |
| D9 | P2 | Registry called Sentinel-2/GEDI/ALOS "operational" | **Fixed.** Truthful classification; 0 operational; consistent with `/health` | Browser, 20+ tests |
| D10 | P2 | Claims workbench found 1 of 4 claims, missed over-claim | **Fixed** for the audit sample (5 statements incl. over-claim + unrecognised sentences) | Browser, unit tests |
| D11 | P2 | Org pages leaked a tenant's project summary | **Fixed** (same change as D2) | Browser |
| D12 | P2 | Stepper labels/links didn't match tabs; asserted things not done | **Fixed.** 8 steps, each linked to a real page, status from real data | Browser |
| D13 | P2 | `/sign-in` 404; hidden org-create form | **Fixed** | Browser |
| D14 | P2 | Sidebar links had no accessible names | **Fixed** for shell/nav. A full accessibility audit was **not** done | Accessibility tree, tests |
| D15 | P3 | Tour reappeared on every load / Next unreliable | **Fixed** (see note) | Browser |
| D16 | P3 | Audit log actors as UUIDs | **Mostly fixed.** Actor email + humanised action; *resource* still shows a short UUID | Browser |
| D17 | P3 | Stale landing copy | **Fixed** | Tests |
| D18 | P3 | Jargon | **Partly fixed.** Dashboards/lens/landing done; project panels (`ClimatePanel`, `ReadinessChecklist`, …) still use NDVI/SPI wording | — |

Tour note: the "Next does nothing" report did not reproduce on the old build, so no root cause was confirmed. The tour was rebuilt (reducer-driven, persisted, keyboard-accessible) and verified in the browser: Next advances, Skip persists across a full reload.

Additional defects found and fixed during this work: unauthenticated `/benchmarks` (ran a compute suite for anyone) now requires sign-in; ledger response headers were hidden from browser scripts (CORS `expose_headers`); document extraction used the old extractor (now the same analyser as the public Claims page); `Observed data` label read as "has satellite data" (now "Real project (not simulated)"); the old ledger also invented a Kariba record for *any* project id and invented a fallback commit SHA.

## 3. What changed, by area

- **Audit ledger** (`platform/audit/ledger.py`, rewritten): domain-separated leaves over canonical JSON, odd nodes promoted (not duplicated), per-project hash chain (`sequence`, `prev_root_hash`), ORM-level append-only guard, retrying append for concurrent writers. Empty ledger reports `empty`; legacy rows report `legacy_unverifiable`. New endpoints: `GET /projects/{id}/ledger`, `POST …/ledger/verify-report`, `POST …/ledger/verify-reproducibility`, `GET /orgs/{slug}/reports`. The old unauthenticated global `/audit/ledger/*` routes are removed. A dossier download appends a `report.sealed` record containing the SHA-256 of the exact ZIP.
- **Claims** (`claims/statements.py`, `platform/projects/claim_gaps.py`, `api/claims.py`, `api/v2.py`): project-scoped structured claims; Kariba suite only for the seeded Kariba project and labelled synthetic; multi-statement extraction with verbatim spans, units, periods, over-claim flags, evidence gaps and unrecognised sentences. No confidence scores are produced.
- **Intelligence** (`platform/intelligence/*`): project-scoped, context from the project's own records and documents, guardrails drop ungrounded numbers/prohibited assertions, measured latency, `GET /intelligence/status`.
- **Documents** (`projects/documents.py`, `api/project_documents.py`, migration 0010): see §6.
- **Registry/health** (`datasets/evidence_registry.py`, `/health`): `ingestion_mode`, `validation_status`, `blocked_for_production_analysis`, nullable unmeasured quality/completeness, hashes read from real local artefacts; production guard wired into `earth_engine_access`.
- **Frontend**: org Assessments/Reports/Intelligence/Evidence Library, project stepper + Evidence tab (documents), Verification Workbench, Claims page, tour, shell a11y, org-creation form, audit-log display, loading/error/not-found routes.

## 4. Test results (exact commands and counts)

Run from the repo root with the project venv; the project's `addopts = -q` hides the summary line, so `-W ignore` and no `-q` were used where counts are quoted.

| Check | Command | Result |
|---|---|---|
| Backend, whole suite, final tree | `.venv/Scripts/python -m pytest -p no:cacheprovider -W ignore` | **1593 passed, 9 failed, 1 skipped** (9 min 11 s) |
| Same 9 tests on clean baseline `bdde7e1` | same tests, `git worktree` of `bdde7e1`, `PYTHONPATH` to its source | **same 9 fail** → pre-existing, not caused by this work |
| Backend, affected suites re-run after last edits | `pytest tests/tenancy tests/auth tests/claims tests/test_audit_persistence.py tests/test_cors.py tests/test_v2_api.py tests/test_openapi_snapshot.py tests/test_store_schema.py tests/test_dataset_truthfulness.py tests/test_rate_limiting.py tests/test_contract_boundary.py` | **580 passed, 2 failed** (both pre-existing, below) |
| Frontend, whole suite | `cd apps/web && npx vitest run` | **69 files, 644 tests passed** (baseline per AGENTS.md: 57 files, 542) |
| TypeScript | `npx tsc --noEmit` | 0 errors |
| Lint | `npx next lint` | no warnings or errors |
| API types in sync | `npm run check:api-types` | OK |
| Fixture-fallback guard | `npm run check:fixture-fallback` | OK |
| Production build | `npx next build` | succeeds (one harmless autoprefixer note in `projects.module.css`) |
| Python lint/format | `ruff check packages tests`, `ruff format --check` | clean |
| Types | `mypy` | no issues, 186 files |

**The 9 pre-existing failures** (identical on `bdde7e1`): four `test_scientific_integrity_regression.py::TestWithdrawnResults` (a tracked doc, `docs/science/validation.md`, mentions a withdrawn constant outside the test's allowlist), `test_climate_integration::…ndmi_values_and_provenance`, `test_gemini_narrator::…gemini_config` (`.env` sets a different model), `test_project_assessment` ×2 (Kariba assessment levels), `test_docker_compose_and_helm_chart_structure`. They were not touched, and not hidden. The four withdrawn-results tests concern fabricated-results documentation, so they deserve attention separately.

**Intermittent**: `tests/server-api.test.ts > replays a call once…` failed once in a full Vitest run executed while two full pytest suites were running; it passed in isolation and in two further full runs. Treated as load-sensitive timing; not reproduced.

**New tests**: 24 ledger integrity (`tests/test_audit_persistence.py`: empty, single, multiple, modification, deletion, reordering, replay into another project, ORM guard, restart, concurrent writers in one process and in separate ledgers, report binding, legacy rows), 12 ledger/report API (`tests/tenancy/test_ledger_api.py`), 15 documents, 17 intelligence, claims suites (92 incl. tenancy), registry truthfulness, CORS exposure, plus 12 new frontend test files.

## 5. Security regression results

All pass in the final runs: cross-tenant project/ledger/document/claims/intelligence access (404, same as unknown), report/dossier download isolation, view-level grantee denied dossier and upload (403, also confirmed in the browser), unauthenticated requests (401), login rate limiting (5×401 then 429), authorization dependency on every non-public route (`test_route_protection`), audit-event append-only, ledger tamper/delete/reorder detection.
Decisions: `/benchmarks` now requires sign-in. `/evidence-registry` is kept public **on purpose** (static reference metadata; a test asserts it holds no tenant data) and explicitly allowlisted with that rationale — change it if you prefer it signed-in.

## 6. Database migration notes

- **0009 `audit_hash_chain`**: adds `sequence`, `prev_root_hash`, `record_kind`, `hash_scheme` to `audit_records` and a unique index on `(project_id, sequence)`. Existing rows are kept (append-only) and reported as `legacy_unverifiable`; they were produced by the old implementation with placeholder hashes and must not be trusted.
- **0010 `project_documents`**: new table; files are stored via the existing blob store (`PROJECT_DOCUMENTS_DIR`, `PROJECT_DOCUMENT_MAX_BYTES`, default 10 MB).
- **Apply with** `python -m apps.worker.main --migrate --exit-when-idle` (migrations were exercised on SQLite in tests and the browser run; **not run against Postgres**).
- **Deployment**: the Docker stack currently on ports 3000/8000 still serves the **old** code. Nothing was rebuilt or restarted there. Run `docker compose up --build` to deploy these changes.

## 7. Remaining known limitations

1. **No in-app observation ingestion for user projects** (biggest gap). Satellite/climate series can only be ingested by an operator for configured cases. Consequently assessments for user projects stay at Level 0 / "inconclusive" and the "run an assessment" step cannot be completed by an NGO. The UI states this.
2. **Documents and claims are not linked in the workbench.** An uploaded document yields candidate statements (viewable, labelled "not verified"), but the Verification Workbench still says "no claims" until claims are submitted; it should offer to promote document candidates.
3. PDF/DOCX are not parsed (no parser installed); PDFs are stored with status `extraction_unsupported`.
4. **Live Groq path not verified** (no key; tested with a mocked provider and the "unavailable" path). Questions about *other* places/projects rely on the system prompt only.
5. The seeded Kariba **demo claim suite** contains confident wording ("Evidence Quality A (100/100)", "hash verified", "Sentinel-2 2021–2023 available") that is illustrative. It sits under a prominent SIMULATED DATA banner, but it is inconsistent with the registry (one 2023 scene) and with the project's Level 0. It should be rewritten or removed before any external demo.
6. The ledger detects alteration, deletion and reordering but is **not externally timestamped or signed**; deleting only the newest record is detectable only from a report that remembers it. Concurrency was tested with threads on SQLite, not on Postgres.
7. `/claims/structured` and the intelligence responses are open objects in the OpenAPI schema; the frontend normalises them at runtime (tested), named response models would be cleaner.
8. Wording: CHIRPS/NASA POWER read "Not validated" yet "Usable for production analysis" (usable as a covariate); audit-log *resource* column shows a short UUID; project panels still contain NDVI/SPI jargon.
9. Seeded Kariba shows `data_mode = observed` (real project record) while its claim suite is simulated; both are labelled, but a reader must read the banner to see the distinction.

## 8. Browser-based workflow verification

Run on isolated instances of the final code (`127.0.0.1:3100` web, `:8100` API, throwaway SQLite DB, no external keys); your Docker stack was not touched. Interactions used the real UI; file inputs were filled programmatically (the pane has no file chooser).

**NGO** — register (empty, weak, mismatched, valid) ✓ · create organization (inline validation, focus on error) ✓ · empty org: Dashboard/Assessments/Reports/Intelligence/Evidence Library show only honest empty states, no Kariba ✓ · create project with GeoJSON ✓ (persisted, survived an API restart) · stepper "2 of 8 done, next: Documents, Satellite: Not available" ✓ · upload `.txt` → "Text read, not verified", 5 candidate statements incl. over-claim ✓ · Verification Workbench loads (no 500), lists what's missing ✓ · dossier download → ledger record appears, "Ledger verified", 9-file ZIP incl. documents manifest ✓ · org Reports lists the sealed report ✓.
**Funder** (seeded demo account) — sees only the granted Kariba project, labelled Simulated; Assessments and claims page show the simulation banner ✓ · view level: dossier 403, upload 403, other org's project/reports 404 ✓ · Reports shows "Nothing sealed yet" before any download ✓. Not exercised: share-grant creation UI, evidence provenance drill-down on a real project.
**Auditor** (seeded demo account, audit level) — dossier download ✓ · ledger verified ✓ · "Check a downloaded report": genuine ZIP → "byte-identical… ledger intact"; one-byte-altered copy → rejected ✓ · audit log shows actor email and "Report downloaded" ✓. Not exercised: real-data provenance (none exists to inspect).
**Not verified**: mobile layout, member-invite UI, live Groq, Postgres.

## 9. Release-readiness (revised)

| Dimension | Before | Now |
|---|---|---|
| Truthfulness of UI | NOT READY | READY for what exists |
| Data integrity / audit ledger | NOT READY | CONDITIONALLY READY (SQLite-tested; no external anchor) |
| Core workflow completion (NGO) | NOT READY | NOT READY — blocked by no observation ingestion |
| Funder / auditor workflows | NOT READY | CONDITIONALLY READY for demo cases only |
| Onboarding / a11y | NOT READY | CONDITIONALLY READY (no full a11y audit) |
| Controlled pilot (real projects) | NOT READY | **NOT READY** |
| Independent-audit pilot | NOT READY | NOT READY |
| Public production | NOT READY | NOT READY |

**To advance to a controlled pilot:** (1) an in-app or operator-assisted observation-ingestion path for user boundaries, with its provenance recorded; (2) link document-extracted statements into the claims workbench; (3) rebuild/redeploy and run migrations 0009/0010 on the real database, then re-run the browser pass there; (4) verify the live Groq path with a real key; (5) rewrite or retire the Kariba demo claim wording; (6) run ledger concurrency tests on Postgres; (7) a human accessibility pass and a mobile pass; (8) decide the 4 pre-existing "withdrawn results" doc test failures.

## 10. Git state

Branch `viraj`, HEAD `bdde7e187dc8c809563048bb56b3c697526a502e` (unchanged — **no commits made**).
Working tree: **79 modified, 56 untracked (new), 1 deleted** (`ReportsPage.module.css`, unused after the Reports rewrite). Regenerated: `apps/web/src/lib/generated/openapi.json` and `schema.d.ts`. Two throwaway artifacts live outside the repo (scratchpad: baseline worktree, E2E DB) and are not part of the change.
