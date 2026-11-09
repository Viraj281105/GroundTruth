# Continuous Monitoring Architecture

**Platform**: `packages/groundtruth/src/groundtruth/platform/compare/` & `jobs/`  
**Core Concept**: Shift from static snapshot verification to perpetual, automated observation.

A project verified in 2022 can suffer illegal logging, canopy dieback, or severe drought in 2024. Continuous monitoring enables GroundTruth 2.0 to re-evaluate interventions automatically as new satellite overpasses and climate grids arrive, detecting reversals before credits are traded.

```mermaid
flowchart TD
    subgraph Trigger["1. Automated Schedule Trigger"]
        Cron["Continuous Monitoring Cron<br/>(Monthly / Annual Satellite Composites)"]
        Event["New Earth Observation Ingestion<br/>(Sentinel-2 / Landsat-9 Overpass)"]
    end

    subgraph Execution["2. Automated Spec Replay"]
        StoredSpec["Retrieve Stored Specification<br/>(Pinned Request & Unit Boundary)"]
        ExtendWindow["Extend Analysis Window<br/>(e.g., append post_end + 1 year)"]
        WorkerQueue["Submit to Asynchronous Worker Queue"]
        WorkerRun["Execute run_analysis()<br/>(Engine runs with identical code)"]
        NewBundle["Emit New Immutable EvidenceBundle"]
    end

    subgraph Comparison["3. Algorithmic Bundle Comparison (platform/compare/)"]
        PriorBundle["Retrieve Prior Verified Bundle"]
        DiffEngine["Diff Engine by Evidence ID<br/>• Value shifts (relative tolerance 1e-9)<br/>• Confidence bound movements<br/>• Non-Comparability Guards"]
    end

    subgraph Evaluation["4. Review Triggers & Alert Delivery"]
        AlertRule{"Evaluate Alert Rules<br/>• Significant Canopy Drop (>5%)?<br/>• Post-Treatment SCM Divergence?<br/>• Severe SPI-12 Drought Spike?"}
        ReviewFlag["Raise Automated Due-Diligence Review Flag<br/>(Dispatch Webhook & Funder Notification)"]
        StableLog["Record Stable Monitoring Checkpoint<br/>(Append to Project Audit History)"]
    end

    Cron --> StoredSpec
    Event --> StoredSpec
    StoredSpec --> ExtendWindow --> WorkerQueue --> WorkerRun --> NewBundle
    NewBundle --> DiffEngine
    PriorBundle --> DiffEngine
    DiffEngine --> AlertRule
    AlertRule -- Threshold Exceeded --> ReviewFlag
    AlertRule -- Within Tolerance --> StableLog
```

![Funder Dashboard](../product/screens/funder-dashboard.png)

---

## 1. Why GroundTruth 2.0 Makes Monitoring Seamless

Continuous monitoring is architecturally trivial in GroundTruth 2.0 because of foundational design choices:

| Architectural Primitive | Foundation | Role in Continuous Monitoring |
| :--- | :--- | :--- |
| **`spec_hash`** | ADR-006 | Guarantees that re-running an analysis with an extended window executes the exact same mathematical model without manual parameter re-entry. |
| **Pinned `DatasetRef`** | ADR-009 | Ensures any measured delta is caused by real ecological changes on the ground, not silent upstream archive reprocessing. |
| **Immutable `EvidenceBundle`** | ADR-004 | Prior and current states can be diffed element-by-element across stable dotted IDs. |
| **Decoupled Jobs** | ADR-008 | Scheduled re-runs execute on existing background workers without consuming API gateway resources. |

---

## 2. Algorithmic Run Comparison (`platform/compare/`)

The comparison service evaluates differences across two verified runs, categorizing evidence identifiers as `added`, `removed`, `changed`, or `unchanged`.

```mermaid
graph TD
    CompReq["GET /runs/compare?baseline={runA}&candidate={runB}"] --> Guards{"Evaluate Non-Comparability Guards"}
    
    Guards -- "Different Case IDs" --> NonComp["Return comparable: false<br/>Reason: different_case"]
    Guards -- "One Simulated, One Observed" --> NonComp2["Return comparable: false<br/>Reason: different_data_mode"]
    Guards -- "Different Engine Versions" --> NonComp3["Return comparable: false<br/>Reason: different_engine_version"]
    Guards -- "Contract Major Mismatch" --> NonComp4["Return comparable: false<br/>Reason: different_contract_major"]
    Guards -- "Run Lacks Bundle (Refused/Failed)" --> NonComp5["Return comparable: false<br/>Reason: no_bundle"]
    
    Guards -- "All Guards Satisfied" --> ExecuteDiff["Execute Evidence-by-Evidence Diff"]
    ExecuteDiff --> DiffOutput["Emit Diff Matrix:<br/>• Numerical changes (|delta| > 1e-9)<br/>• Confidence interval shifts<br/>• Neutral verdict diff<br/>• Warning transitions"]
```

### 2.1 The Non-Negotiable Non-Comparability Guards
A measurement change between two runs could stem from methodology revisions rather than ecological reality. To protect due-diligence teams from measurement artifacts, the engine strictly refuses to generate a diff if:
- `different_engine_version`: The runs were executed on different versions of the analytical engine.
- `different_data_mode`: Comparing a simulated benchmark run against a real observation run.
- `different_case`: The runs evaluate different geographic projects.

---

## 3. Alert Triggers & Reversal Detection

When new observations are processed, threshold rules detect environmental reversal events:

```mermaid
stateDiagram-v2
    [*] --> MonitorIdle: Awaiting New Overpass
    MonitorIdle --> ReplaySpec: Scheduled Window Extension
    ReplaySpec --> DiffBundles: Generate Evidence Delta
    
    DiffBundles --> NormalCheck: Delta Within Baseline Bounds
    NormalCheck --> MonitorIdle: Log Green Status Checkpoint

    DiffBundles --> ReversalDetected: Significant Canopy Decline (>10%)
    ReversalDetected --> IssueAuditAlert: Trigger Review Flag (Amber)
    
    DiffBundles --> ClimateShockDetected: SPI-12 Drought Spike (SPI < -1.5)
    ClimateShockDetected --> AnnotateClimate: Tag Decline as Weather-Driven (Do Not Penalize Project)
    
    IssueAuditAlert --> NotifyFunder: Notify Funder & Auditor Personas
    AnnotateClimate --> NotifyFunder
```

* **Canopy Loss Alert**: Detects sharp negative shifts in `effect.point_estimate` or `assessment.vegetation_trajectory`.
* **Climate Attribution Isolator**: Checks whether vegetation decline coincides with severe regional drought ($\text{SPI-12} < -1.5$). If the regional synthetic control also declines, the reversal is attributed to drought stress rather than project failure.
