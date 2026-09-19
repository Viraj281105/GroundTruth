# Ownership

GroundTruth is built by two people. This document says who owns what, where the
boundary between them sits, and what "done" means for each subsystem.

| | Owner | Share | Owns |
| --- | --- | --- | --- |
| **Analytical intelligence + user-facing product** | **Viraj** | ~40% | The scientific engine and the entire visual experience |
| **Platform + application engineering** | **Bhumi** | ~60% | Everything that makes GroundTruth a real, deployable application |

The split is deliberate. Viraj holds the two areas that decide whether the
project is *credible* (the science) and whether it *lands* (the demo). Bhumi
holds the larger surface: turning a computational module into a system that
runs, persists, scales, deploys and stays up.

---

## Architecture ownership

```
┌──────────────────────────────────────────────────────────────────────────┐
│  FRONTEND — Viraj                                                        │
│  maps · counterfactual charts · placebo plots · timeline · evidence      │
│  explorer · project pages · report view · demo polish                   │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │ generated TypeScript types
                                │ (from OpenAPI — Bhumi publishes)
┌───────────────────────────────▼──────────────────────────────────────────┐
│  PLATFORM — Bhumi                         src/groundtruth/platform/      │
│                                                                          │
│   api/        FastAPI, schemas, validation, errors, OpenAPI docs         │
│   cases/      project + case management, request translation             │
│   jobs/       analysis lifecycle, queueing, retries, cancellation        │
│   store/      evidence + provenance persistence, run history             │
│   storage/    artifacts, exports, generated reports                      │
│   datasets/   dataset registry, pinning, credentials, caching, retries   │
│   reports/    report pipeline, grounded GenAI narration                  │
│   config.py   environment and production configuration                   │
│                                                                          │
│   plus: deployment, CI/CD, monitoring, E2E tests, hardening              │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │
        ┌───────────────────────▼────────────────────────┐
        │  CONTRACT — shared, versioned, frozen          │
        │            src/groundtruth/contracts/          │
        │                                                │
        │  AnalysisRequest  ──────────────►              │
        │                   ◄──────────────  AnalysisResult
        │  DataAccess ports ◄──────────────              │
        │                                                │
        │  Evidence · Provenance · units · errors        │
        │  grounding rules · identifiers · versioning    │
        │                                                │
        │  Changes require BOTH owners to agree.         │
        └───────────────────────┬────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────────┐
│  ENGINE — Viraj                            src/groundtruth/engine/       │
│                                                                          │
│   observation/  spectral indices, cloud masking, compositing, zonal      │
│   features/     covariate engineering and transformations                │
│   matching/     donor-pool methodology, eligibility, balance             │
│   causal/       synthetic control, difference-in-differences             │
│   uncertainty/  placebo inference, leave-one-out, specification curve    │
│   assembler.py  evidence assembly and the verdict gate chain             │
│   run.py        run_analysis(request, data) -> result                    │
│                                                                          │
│   Pure computation. No files, no sockets, no credentials, no database.   │
└──────────────────────────────────────────────────────────────────────────┘
```

The boundary is enforced, not asserted. `tests/test_contract_boundary.py`
parses the AST of every module and fails the build if:

- `contracts/` imports from either side;
- `engine/` imports the platform, or performs any I/O;
- `platform/` imports anything from `engine/` beyond `run_analysis`,
  `describe_engine`, `engine_ref` and `ENGINE_VERSION`.

---

## Responsibility matrix

`A` = accountable (does the work, owns the decision) · `R` = reviews ·
`—` = not involved

| Area | Viraj | Bhumi |
| --- | :---: | :---: |
| **Scientific method** | | |
| Remote-sensing methodology (indices, masking, compositing) | **A** | — |
| Sensor cross-calibration and transition handling | **A** | R |
| Feature / covariate engineering | **A** | R |
| Donor-pool methodology and eligibility rules | **A** | — |
| Matching and balance diagnostics | **A** | — |
| Synthetic control and causal estimation | **A** | — |
| Placebo, robustness and specification curve | **A** | — |
| Uncertainty representation and intervals | **A** | R |
| Evidence assembly and the verdict gate chain | **A** | R |
| Biomass / carbon conversion methodology | **A** | — |
| Kariba validation and analytical review | **A** | R |
| Control-case behaviour (Cardamom, Mikoko Pamoja) | **A** | — |
| **User-facing product** | | |
| Design system and app shell | **A** | — |
| Dashboard architecture | **A** | R |
| Interactive maps | **A** | — |
| Counterfactual and placebo visualisations | **A** | — |
| Project timeline and evidence exploration | **A** | — |
| Evidence and result presentation | **A** | R |
| Report view | **A** | R |
| Demo experience and visual polish | **A** | R |
| **Platform** | | |
| Backend architecture | R | **A** |
| FastAPI layer, schemas, validation, errors | — | **A** |
| Database architecture, schemas, migrations | — | **A** |
| Project / case management | — | **A** |
| Analysis request lifecycle | R | **A** |
| Background job orchestration | — | **A** |
| Data ingestion services (auth, retries, caching) | R | **A** |
| Dataset registry, versioning and pinning | R | **A** |
| Storage and file management | — | **A** |
| Connecting external datasets to the engine ports | R | **A** |
| Integrating the analytical engine | R | **A** |
| Evidence and provenance persistence | R | **A** |
| Analysis-result APIs | R | **A** |
| Report-generation pipeline | R | **A** |
| Grounded GenAI integration | R | **A** |
| Evidence → report transformation | R | **A** |
| Backend validation and error handling | — | **A** |
| Frontend / backend integration | R | **A** |
| Deployment and production configuration | — | **A** |
| CI/CD | — | **A** |
| Integration and end-to-end testing | — | **A** |
| Monitoring and logging | — | **A** |
| API documentation | — | **A** |
| Production hardening | — | **A** |
| **Shared** | | |
| The contract (`src/groundtruth/contracts/`) | **A** | **A** |
| Scientific integrity rules in `CONTRIBUTING.md` | **A** | R |

---

## Coordination points

These are the only places where both owners must be in the room. Everything
else should proceed independently — that is the point of the boundary.

| # | Coordination point | Why | When |
| --- | --- | --- | --- |
| **C1** | **Any change to `contracts/`** | Both sides depend on it. A major bump needs a migration for stored bundles. | Whenever a schema field, enum member or error code is added or changed |
| **C2** | **DataAccess port semantics** | Viraj specifies what the engine needs; Bhumi decides where it comes from. Getting the split wrong here puts credentials in the engine or methodology in the platform. | Phase 2, before EO integration starts |
| **C3** | **Earth Engine reduction handover** | Viraj owns the band math, masking and compositing; Bhumi owns the client, auth, retries and caching. They meet at one function. | Phase 2, issues #1 and #14 |
| **C4** | **Covariate list and derivation** | Viraj decides which covariates matter and how they are transformed; Bhumi builds the services that fetch them. | Phase 2, issues #3 and #15 |
| **C5** | **Evidence → UI projection** | What the API returns must be what the UI can render without re-deriving anything. Settled once, in the OpenAPI schema. | Phase 3, before frontend work starts in earnest |
| **C6** | **Report structure** | Viraj specifies what a report must contain and how it must be caveated; Bhumi builds the pipeline and the GenAI integration. | Phase 3, issue #7 |
| **C7** | **Kariba result review** | No case may be promoted to `status: analysed` without both owners reviewing the run. | Phase 4, issue #4 |
| **C8** | **Demo rehearsal** | Viraj drives the demo; Bhumi must have the deployment stable and the failure paths understood. | Phase 5 |

Everything not on this list is a single-owner decision. If you find yourself
waiting on the other person outside these eight points, the boundary has
drifted and should be fixed rather than worked around.

---

## Definition of done

A subsystem is done when **every** line below is true. Not "mostly".

### Analytical engine (Viraj)

- [ ] `run_analysis` returns a typed `AnalysisResult` for every outcome,
      including refusal — it never raises for a domain failure
- [ ] Deterministic: the same `spec_hash` and seed produce identical numeric
      output, verified by a test
- [ ] No I/O: no filesystem, network, credential or database access, enforced
      by `test_contract_boundary.py`
- [ ] Every emitted value carries complete `Provenance` with a stable
      fingerprint
- [ ] No spectral index is reported in a carbon unit
- [ ] Every estimate is accompanied by an interval labelled with its `kind`
- [ ] Placebo p-values use the add-one correction and state their floor
- [ ] Failed robustness gates short-circuit to `INCONCLUSIVE`; there is no
      weak-positive path
- [ ] Unit tests cover the recovery case, the null case and each refusal path
- [ ] Methodology is documented in `docs/` with its assumptions and failure
      modes stated

### Frontend (Viraj)

- [ ] Every view renders correctly at phone, tablet and desktop widths
- [ ] The simulated-data banner is persistent and not dismissible on any view
      showing a simulated run
- [ ] No bare numbers: every value shows its unit and, where one exists, its
      interval with the interval's `kind`
- [ ] Provenance for any displayed number is reachable in two clicks
- [ ] Caveats render with the verdict, never behind a disclosure triangle
- [ ] `INCONCLUSIVE` is styled neutrally; `divergent_from_claim` is amber, not
      alarm-red
- [ ] No copy, tooltip or colour implies wrongdoing
- [ ] Loading, empty, refusal and error states are designed, not default
- [ ] Types come from the generated API client, never hand-written against a
      Python implementation detail
- [ ] Keyboard navigable; charts have accessible text alternatives

### Platform (Bhumi)

- [ ] The API consumes the engine only through the contract, enforced by test
- [ ] Every `ErrorCode` maps to an HTTP status; refusals are distinguishable
      from malfunctions in the response body
- [ ] Every request is validated at the boundary with a structured error
- [ ] Analysis jobs survive a process restart; status transitions are
      persisted and observable
- [ ] Evidence bundles are stored with their contract version and remain
      readable after a minor contract bump
- [ ] `spec_hash` caching returns a stored result rather than recomputing
- [ ] No credential is ever logged
- [ ] An observed-data request with no implementation returns 501, never
      simulated data
- [ ] OpenAPI schema is complete and generates working TypeScript types
- [ ] Integration tests cover the full path: request → job → engine → store →
      API → response
- [ ] Deploys from a green CI run with a documented rollback
- [ ] Structured logs carry run id, case id and stage; errors are alertable

### The contract (shared)

- [ ] Every field has a docstring saying what it means and who sets it
- [ ] Version bumped according to the semantics in `contracts/version.py`
- [ ] Both owners have reviewed the change
- [ ] Stored bundles from the previous version still load
- [ ] Round-trips through JSON without loss
- [ ] `test_contract_boundary.py` passes

---

## Workload accounting

Story points, not task counts — splitting small tasks to balance a number would
defeat the purpose.

| Owner | Area | Points |
| --- | --- | ---: |
| Viraj | Frontend and demo experience | 22 |
| Viraj | Analytical engine and validation | 18 |
| | **Viraj total** | **40** |
| Bhumi | Foundation, configuration, database | 10 |
| Bhumi | Data, job and storage services | 16 |
| Bhumi | APIs, reports and GenAI integration | 16 |
| Bhumi | Integration, deployment, CI/CD, operations | 18 |
| | **Bhumi total** | **60** |

See [`docs/13-implementation-plan.md`](docs/13-implementation-plan.md) for the
phased task breakdown and [`docs/12-contract.md`](docs/12-contract.md) for the
contract specification.
