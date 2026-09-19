# Continuous monitoring architecture

**Status: FUTURE. None of this is built.** The extension points exist; the
capability does not.

The long-term shift: **verify once → keep watching.** A verification is a
snapshot. A project that looked sound in 2022 can be cleared in 2024, and a
buyer holding those credits has no mechanism to find out.

---

## Why the groundwork already exists

Continuous monitoring is mostly *re-running a stored specification and
comparing*. Three existing design decisions make that cheap rather than a
rewrite:

| Existing | Why it matters here |
| --- | --- |
| `spec_hash` (ADR-006) | A stored spec can be replayed exactly. Re-analysis is "same spec, later window". |
| `DatasetRef` pinning (ADR-009) | The delta between two runs is attributable to new data rather than to a silently reprocessed archive. |
| Immutable `EvidenceBundle` (ADR-004) | Two bundles diff cleanly by evidence id. |
| Job lifecycle (ADR-008) | Scheduled work is the same machinery as user-requested work. |

None of this was built *for* monitoring. It is a consequence of taking
reproducibility seriously, which is the usual pattern: the discipline pays
somewhere you did not plan for.

---

## Shape

```
schedule ──► replay stored spec with an extended window
                      │
                      ▼
             run_analysis (unchanged)
                      │
                      ▼
             new EvidenceBundle
                      │
                      ▼
             diff against the previous bundle by evidence id
                      │
         ┌────────────┴────────────┐
         ▼                         ▼
   material change            no material change
         │                         │
         ▼                         ▼
   raise a review trigger     record and continue
```

**The engine does not change.** Monitoring is a platform capability built on
scheduling, storage and comparison — all Bhumi-side.

---

## Capabilities and what each needs

| Capability | Needs | Engine change? |
| --- | --- | --- |
| Periodic re-analysis | Scheduler, stored specs, result history | No |
| Restoration progress tracking | Bundle diff over time | No |
| Deforestation alerts | GFW integrated alerts as a provider | New indicator (minor) |
| Fire events | FIRMS / MCD64 as a provider | New indicator (minor) |
| Ecological deterioration | Trend test over successive estimates | New estimator |
| Intervention changes | Registry metadata monitoring | No — platform |
| Anomaly detection | Deviation from a project's own trajectory | New estimator |
| Project health score | Aggregation over evidence | Reporting only |
| Automated review triggers | Threshold rules over diffs | No — platform |

---

## Design constraints

These are the parts that are easy to get wrong, and are worth writing down
before anyone builds it.

**Distinguish a real change from a methodological one.** If the engine version
changed between runs, a bundle difference may be a methodology fix rather than a
change on the ground. `EngineRef` is stored with every result precisely so a
diff can say which it is. **A diff across engine versions must be labelled as
not comparable** rather than reported as an ecological change.

**Alerts must inherit the same restraint as verdicts.** "This project warrants
re-review" is the strongest claim available. Not "this project is failing", and
never anything implying misconduct. The same prohibited-assertion rules apply to
alert copy as to reports.

**Alert fatigue is a correctness problem.** A monitoring system that fires
constantly gets muted, and a muted system is worse than none because it creates
false assurance. Thresholds must be calibrated against the placebo distribution
— the same logic as the verdict gate chain: a change is worth reporting when it
is unusual relative to what comparable untreated regions did.

**Cost scales with frequency × projects.** Monthly re-analysis of 1,000 projects
is 12,000 analyses a year, each a placebo suite. `spec_hash` caching, incremental
windows and cheap screening before expensive confirmation are all required. This
is the main reason the worker is a separate process.

**Seasonality is not deterioration.** A monthly cadence on an annual-composite
indicator will mostly measure phenology. Either the cadence matches the
indicator's temporal resolution, or the comparison is year-over-year.

---

## What must not be built into this

| Not building | Why |
| --- | --- |
| Automated de-listing or credit suspension | No project should lose status on a screening signal |
| Real-time alerting on raw imagery | The unit of analysis is a counterfactual estimate, not a pixel change |
| Alerts to third parties without the developer seeing them first | Basic fairness, and it is how a screening tool earns cooperation |

---

## Prerequisites

Monitoring is meaningless until a single analysis is trustworthy. In order:

1. A real analysis on real data (MVP)
2. Validated against Kariba
3. Persistence and job infrastructure (Stage 2)
4. Automated ingestion so projects are onboarded without hand-configuration
   (Stage 3)
5. Only then: scheduling and diffing

Building this earlier would produce a system that continuously monitors
something we have not yet shown we can measure once.
