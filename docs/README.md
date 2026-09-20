# Documentation

GroundTruth's documentation is the project's source of truth for developers,
researchers, future contributors and AI coding agents. It is structured so that
a question has one obvious place to be answered.

---

## Start here

| If you are... | Read |
| --- | --- |
| New to the project | [`PROJECT_CONTEXT.md`](../PROJECT_CONTEXT.md) → [`ARCHITECTURE.md`](../ARCHITECTURE.md) |
| About to write code | [`AGENTS.md`](../AGENTS.md) → [`DEVELOPMENT.md`](../DEVELOPMENT.md) |
| An AI coding agent | [`AGENTS.md`](../AGENTS.md). It is written for you. |
| Reviewing the science | [science/causal-inference.md](science/causal-inference.md) → [science/limitations.md](science/limitations.md) |
| Wondering why something is the way it is | [decisions/](decisions/) |
| Planning work | [`OWNERSHIP.md`](../OWNERSHIP.md) → [product/implementation-plan.md](product/implementation-plan.md) |
| Checking what actually exists | [product/capability-matrix.md](product/capability-matrix.md) |

## Root documents

| File | Contents |
| --- | --- |
| [`README.md`](../README.md) | The project in one page |
| [`PROJECT_CONTEXT.md`](../PROJECT_CONTEXT.md) | Why it exists, who it is for, what it must never claim |
| [`ARCHITECTURE.md`](../ARCHITECTURE.md) | The load-bearing decision and the system map |
| [`AGENTS.md`](../AGENTS.md) | Operating instructions: rules, conventions, where code goes |
| [`DEVELOPMENT.md`](../DEVELOPMENT.md) | Setup, commands, testing, debugging, troubleshooting |
| [`OWNERSHIP.md`](../OWNERSHIP.md) | Responsibility matrix, coordination points, definition of done |
| [`ROADMAP.md`](../ROADMAP.md) | NOW → MVP → Stage 2 → Stage 3 → long term |
| [`GLOSSARY.md`](../GLOSSARY.md) | Terms that mean something specific here |
| [`CONTRIBUTING.md`](../CONTRIBUTING.md) | How to contribute, and the non-negotiable rules |
| [`SECURITY.md`](../SECURITY.md) | Threat model and what is not secured yet |
| [`CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md) | Conduct, including scientific-integrity obligations |
| [`CHANGELOG.md`](../CHANGELOG.md) | What changed, when |

## Architecture

| Document | Contents |
| --- | --- |
| [system.md](architecture/system.md) | System architecture, stages, implementation status |
| [contract.md](architecture/contract.md) | **The engine/platform contract, in full** |
| [backend.md](architecture/backend.md) | Platform modules, request lifecycle, persistence plan |
| [frontend.md](architecture/frontend.md) | Views, UI rules, data flow |
| [worker.md](architecture/worker.md) | Job execution, retries, cancellation |
| [earth-observation.md](architecture/earth-observation.md) | EO layer, sources, hazards, extension points |
| [causal.md](architecture/causal.md) | Estimator structure, plug-in points, the verdict gate chain |
| [evidence.md](architecture/evidence.md) | Evidence object, provenance graph, the target model |
| [genai.md](architecture/genai.md) | Where the model sits and how grounding is enforced |
| [monitoring.md](architecture/monitoring.md) | Continuous monitoring (future) |

## Science

| Document | Contents |
| --- | --- |
| [methodology.md](science/methodology.md) | The counterfactual approach, stage by stage |
| [causal-inference.md](science/causal-inference.md) | Estimand, estimators, assumptions, **why NDVI is not carbon** |
| [validation.md](science/validation.md) | Pre-registered validation plan |
| [limitations.md](science/limitations.md) | What is not built, and where the method could be wrong |

## Data

| Document | Contents |
| --- | --- |
| [sources.md](data/sources.md) | Products, assets, and what each cannot tell you |
| [conventions.md](data/conventions.md) | Spatial, temporal and quality conventions |

## Product

| Document | Contents |
| --- | --- |
| [problem.md](product/problem.md) | The problem in depth, with sources |
| [capability-matrix.md](product/capability-matrix.md) | **Implemented / planned / future, per capability** |
| [implementation-plan.md](product/implementation-plan.md) | Phased tasks, owners, dependencies, parallel order |
| [roadmap-detail.md](product/roadmap-detail.md) | Milestone detail with exit criteria |

## Engineering

| Document | Contents |
| --- | --- |
| [testing.md](engineering/testing.md) | Testing strategy and what a good test looks like here |
| [configuration.md](engineering/configuration.md) | Settings, secrets, environments |

## Security

| Document | Contents |
| --- | --- |
| [security/architecture.md](security/architecture.md) | Trust boundaries, secrets, the GenAI boundary as a control, planned controls |
| [`SECURITY.md`](../SECURITY.md) | Threat model, reporting, what is not secured yet |

## Decisions

[decisions/](decisions/) — eleven ADRs covering the monorepo, the engine/platform
boundary, the analysis contract, the evidence object, provenance,
reproducibility, the GenAI boundary, job architecture, data management,
deployment and the unit of analysis.

## Competition

| Document | Contents |
| --- | --- |
| [strategy.md](competition/strategy.md) | PCCOE IGC 2026 positioning and hard questions |
| [demo-flow.md](competition/demo-flow.md) | A seven-minute demo that runs today |

## Research

[research/](research/) — reading notes and literature relevant to the method.

---

## Three rules that recur everywhere

1. **Observed change is not causal effect.** Everything in the pipeline exists
   to close that gap honestly, and to state what is left open.
2. **NDVI is not carbon.** Converting a spectral index to a mass requires a
   biomass model with its own error budget, and the code refuses to do it
   implicitly.
3. **Model divergence is not fraud.** A gap between an independent estimate and
   a claim means the claim warrants accredited review. Nothing in a satellite
   time series can establish intent.

## Status discipline

**No analysis of a real project has been run.** Every number the pipeline
currently produces comes from a simulated fixture and is labelled as such. If
you add a capability, update
[product/capability-matrix.md](product/capability-matrix.md) in the same change.
