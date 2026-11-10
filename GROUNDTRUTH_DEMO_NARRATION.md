# GroundTruth demonstration: narration and shot list

Video: `GROUNDTRUTH_DEMO_VIDEO.mp4`, 6:46 (406 s), 1920x1080, 30 fps, H.264 + AAC. Voice: Windows `Microsoft David Desktop` (local, offline). 792 words. Every timestamp below is measured from the final recording, not estimated.

Everything on screen is the live application, driven by `apps/web/e2e/demo/video/record.mjs`. Nothing is mocked or edited in. The one satellite project is a demonstration project created in the recording environment from a **hand-drawn boundary near Pune** and a **sample design note written for this demo**; its claims are illustrative, its satellite values are real Sentinel-2 measurements. The Kariba benchmark and the simulated cases are not used.

## Vocabulary used in the narration

| Term | Meaning in this product | Where it is seen |
|---|---|---|
| Observed | A measurement taken by a sensor (Sentinel-2 surface reflectance) | Observation tab, scene ids |
| Derived indicator | A number computed from observations (annual NDVI, EVI, NDMI, NBR inside the boundary) | Evidence-state badge `DERIVED` |
| Submitted claim | A statement the project made in its own document | Evidence tab, claims, original wording kept |
| Suggestion | A statement the platform extracted from text by pattern matching (not a language model); a candidate only | Extracted statements dialog |
| Model estimate | Anything produced by a statistical model; none in this demonstration (chart legend: diamond) | Chart legend |
| Inference | A conclusion drawn from evidence; the product limits these ("consistent with", "partly consistent") and refuses attribution | Verification tab |
| Unsupported | A claim the available evidence cannot test, with the reason; "not enough evidence" never means false | Verification tab |

The optional language-model assistant (which narrates results and computes nothing) is not configured in the demonstration environment and is not shown.

## Script

### 0:05 to 0:52: The accountability problem

| Time | Narration |
|---|---|
| 0:05.9 | Restoration and carbon projects are funded on claims: hectares restored, vegetation recovered, trees surviving. |
| 0:14.9 | Funders and auditors can rarely check those claims themselves, or see where each number came from. |
| 0:21.9 | GroundTruth is a screening tool for that gap. It lines up what a project claims against what can be observed, and states plainly what it cannot show. |
| 0:32.2 | It is not a fraud detector, and it does not replace an audit. A gap between claim and evidence is a reason to look closer, never a verdict. |
| 0:42.4 | The benchmark cases on this public page are simulated, and labelled. Everything after this uses a project created live, with real satellite data. |

### 0:55 to 1:37: The NGO: sign in and open a project

| Time | Narration |
|---|---|
| 0:55.7 | Let's follow a restoration NGO, signing in with a demonstration account. |
| 1:04.0 | What this user can open or change is decided by the server, not the page. The dashboard also lists a shared reference project with no observations, so we open our own. |
| 1:16.2 | This demonstration project is in the Sahyadri foothills near Pune, India, created by uploading a hand-drawn boundary. It is not a registered project. |
| 1:27.4 | The progress bar shows what is done: boundary, document, satellite data, assessment and claims. Climate data is still missing. |

### 1:42 to 2:31: Boundary, documents and claim extraction

| Time | Narration |
|---|---|
| 1:42.7 | The boundary is stored with a checksum, and measured on an equal-area projection: about two thousand and eighteen hectares. |
| 1:51.1 | On the Evidence tab the NGO uploads its design document, stored with a SHA-256 checksum so it cannot be changed unnoticed. |
| 2:00.5 | GroundTruth then lists the statements it recognises. This is plain pattern matching, not a language model, and these are candidates only. Nothing here is verified. |
| 2:12.9 | It found five: a restored area, a greenness change, sapling survival, a carbon figure, and a rise in bird species richness. |
| 2:23.3 | I have added all five as claims. Adding a claim does not verify it, and the original wording stays beside it. |

### 2:34 to 3:48: Real satellite observations

| Time | Narration |
|---|---|
| 2:34.4 | To get satellite evidence, the NGO requests observations for the boundary. A background worker downloads Sentinel-2 images from Microsoft Planetary Computer, masks cloud, and reduces each year to one value. |
| 2:49.1 | This request covered 2021 to 2026, January to March, at most twenty percent cloud. It finished, with project-area coverage above ninety-five percent every year. |
| 3:03.0 | The satellite's reflectance measurements are observations. The indices computed from them, such as NDVI, are derived indicators, and each row is badged that way. A model estimate would carry a diamond. There are none here. |
| 3:20.0 | The table lists the exact scene identifiers behind each year, so anyone can repeat the calculation. |
| 3:27.2 | NDVI shows how green the land looks from space. It is not carbon, tree survival or biodiversity, and these values are not validated against field data. |
| 3:39.0 | The series is not a clean rise: greenness peaks in 2023, then falls back. The assessment reads this as no clear change. |

### 3:51 to 4:53: Claim assessment

| Time | Narration |
|---|---|
| 3:51.9 | On the verification tab, each claim is judged on its own evidence. |
| 3:57.1 | The area claim is only partly consistent. The claimed nineteen hundred hectares fits inside the boundary, but a boundary shows where a project works, not how much land was restored. |
| 4:09.9 | The greenness claim, up 0.05, is consistent with the observed change of about 0.051. That describes greenness. It does not show the project caused it. |
| 4:23.9 | Three claims are marked not enough evidence to test: survival needs field surveys, carbon needs biomass measurement or a registry record, and bird species need wildlife surveys. Unverified does not mean false. It means the evidence has not been supplied. |
| 4:42.3 | Attribution is inconclusive: there are no observations from before treatment, no comparison areas and no climate series. So GroundTruth makes no causal claim. |

### 4:56 to 5:44: Evidence dossier and audit ledger

| Time | Narration |
|---|---|
| 4:56.8 | Everything the platform knows can be exported as a technical dossier for an auditor. |
| 5:02.5 | The ZIP holds the assessment, claims, observations with scene identifiers, documents and provenance, with a checksum manifest. |
| 5:12.4 | Each download is sealed in an audit ledger. Records are chained to one another, and the page recomputes the chain every time it loads. |
| 5:21.6 | The new report-sealed record appears here. The ledger is not externally timestamped or signed, so it detects alteration, deletion and reordering, but cannot prove when a record was written. |
| 5:34.8 | In testing, altering one stored record in the database made the page report a failed integrity check. Restoring it returned the status to verified. |

### 5:49 to 6:43: Funder, auditor and what comes next

| Time | Narration |
|---|---|
| 5:49.7 | The funder has view access. They can read claims, observations and the ledger, but see no upload or request controls, and the server refuses those actions even when attempted directly. |
| 6:07.5 | The auditor can download the dossier, and check any file they were given against the ledger record that sealed it. |
| 6:14.6 | Here, the file is confirmed byte-for-byte identical to the sealed report. |
| 6:21.9 | This is an early screening tool. Next: observations from before a project began, climate and comparison-area data so attribution becomes possible, and field validation of the satellite values. |
| 6:36.3 | GroundTruth. What was claimed, what was observed, and what cannot yet be shown. |

## What is on screen, per scene

* **The accountability problem**: Public landing page, scrolled slowly. Title cards between scenes are rendered by the recorder inside the page.
* **The NGO: sign in and open a project**: Sign-in form (typed, password masked), welcome state, NGO dashboard, Projects list, the demonstration project's progress bar.
* **Boundary, documents and claim extraction**: NGO dashboard map showing the boundary; Evidence tab with the stored document and its SHA-256; the extracted-statements dialog with five candidates, each already added as a claim.
* **Real satellite observations**: Earth observation tab: the finished Sentinel-2 request, the NDVI chart (EVI toggled and back), the table with `DERIVED` badges and scene ids, back to the chart.
* **Claim assessment**: Verification tab: area claim (partly consistent), greenness claim (consistent), three not-enough-evidence claims, the attribution readiness checklist.
* **Evidence dossier and audit ledger**: Reports tab: the dossier is downloaded live, the ledger gains a `Report sealed` record, the ledger limits text.
* **Funder, auditor and what comes next**: Funder session (read-only evidence and ledger, no controls), auditor session (dossier control, the check-a-file form confirming the file byte for byte), closing card with the roadmap.

## Claims the narration makes, and where each is backed

| Statement | Backing |
|---|---|
| Real Sentinel-2 from Microsoft Planetary Computer, 2021 to 2026, 15 Jan to 15 Mar, at most 20 % cloud, two scenes a year | Request card on screen; stored request row |
| Coverage above 95 % every year | Request result text on screen |
| NDVI +0.051 vs claimed +0.05 | Verification card on screen (observed 0.0512) |
| Boundary about 2,018 ha vs claimed 1,900 ha | Verification card on screen |
| Trajectory is "no clear change" | Assessment (Theil-Sen slope interval spans zero); stated on the overview |
| Altering one ledger record made the check fail, restoring it recovered | Performed on the isolated database; see the audit report. It is described, not shown |
| Funder actions refused by the server | Direct API probes returning 403; see the audit report. Described, not shown |

## Things the narration deliberately does not say

NDVI is never presented as carbon, survival, biodiversity or a project effect; the satellite values are said to be unvalidated; the Kariba illustrative data is not used; nothing is called fraud; the ledger is described as not externally timestamped or signed.
