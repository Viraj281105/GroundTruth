# GroundTruth

**Independent Causal Verification for Climate Restoration & Carbon-Credit Claims**

GroundTruth is a research-grade prototype for independently screening restoration and carbon-credit claims using multi-temporal Earth observation, causal inference, uncertainty analysis, and evidence-grounded Generative AI.

## PCCOE IGC 2026
- Theme: AI for Climate Change
- Domain: Biodiversity, Ecosystem Conservation & Climate Awareness
- Topic: Ecosystem Restoration
- Official title: Restoration & Carbon-Credit Causal Impact Verifier
- Team: Viraj Jadhao, Bhumi Sirvi

## Core idea
Before/after satellite change is not enough. GroundTruth constructs a matched counterfactual from comparable non-project regions, estimates the project's incremental ecological effect, quantifies uncertainty, and turns verified analytical outputs into a traceable human-readable report.

> GroundTruth is a screening and decision-support system, not a replacement for accredited field auditing and does not determine fraud.

## Repository status
This repository starts as the system scaffold. Stage 2 development is planned around the Kariba REDD+ case, with Southern Cardamom and Mikoko Pamoja as supporting validation cases.

## Architecture
`Project claim → Earth observation → preprocessing → donor matching → synthetic control → causal effect → placebo/uncertainty → evidence report`

## Planned stack
- Python, FastAPI
- Google Earth Engine / Sentinel-2 / Landsat / Global Forest Watch
- GeoPandas, rasterio, xarray, pandas, NumPy, scikit-learn
- Causal inference / synthetic control / DiD
- PostgreSQL + PostGIS where persistence is needed
- React/Next.js frontend for the prototype
- LLM/GenAI reporting layer with strict grounding to verified analytical outputs

## Research principles
1. Never equate greenness with carbon tonnes.
2. Never state fraud from model output.
3. Report intervals and robustness checks instead of false precision.
4. Preserve provenance for every reported number.
5. Separate deterministic analysis from Generative AI narration.

## Project documentation
See `docs/` for the problem definition, methodology, data sources, validation plan, architecture, roadmap, and demo plan.
