# GroundTruth API: a consumer's guide

For anyone integrating with the GroundTruth API from outside the project: a script, a notebook,
another service. It covers signing in, running and reading an analysis, comparing runs,
exporting, and, in most detail, how to tell **a refusal** from **an error**, because a client that
treats them alike will mislead its users.

The reference for every endpoint, field and parameter is the OpenAPI schema the API serves at
`/openapi.json` (browsable at `/docs`). Every example below is a real response: they are produced
by calling the API on simulated data in `tests/test_api_docs.py`, which fails if this guide falls
out of date. Values that differ on every call are shown as placeholders (`<run_id_1>`,
`<request_id>`, `<timestamp>`, `<uuid>`, `<ms>`, `<token>`, `<seconds>`), and long lists are cut,
with a note saying so.

**Contents**

1. [Before you start](#1-before-you-start)
2. [Signing in](#2-signing-in)
3. [Running an analysis](#3-running-an-analysis)
4. [Reading a result](#4-reading-a-result)
5. [Comparing two runs](#5-comparing-two-runs)
6. [Exports](#6-exports)
7. [Refusals and errors](#7-refusals-and-errors)
8. [Every error code](#8-every-error-code)
9. [Limits](#9-limits)
10. [Simulated and observed data](#10-simulated-and-observed-data)
11. [Reproducibility](#11-reproducibility)

## 1. Before you start

* **Base URL**: wherever the deployment serves the API, e.g. `http://localhost:8000` locally.
* **Format**: JSON in and out, except the exports (CSV, PDF, ZIP) and the map tiles.
* **Sign-in**: every route except `/health`, the OpenAPI pages and the sign-in routes under
  `/auth/` needs a session. Most also need an **active organization**, and project data needs your organization to
  own the project or have been granted it.
* **Request ids**: every response carries `X-Request-ID`. Quote it when you report a problem. You
  may send your own (8 to 64 characters of `A-Z a-z 0-9 . _ -`) and it is kept.
* **Never parse the prose.** Act on `code` and `is_refusal`; the `message` text may change.

## 2. Signing in

Sign-in is a session cookie, as a browser uses it. Post your email and password to
`/auth/login`; the response sets `gt_session` (HttpOnly, SameSite=Lax, Secure behind HTTPS, valid
for 7 days by default). Send that cookie with every later request.

**Scripts must send an `Origin` header** on every `POST`, `PATCH` and `DELETE` that carries the
cookie, and it must be one of the deployment's allowed origins (`CORS_ALLOWED_ORIGINS`, normally
the web app's address). This is the guard against cross-site request forgery: without it, a
signed-in write is refused with `403 csrf_origin_rejected` (example in section 7). `GET` needs no
`Origin`.

<!-- example:sign-in -->
```http
POST /auth/login
Content-Type: application/json
Origin: http://localhost:3000

{
  "email": "analyst@example.org",
  "password": "correct horse battery"
}
```

Response `200`

```http
content-type: application/json
set-cookie: gt_session=<token>; HttpOnly; Max-Age=604800; Path=/; SameSite=lax
x-request-id: <request_id>
```

```json
{
  "id": "<uuid>",
  "email": "analyst@example.org",
  "role": "user",
  "is_active": true,
  "created_at": "<timestamp>",
  "last_login_at": "<timestamp>"
}
```
<!-- /example:sign-in -->

If you belong to more than one organization, choose the one you act for with
`POST /orgs/active` and `{"slug": "<org-slug>"}`; with exactly one it is chosen for you.
`GET /auth/me` tells you who you are signed in as and which organization is active.

A request without a session is refused:

<!-- example:unauthenticated -->
```http
GET /runs
```

Response `401`

```http
content-type: application/json
x-request-id: <request_id>
```

```json
{
  "detail": {
    "code": "unauthenticated",
    "message": "Sign in to continue.",
    "hint": null,
    "is_refusal": false
  },
  "is_refusal": false,
  "request_id": "<request_id>"
}
```
<!-- /example:unauthenticated -->

In Python with `requests`, a session keeps the cookie for you:

```python
import requests

API, ORIGIN = "http://localhost:8000", "http://localhost:3000"
s = requests.Session()
s.headers["Origin"] = ORIGIN
s.post(f"{API}/auth/login", json={"email": "you@example.org", "password": "..."}).raise_for_status()
```

## 3. Running an analysis

An analysis runs in the background: **submit it, then poll it** (or follow its event stream).

**Submit** with `POST /jobs`. `202` means a new job was queued. `200` means nothing new had to
run: a stored result already answers exactly this request (`from_cache: true`), or an identical job
is already in flight (`deduplicated: true`). Either way `run_id` is the run that answers it.

<!-- example:submit-job -->
```http
POST /jobs
Content-Type: application/json
Origin: http://localhost:3000

{
  "case_id": "kariba-redd",
  "synthetic": true
}
```

Response `202`

```http
content-type: application/json
x-request-id: <request_id>
```

```json
{
  "run_id": "<run_id_1>",
  "from_cache": false,
  "deduplicated": false,
  "status_url": "/jobs/<run_id_1>",
  "job": {
    "run_id": "<run_id_1>",
    "case_id": "kariba-redd",
    "status": "queued",
    "result_state": "queued",
    "terminal": false,
    "engine_status": null,
    "data_mode": "simulated",
    "is_simulated": true,
    "notice": "SIMULATED DATA: this run used the synthetic fixture provider. Its numbers describe a test fixture and say nothing about any real project.",
    "attempt": 0,
    "max_attempts": 3,
    "cancel_requested": false,
    "stage": null,
    "stages": [
      {
        "name": "claim",
        "label": "Claimed by a worker",
        "state": "pending",
        "started_at": null,
        "finished_at": null,
        "duration_ms": null,
        "elapsed_ms": null
      },
      {
        "name": "data",
        "label": "Resolving data access",
        "state": "pending",
        "started_at": null,
        "finished_at": null,
        "duration_ms": null,
        "elapsed_ms": null
      },
      {
        "name": "engine",
        "label": "Running the analysis engine",
        "state": "pending",
        "started_at": null,
        "finished_at": null,
        "duration_ms": null,
        "elapsed_ms": null
      },
      {
        "name": "record",
        "label": "Recording the result",
        "state": "pending",
        "started_at": null,
        "finished_at": null,
        "duration_ms": null,
        "elapsed_ms": null
      }
    ],
    "engine_metrics": {
      "available": false,
      "source": "run_metrics",
      "total_ms": null,
      "stages": [],
      "stopped_at": null,
      "n_units_observed": null,
      "n_donors_admitted": null,
      "n_estimator_fits": null,
      "note": "Available when the engine finishes. Nothing is estimated."
    },
    "timeline": [
      {
        "event": "queued",
        "at": "<timestamp>"
      }
    ],
    "created_at": "<timestamp>",
    "updated_at": "<timestamp>",
    "last_heartbeat_at": null,
    "lease_expires_at": null,
    "retry_at": null,
    "error": null,
    "failure_reason": null,
    "status_url": "/jobs/<run_id_1>",
    "result_url": null,
    "note": "There is no percentage because none can be known: the analysis engine runs as one step and reports its internal timings only when it finishes. `stages` are observed as they happen; `engine_metrics` fills in afterwards."
  }
}
```
<!-- /example:submit-job -->

**Poll** `GET /jobs/{run_id}` (the `status_url`) about once a second, and **stop when `terminal` is
true**. `result_state` says what the run produced: `queued`, `running`, `measured`, `refused`,
`failed` or `cancelled`.

<!-- example:poll-queued -->
```http
GET /jobs/<run_id_1>
```

Response `200`

```http
content-type: application/json
x-request-id: <request_id>
```

```json
{
  "run_id": "<run_id_1>",
  "case_id": "kariba-redd",
  "status": "queued",
  "result_state": "queued",
  "terminal": false,
  "engine_status": null,
  "data_mode": "simulated",
  "is_simulated": true,
  "notice": "SIMULATED DATA: this run used the synthetic fixture provider. Its numbers describe a test fixture and say nothing about any real project.",
  "attempt": 0,
  "max_attempts": 3,
  "cancel_requested": false,
  "stage": null,
  "stages": [
    {
      "name": "claim",
      "label": "Claimed by a worker",
      "state": "pending",
      "started_at": null,
      "finished_at": null,
      "duration_ms": null,
      "elapsed_ms": null
    },
    {
      "name": "data",
      "label": "Resolving data access",
      "state": "pending",
      "started_at": null,
      "finished_at": null,
      "duration_ms": null,
      "elapsed_ms": null
    },
    {
      "name": "engine",
      "label": "Running the analysis engine",
      "state": "pending",
      "started_at": null,
      "finished_at": null,
      "duration_ms": null,
      "elapsed_ms": null
    },
    {
      "name": "record",
      "label": "Recording the result",
      "state": "pending",
      "started_at": null,
      "finished_at": null,
      "duration_ms": null,
      "elapsed_ms": null
    }
  ],
  "engine_metrics": {
    "available": false,
    "source": "run_metrics",
    "total_ms": null,
    "stages": [],
    "stopped_at": null,
    "n_units_observed": null,
    "n_donors_admitted": null,
    "n_estimator_fits": null,
    "note": "Available when the engine finishes. Nothing is estimated."
  },
  "timeline": [
    {
      "event": "queued",
      "at": "<timestamp>"
    }
  ],
  "created_at": "<timestamp>",
  "updated_at": "<timestamp>",
  "last_heartbeat_at": null,
  "lease_expires_at": null,
  "retry_at": null,
  "error": null,
  "failure_reason": null,
  "status_url": "/jobs/<run_id_1>",
  "result_url": null,
  "note": "There is no percentage because none can be known: the analysis engine runs as one step and reports its internal timings only when it finishes. `stages` are observed as they happen; `engine_metrics` fills in afterwards."
}
```
<!-- /example:poll-queued -->

Once a worker has run it:

<!-- example:poll-finished -->
```http
GET /jobs/<run_id_1>
```

Response `200`

```http
content-type: application/json
x-request-id: <request_id>
```

```json
{
  "run_id": "<run_id_1>",
  "case_id": "kariba-redd",
  "status": "succeeded",
  "result_state": "measured",
  "terminal": true,
  "engine_status": "completed",
  "data_mode": "simulated",
  "is_simulated": true,
  "notice": "SIMULATED DATA: this run used the synthetic fixture provider. Its numbers describe a test fixture and say nothing about any real project.",
  "attempt": 1,
  "max_attempts": 3,
  "cancel_requested": false,
  "stage": "record",
  "stages": [
    {
      "name": "claim",
      "label": "Claimed by a worker",
      "state": "done",
      "started_at": "<timestamp>",
      "finished_at": "<timestamp>",
      "duration_ms": "<ms>",
      "elapsed_ms": null
    },
    {
      "name": "data",
      "label": "Resolving data access",
      "state": "done",
      "started_at": "<timestamp>",
      "finished_at": "<timestamp>",
      "duration_ms": "<ms>",
      "elapsed_ms": null
    },
    {
      "name": "engine",
      "label": "Running the analysis engine",
      "state": "done",
      "started_at": "<timestamp>",
      "finished_at": "<timestamp>",
      "duration_ms": "<ms>",
      "elapsed_ms": null
    },
    {
      "name": "record",
      "label": "Recording the result",
      "state": "done",
      "started_at": "<timestamp>",
      "finished_at": "<timestamp>",
      "duration_ms": null,
      "elapsed_ms": null
    }
  ],
  "engine_metrics": {
    "available": true,
    "source": "run_metrics",
    "total_ms": "<ms>",
    "stages": [
      {
        "name": "observation",
        "duration_ms": "<ms>"
      },
      {
        "name": "matching",
        "duration_ms": "<ms>"
      },
      "… 4 more (cut in this guide)"
    ],
    "stopped_at": null,
    "n_units_observed": 81,
    "n_donors_admitted": 50,
    "n_estimator_fits": 65,
    "note": "From RunMetrics, recorded by the engine when it returned."
  },
  "timeline": [
    {
      "event": "queued",
      "at": "<timestamp>"
    },
    {
      "event": "running",
      "at": "<timestamp>"
    },
    {
      "event": "succeeded",
      "at": "<timestamp>"
    }
  ],
  "created_at": "<timestamp>",
  "updated_at": "<timestamp>",
  "last_heartbeat_at": null,
  "lease_expires_at": null,
  "retry_at": null,
  "error": null,
  "failure_reason": null,
  "status_url": "/jobs/<run_id_1>",
  "result_url": "/runs/<run_id_1>",
  "note": "There is no percentage because none can be known: the analysis engine runs as one step and reports its internal timings only when it finishes. `stages` are observed as they happen; `engine_metrics` fills in afterwards."
}
```
<!-- /example:poll-finished -->

Instead of polling, `GET /jobs/{run_id}/events` streams Server-Sent Events: a `progress` event
whenever the job's view changes and a final `done`, each carrying the same JSON as
`GET /jobs/{run_id}`; an `error` or `timeout` event ends the stream early. To stop a job, send
`POST /jobs/{run_id}/cancel`: a queued job is cancelled at once; a running one stops at its next
checkpoint, or when the engine returns, and its result is then discarded.

`POST /cases/{case_id}/verify` is the synchronous alternative: it runs the analysis while you wait
and answers with the result, or with the refusal (section 7).

## 4. Reading a result

`GET /runs/{run_id}` returns a stored run in full: its lifecycle, its outcome and its evidence
bundle (`include_bundle=false` leaves the bundle out; `include_report=true` adds a plain-language
report). `GET /runs` lists runs, newest first, filtered by `case_id`, `status`, `engine_version`,
`data_mode`, `created_after` and `created_before`, and paged with `limit` and `cursor`.

A completed run (its bundle cut to two items here):

<!-- example:completed-run -->
```http
GET /runs/<run_id_1>
```

Response `200`

```http
content-type: application/json
x-request-id: <request_id>
```

```json
{
  "run_id": "<run_id_1>",
  "case_id": "kariba-redd",
  "spec_hash": "7d88978d78ddbf8ece5578fb88eebfc4",
  "status": "succeeded",
  "result_state": "measured",
  "engine_status": "completed",
  "verdict_label": "inconclusive",
  "data_mode": "simulated",
  "is_simulated": true,
  "notice": "SIMULATED DATA: this run used the synthetic fixture provider. Its numbers describe a test fixture and say nothing about any real project.",
  "engine_version": "0.10.0",
  "contract_version": "1.0.0",
  "created_at": "<timestamp>",
  "error_code": null,
  "is_refusal": null,
  "failure_reason": null,
  "has_bundle": true,
  "engine": {
    "engine_version": "0.10.0",
    "contract_version": "1.0.0",
    "git_sha": null
  },
  "seed": 20260101,
  "datasets": [
    {
      "dataset_id": "groundtruth-synthetic-simulation",
      "version": "v1;true_effect=0.06",
      "provider": "synthetic",
      "asset": null,
      "source_uri": null,
      "retrieved_at": null
    }
  ],
  "started_at": "<timestamp>",
  "finished_at": "<timestamp>",
  "metrics": {
    "duration_ms": "<ms>",
    "stage_durations_ms": {
      "observation": "<ms>",
      "matching": "<ms>",
      "alignment": "<ms>",
      "estimation": "<ms>",
      "robustness": "<ms>",
      "assembly": "<ms>"
    },
    "n_units_observed": 81,
    "n_donors_admitted": 50,
    "n_estimator_fits": 65
  },
  "error": null,
  "verdict_rationale": "INCONCLUSIVE / NOT CALIBRATED: an effect on the observed indicator was estimated, but it cannot be expressed in tCO2e because no validated, site-calibrated biomass model is available. The claim and the effect are not in commensurable units, so no comparison against the developer's claim is made, and NDVI is not carbon.",
  "caveats": [
    "THIS RUN USED SIMULATED DATA. The figures below describe a synthetic test fixture and say nothing about any real project.",
    "A divergence between an independent estimate and a developer claim is not evidence of fraud; it indicates that the claim warrants accredited review.",
    "Spectral indices track vegetation condition, not carbon stocks.",
    "Estimates are conditional on the donor pool and the pre-treatment fit reported alongside them."
  ],
  "warnings": [
    "SIMULATED DATA: this bundle was produced from the synthetic fixture provider and must not be published as a finding about a real project.",
    "There are more donors than pre-treatment periods, so the individual donor weights are not uniquely identified. The counterfactual path and the effect estimate are still well determined, but the listed contributing regions are one of several equally good weightings, and should be read as an illustration of the comparison set rather than as the only one consistent with the data.",
    "The difference-in-differences cross-check fails its parallel-trends screen; treat it as uninformative here and rely on the synthetic control.",
    "30 candidate regions were excluded from the donor pool; see the donor-pool table for per-unit reasons."
  ],
  "bundle": {
    "case_id": "kariba-redd",
    "schema_version": "1.0",
    "items": [
      {
        "id": "claim.case_id",
        "label": "Case identifier",
        "value": "kariba-redd",
        "unit": "",
        "confidence": null,
        "provenance": {
          "source": "https://registry.verra.org/app/projectDetail/VCS/902",
          "method": "published-third-party-figure",
          "stage": "external",
          "source_uri": "https://registry.verra.org/app/projectDetail/VCS/902",
          "retrieved_at": null,
          "code_version": null,
          "parameters": {},
          "inputs": [],
          "notes": null
        },
        "state": "DERIVED",
        "qualifiers": {}
      },
      {
        "id": "fit.n_pre_periods",
        "label": "Pre-treatment periods observed for the project and every donor",
        "value": 10,
        "unit": "",
        "confidence": null,
        "provenance": {
          "source": "groundtruth.platform.datasets.synthetic",
          "method": "window-alignment/period-labels",
          "stage": "alignment",
          "source_uri": null,
          "retrieved_at": "<timestamp>",
          "code_version": "0.3.0",
          "parameters": {
            "pre_periods": [
              2001,
              2010
            ],
            "post_periods": [
              2011,
              2022
            ],
            "n_units": 51
          },
          "inputs": [],
          "notes": "Every included series was checked to carry a finite value for every window period. The pre/post split is taken from period labels, not array positions."
        },
        "state": "DERIVED",
        "qualifiers": {
          "first_period": 2001,
          "last_period": 2010
        }
      },
      "… 28 more (cut in this guide)"
    ],
    "verdict": {
      "label": "inconclusive",
      "rationale": "INCONCLUSIVE / NOT CALIBRATED: an effect on the observed indicator was estimated, but it cannot be expressed in tCO2e because no validated, site-calibrated biomass model is available. The claim and the effect are not in commensurable units, so no comparison against the developer's claim is made, and NDVI is not carbon.",
      "divergence_ratio": null,
      "caveats": [
        "THIS RUN USED SIMULATED DATA. The figures below describe a synthetic test fixture and say nothing about any real project.",
        "A divergence between an independent estimate and a developer claim is not evidence of fraud; it indicates that the claim warrants accredited review.",
        "Spectral indices track vegetation condition, not carbon stocks.",
        "Estimates are conditional on the donor pool and the pre-treatment fit reported alongside them."
      ],
      "supporting_evidence_ids": []
    },
    "warnings": [
      "SIMULATED DATA: this bundle was produced from the synthetic fixture provider and must not be published as a finding about a real project.",
      "There are more donors than pre-treatment periods, so the individual donor weights are not uniquely identified. The counterfactual path and the effect estimate are still well determined, but the listed contributing regions are one of several equally good weightings, and should be read as an illustration of the comparison set rather than as the only one consistent with the data.",
      "The difference-in-differences cross-check fails its parallel-trends screen; treat it as uninformative here and rely on the synthetic control.",
      "30 candidate regions were excluded from the donor pool; see the donor-pool table for per-unit reasons."
    ]
  },
  "report_markdown": null,
  "report_generator": null
}
```
<!-- /example:completed-run -->

What to show, and how:

* **`verdict_label`** is a screening verdict. A divergence between this estimate and a developer's
  claim **warrants accredited review; it is never a finding of fraud**, and must not be presented
  as one.
* **`caveats`** must accompany the verdict wherever you show it.
* Every **evidence item** has a value, its unit, its uncertainty (`confidence`) and its
  provenance. A vegetation index (NDVI, EVI) is an index, **never a carbon quantity**: do not
  convert it.
* **`is_simulated`** true means the numbers come from a simulation, not satellites: show the
  `notice` prominently (section 10).

## 5. Comparing two runs

`GET /runs/compare?baseline=…&candidate=…` sets two runs side by side, evidence item by evidence
item. Two runs of the same case, data mode, engine version and contract major version are
comparable:

<!-- example:compare -->
```http
GET /runs/compare?baseline=<run_id_1>&candidate=<run_id_4>
```

Response `200`

```http
content-type: application/json
x-request-id: <request_id>
```

```json
{
  "baseline": {
    "run_id": "<run_id_1>",
    "case_id": "kariba-redd",
    "spec_hash": "7d88978d78ddbf8ece5578fb88eebfc4",
    "status": "succeeded",
    "result_state": "measured",
    "engine_status": "completed",
    "verdict_label": "inconclusive",
    "data_mode": "simulated",
    "is_simulated": true,
    "notice": "SIMULATED DATA: this run used the synthetic fixture provider. Its numbers describe a test fixture and say nothing about any real project.",
    "engine_version": "0.10.0",
    "contract_version": "1.0.0",
    "created_at": "<timestamp>",
    "error_code": null,
    "is_refusal": null,
    "failure_reason": null
  },
  "candidate": {
    "run_id": "<run_id_4>",
    "case_id": "kariba-redd",
    "spec_hash": "f6f0834f3cf5a00e61a09da90539e14b",
    "status": "succeeded",
    "result_state": "measured",
    "engine_status": "completed",
    "verdict_label": "inconclusive",
    "data_mode": "simulated",
    "is_simulated": true,
    "notice": "SIMULATED DATA: this run used the synthetic fixture provider. Its numbers describe a test fixture and say nothing about any real project.",
    "engine_version": "0.10.0",
    "contract_version": "1.0.0",
    "created_at": "<timestamp>",
    "error_code": null,
    "is_refusal": null,
    "failure_reason": null
  },
  "comparable": true,
  "not_comparable": [],
  "same_specification": false,
  "contains_simulated": true,
  "diff": {
    "summary": {
      "added": 0,
      "removed": 0,
      "changed": 0,
      "unchanged": 30
    },
    "items": [],
    "verdict": {
      "baseline_label": "inconclusive",
      "candidate_label": "inconclusive",
      "label_changed": false,
      "baseline_divergence_ratio": null,
      "candidate_divergence_ratio": null,
      "divergence_ratio_changed": false,
      "rationale_changed": false
    },
    "warnings": {
      "added": [],
      "removed": []
    }
  }
}
```
<!-- /example:compare -->

Otherwise you get every reason they are not (`not_comparable`), here a refused run with no
evidence bundle:

<!-- example:compare-not-comparable -->
```http
GET /runs/compare?baseline=<run_id_1>&candidate=<run_id_2>
```

Response `200`

```http
content-type: application/json
x-request-id: <request_id>
```

```json
{
  "baseline": {
    "run_id": "<run_id_1>",
    "case_id": "kariba-redd",
    "spec_hash": "7d88978d78ddbf8ece5578fb88eebfc4",
    "status": "succeeded",
    "result_state": "measured",
    "engine_status": "completed",
    "verdict_label": "inconclusive",
    "data_mode": "simulated",
    "is_simulated": true,
    "notice": "SIMULATED DATA: this run used the synthetic fixture provider. Its numbers describe a test fixture and say nothing about any real project.",
    "engine_version": "0.10.0",
    "contract_version": "1.0.0",
    "created_at": "<timestamp>",
    "error_code": null,
    "is_refusal": null,
    "failure_reason": null
  },
  "candidate": {
    "run_id": "<run_id_2>",
    "case_id": "kariba-redd",
    "spec_hash": "65496c3c8795dab6a0be477a8b25d257",
    "status": "succeeded",
    "result_state": "refused",
    "engine_status": "refused",
    "verdict_label": "not_assessed",
    "data_mode": "simulated",
    "is_simulated": true,
    "notice": "SIMULATED DATA: this run used the synthetic fixture provider. Its numbers describe a test fixture and say nothing about any real project.",
    "engine_version": "0.10.0",
    "contract_version": "1.0.0",
    "created_at": "<timestamp>",
    "error_code": "donor_pool_inadequate",
    "is_refusal": true,
    "failure_reason": null
  },
  "comparable": false,
  "not_comparable": [
    {
      "code": "no_bundle",
      "side": "candidate",
      "message": "The candidate run was refused by the engine (donor_pool_inadequate): only 79 admissible donors for 'kariba-redd'; 500 required. Widen the search region or relax the caliper, but do not estimate on an under-powered pool.. A refusal is a legitimate outcome with no evidence to compare."
    }
  ],
  "same_specification": false,
  "contains_simulated": true,
  "diff": null
}
```
<!-- /example:compare-not-comparable -->

## 6. Exports

| Export | Route | What |
|---|---|---|
| Evidence table | `GET /cases/{case_id}/export/csv` | Every evidence item with its provenance, as CSV |
| Screening report | `GET /cases/{case_id}/export/pdf` | A PDF report, verified against its own evidence before it is sent |
| Monitoring dossier | `GET /projects/{project_id}/export/dossier` | A ZIP of the project's evidence with a checksum manifest |

Each export says what its data is (`X-GroundTruth-Data-Mode: simulated` or `observed`) and who
wrote its report (`X-GroundTruth-Report-Generator`: `deterministic`, or `genai:<provider>` with
`?narrate=true`). A narrated PDF that fails verification is **refused** (`502
narration_not_grounded`), never replaced by something else; `?narrate=true` without a configured
provider is `422 narration_not_configured`.

<!-- example:csv-export -->
```http
GET /cases/kariba-redd/export/csv
```

Response `200`

```http
content-disposition: attachment; filename="kariba-redd-evidence.csv"
content-type: text/csv; charset=utf-8
x-groundtruth-data-mode: simulated
x-groundtruth-report-generator: deterministic
x-request-id: <request_id>
```

```text
# case_id: kariba-redd
# report_generator: deterministic
# schema_version: 1.0
# is_simulated: True
# data_origin: SYNTHETIC_SIMULATION
# verdict_label: inconclusive
# verdict_rationale: INCONCLUSIVE / NOT CALIBRATED: an effect on the observed indicator was estimated, but it cannot be expressed in tCO2e because no validated, site-calibrated biomass model is available. The claim and the effect are not in commensurable units, so no comparison against the developer's claim is made, and NDVI is not carbon.
# biomass_calibration_status: NOT_CALIBRATED
id,label,value,unit,interval_lower,interval_upper,interval_level,interval_kind,provenance_source,provenance_method,provenance_stage,provenance_fingerprint,notes
claim.case_id,Case identifier,kariba-redd,,,,,,https://registry.verra.org/app/projectDetail/VCS/902,published-third-party-figure,external,0276cbcb30e48837,
fit.n_pre_periods,Pre-treatment periods observed for the project and every donor,10,,,,,,groundtruth.platform.datasets.synthetic,window-alignment/period-labels,alignment,7bba4f07a639b020,
fit.n_post_periods,Post-treatment periods observed for the project and every donor,12,,,,,,groundtruth.platform.datasets.synthetic,window-alignment/period-labels,alignment,7bba4f07a639b020,
```
<!-- /example:csv-export -->

## 7. Refusals and errors

Every unsuccessful response has the same envelope:

| Field | Meaning |
|---|---|
| `detail` | What went wrong. Usually an object with `code`, `message` and `hint` (and `stage`, `remediation`, `run_id` for an engine outcome); a plain string for a few generic errors; a list for a validation error. |
| `is_refusal` | **True only for a scientific refusal.** Also inside `detail` when it is an object. |
| `request_id` | The same as the `X-Request-ID` header. |
| `code`, `message`, `fields` | Added at the top level when `detail` is a string or a list, so every error has a `code`. |

No error body ever contains a stack trace, a file path, SQL or a secret.

### A refusal is an answer, not a failure

GroundTruth estimates what a project changed by comparing it with similar areas that had no
project. When the data cannot support a trustworthy number (too few comparable areas, too short a
history), the engine **refuses** instead of returning a fragile one. That is the system working:
the honest answer to "did this project make a difference?" is sometimes "these data cannot tell".

|  | Refusal (`is_refusal: true`) | Error (`is_refusal: false`) |
|---|---|---|
| What it means | The data cannot support an estimate. | Something is wrong with the request or the system. |
| Codes | `insufficient_data`, `donor_pool_inadequate` | everything else |
| Will retrying help? | **No.** The same data refuses the same way. | A 5xx may pass; a 4xx needs a different request. |
| What to tell a user | "The evidence is insufficient to estimate this", with `message` and `remediation`. Never "error" or "failed". | That the request failed, with `message` and the request id. |
| A stored run | `status: succeeded`, `result_state: refused`, `error.is_refusal: true` | `status: failed`, `result_state: failed` |
| What not to do | **Never lower `min_donors` or tune a setting to force a number out.** | — |

The synchronous `/verify` refuses with `422`, and `is_refusal` says it is a refusal:

<!-- example:verify-refusal -->
```http
POST /cases/kariba-redd/verify
Content-Type: application/json
Origin: http://localhost:3000

{
  "min_donors": 500
}
```

Response `422`

```http
content-type: application/json
x-request-id: <request_id>
```

```json
{
  "detail": {
    "code": "donor_pool_inadequate",
    "message": "only 79 admissible donors for 'kariba-redd'; 500 required. Widen the search region or relax the caliper, but do not estimate on an under-powered pool.",
    "stage": "matching",
    "is_refusal": true,
    "remediation": "Widen the donor search region or relax the common-support caliper. Do not lower min_donors to force a result.",
    "run_id": "<run_id_3>"
  },
  "is_refusal": true,
  "request_id": "<request_id>"
}
```
<!-- /example:verify-refusal -->

A queued run that refuses **succeeds as a job**: the job did its work, and the work's answer is a
refusal. Read `result_state` and `error`:

<!-- example:refused-run -->
```http
GET /runs/<run_id_2>?include_bundle=false
```

Response `200`

```http
content-type: application/json
x-request-id: <request_id>
```

```json
{
  "run_id": "<run_id_2>",
  "case_id": "kariba-redd",
  "spec_hash": "65496c3c8795dab6a0be477a8b25d257",
  "status": "succeeded",
  "result_state": "refused",
  "engine_status": "refused",
  "verdict_label": "not_assessed",
  "data_mode": "simulated",
  "is_simulated": true,
  "notice": "SIMULATED DATA: this run used the synthetic fixture provider. Its numbers describe a test fixture and say nothing about any real project.",
  "engine_version": "0.10.0",
  "contract_version": "1.0.0",
  "created_at": "<timestamp>",
  "error_code": "donor_pool_inadequate",
  "is_refusal": true,
  "failure_reason": null,
  "has_bundle": false,
  "engine": {
    "engine_version": "0.10.0",
    "contract_version": "1.0.0",
    "git_sha": null
  },
  "seed": 20260101,
  "datasets": [
    {
      "dataset_id": "groundtruth-synthetic-simulation",
      "version": "v1;true_effect=0.06",
      "provider": "synthetic",
      "asset": null,
      "source_uri": null,
      "retrieved_at": null
    }
  ],
  "started_at": "<timestamp>",
  "finished_at": "<timestamp>",
  "metrics": {
    "duration_ms": "<ms>",
    "stage_durations_ms": {},
    "n_units_observed": 81,
    "n_donors_admitted": 0,
    "n_estimator_fits": 0
  },
  "error": {
    "code": "donor_pool_inadequate",
    "message": "only 79 admissible donors for 'kariba-redd'; 500 required. Widen the search region or relax the caliper, but do not estimate on an under-powered pool.",
    "stage": "matching",
    "detail": {
      "n_candidates": 80,
      "min_donors_required": 500
    },
    "remediation": "Widen the donor search region or relax the common-support caliper. Do not lower min_donors to force a result.",
    "is_refusal": true
  },
  "verdict_rationale": null,
  "caveats": [],
  "warnings": [],
  "bundle": null,
  "report_markdown": null,
  "report_generator": null
}
```
<!-- /example:refused-run -->

### Errors

A request the API cannot read answers `422 validation_error`, naming each field in `fields`; what
you sent is never echoed back:

<!-- example:validation-error -->
```http
POST /jobs
Content-Type: application/json
Origin: http://localhost:3000

{
  "case_id": "kariba-redd",
  "min_donors": "lots"
}
```

Response `422`

```http
content-type: application/json
x-request-id: <request_id>
```

```json
{
  "detail": [
    {
      "type": "int_parsing",
      "loc": [
        "body",
        "min_donors"
      ],
      "msg": "Input should be a valid integer, unable to parse string as an integer"
    }
  ],
  "code": "validation_error",
  "message": "Invalid request. body.min_donors: Input should be a valid integer, unable to parse string as an integer",
  "fields": [
    "body.min_donors"
  ],
  "is_refusal": false,
  "request_id": "<request_id>"
}
```
<!-- /example:validation-error -->

A signed-in write from an origin the deployment does not allow:

<!-- example:csrf-rejected -->
```http
POST /jobs
Content-Type: application/json
Origin: https://elsewhere.example

{
  "case_id": "kariba-redd",
  "synthetic": true
}
```

Response `403`

```http
content-type: application/json
x-request-id: <request_id>
```

```json
{
  "detail": {
    "code": "csrf_origin_rejected",
    "message": "The request's origin is not allowed.",
    "hint": null,
    "is_refusal": false
  },
  "is_refusal": false,
  "request_id": "<request_id>"
}
```
<!-- /example:csrf-rejected -->

An unexpected failure is `500 internal_error` with a generic message and the request id; the
details stay in the server log.

## 8. Every error code

Act on the code. The same code can have more than one HTTP status where noted, so a client should
switch on `code`, not on the status.

| Code | HTTP | Refusal | Meaning | What to do |
|---|---|---|---|---|
| `insufficient_data` | 422 | yes | The pre-treatment history is too short or too sparse to estimate. | Nothing to retry. Show the refusal with its `remediation`. |
| `donor_pool_inadequate` | 422 | yes | Too few comparable areas remain after screening. | Nothing to retry. Never lower `min_donors` to force a result. |
| `invalid_request` | 422 | no | The engine rejected the analysis request. | Fix the request. |
| `contract_version_mismatch` | 409 | no | The request or stored run uses an engine contract this API does not support. | Use a supported contract version. |
| `data_unavailable` | 503 | no | A required dataset could not be retrieved. | Retry later. |
| `estimation_failed` | 500 | no | The estimator failed to produce a result. | Report it with the request id. |
| `not_implemented` | 501 | no | Observed data, or a capability, that does not exist yet (section 10). | Use simulated data, or wait for the capability. |
| `internal_error` | 500 | no | An unexpected failure, or an engine failure it cannot classify. | Retry; report it with the request id if it persists. |
| `validation_error` | 422 | no | The request body or parameters are invalid; `fields` names each one. | Fix the named fields. |
| `http_<status>` | 404, 405, 501, … | no | A generic error with a plain-message `detail`, e.g. `http_404` for an unknown route or case. | Check the URL and ids. |
| `run_not_found` | 404 | no | No such run, or not one you may see. | Check the run id. |
| `case_not_found` | 404 | no | No such case, or not one you may see. | Check the case id. |
| `invalid_cursor` | 400 (`/runs`), 422 (`/orgs/{slug}/audit`) | no | The paging cursor is not valid. | Restart from the first page. |
| `invalid_filter` | 422 | no | A list filter is not valid. | Fix the filter. |
| `store_not_configured` | 503 | no | This deployment has no database for stored runs. | Ask the operator. |
| `store_unavailable` | 503 | no | The database cannot be reached. | Retry later. |
| `store_error` | 500 | no | The database failed. | Report it with the request id. |
| `job_already_finished` | 409 | no | The job is finished; there is nothing to cancel. | None needed. |
| `too_many_submissions` | 429 | no | Over the analysis submission budget (section 9). | Wait `Retry-After` seconds. |
| `invalid_case` | 422 | no | The case definition is invalid; the field is named. | Fix the named field. |
| `case_status_requires_review` | 422 | no | A case cannot be marked analysed without a reviewed run. | Omit `status`. |
| `min_donors_below_case_floor` | 422 | no | `min_donors` is below the case's pre-registered floor. | Omit it, or raise it. |
| `narration_not_configured` | 422 | no | `narrate=true` but no GenAI provider is configured. | Export without `narrate`. |
| `narration_failed` | 502 | no | The narration provider failed; nothing was exported. | Export without `narrate`, or retry. |
| `narration_not_grounded` | 502 | no | The narrated report failed verification against its evidence; refused, not substituted. | Export without `narrate`. |
| `report_not_grounded` | 500 | no | The report failed verification against its own evidence: a defect, never shipped. | Report it with the request id. |
| `unauthenticated` | 401 | no | Not signed in, or the session expired. | Sign in. |
| `invalid_credentials` | 401 | no | Wrong email or password (the two are indistinguishable). | Check the credentials. |
| `forbidden` | 403 | no | Your role may not do this. | Ask an owner or admin. |
| `csrf_origin_rejected` | 403 | no | A signed-in write came without an allowed `Origin`. | Send `Origin` (section 2). |
| `registration_closed` | 403 | no | This deployment does not accept new accounts. | Ask an administrator. |
| `not_found` | 404 | no | No such organization or project, or not one you may see. | Check the slug or id. |
| `user_not_found` | 404 | no | No such account, or not a member. | Check the email or user id. |
| `email_taken` | 409 | no | An account with that email exists. | Sign in instead. |
| `conflict` | 409 | no | The change would break a membership or sharing rule; `message` says which. | Read the message. |
| `last_admin` | 409 | no | The change would leave no administrator. | Appoint another first. |
| `no_active_organization` | 409 | no | The route needs an active organization and none is chosen. | `POST /orgs/active`. |
| `weak_password` | 422 | no | The password does not meet the policy. | Choose a stronger one. |
| `invalid_boundary` | 422 | no | The uploaded boundary file is not a valid area. | Fix the file; the message says why. |
| `invalid_grant` | 422 | no | The sharing request is not valid. | Read the message. |
| `too_many_attempts` | 429 | no | Too many failed sign-ins (section 9). | Wait `Retry-After` seconds. |
| `stream_timeout` | — (event) | no | An events stream ran for its full time; sent as an `error`-type event, not a status. | Reconnect, or poll. |

## 9. Limits

| Limit | Budget | When exceeded |
|---|---|---|
| Analysis submissions (`POST /jobs` and `POST /cases/{id}/verify` together) | 20 per user per 10 minutes, set by the deployment (`ANALYSIS_RATE_LIMIT`, `ANALYSIS_RATE_WINDOW_SECONDS`) | `429 too_many_submissions` |
| Failed sign-ins | 5 per email and client address per 15 minutes | `429 too_many_attempts` |

Both answer with a `Retry-After` header in seconds: wait that long. A submission answered from a
stored result still counts. Results you already have stay readable while you wait.

<!-- example:rate-limited -->
```http
POST /jobs
Content-Type: application/json
Origin: http://localhost:3000

{
  "case_id": "kariba-redd",
  "synthetic": true
}
```

Response `429`

```http
content-type: application/json
retry-after: <seconds>
x-request-id: <request_id>
```

```json
{
  "detail": {
    "code": "too_many_submissions",
    "message": "You have submitted 1 analyses in the last 10 minutes, the most allowed.",
    "hint": "Try again in 600 seconds. Results you already have stay available.",
    "is_refusal": false
  },
  "is_refusal": false,
  "request_id": "<request_id>"
}
```
<!-- /example:rate-limited -->

## 10. Simulated and observed data

Today GroundTruth analyses **simulated data only**: a fixture whose every value is labelled
simulated. Observed (satellite) data is not implemented yet, and asking for it is refused rather
than quietly simulated:

<!-- example:observed-not-implemented -->
```http
POST /jobs
Content-Type: application/json
Origin: http://localhost:3000

{
  "case_id": "kariba-redd",
  "synthetic": false
}
```

Response `501`

```http
content-type: application/json
x-request-id: <request_id>
```

```json
{
  "detail": {
    "code": "not_implemented",
    "message": "Observed-data analysis is not implemented: the Earth Engine reducer chain has not landed.",
    "hint": "Submit with synthetic=true to queue a simulated run.",
    "is_refusal": false
  },
  "is_refusal": false,
  "request_id": "<request_id>"
}
```
<!-- /example:observed-not-implemented -->

A simulated result says so everywhere: `data_mode: "simulated"`, `is_simulated: true`, a `notice`,
a warning in the bundle and the `X-GroundTruth-Data-Mode` export header. **Show that notice
wherever you show the numbers**, and never present simulated numbers as observations.

## 11. Reproducibility

Every run records its `spec_hash` (a hash of the full analysis specification), its engine and
contract versions, its random `seed` and every dataset it read. Two runs with the same
`spec_hash` and engine version give the same numbers, which is why `POST /jobs` can answer from a
stored result. To reproduce a result, keep those four values with it.

For simulated data the specification includes the simulation itself and the effect it injects,
pinned as the dataset `groundtruth-synthetic-simulation` (its version reads
`v1;true_effect=0.06`). Two simulated runs with different effects therefore have different
`spec_hash`es. On `/cases/{case_id}/verify` the `true_effect` you send is pinned the same way.

Stored runs are replayed daily, and a run that no longer reproduces under its own engine version
fails the check (see `docs/operations/README.md`, section 2.4).

---

*Maintainers: the examples are regenerated with `UPDATE_API_DOCS=1 pytest tests/test_api_docs.py`;
the same test fails when they, the error-code table or the OpenAPI descriptions fall behind.*
