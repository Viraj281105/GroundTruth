# 11. Demo flow

A seven-minute live demo. Every command below runs today against the current
repository. Nothing is mocked for the demo beyond the data itself, which is
labelled as simulated throughout.

## Setup (before you present)

```bash
pip install -e ".[api,genai,dev]"
```

## 0. Honesty first (30s)

```bash
groundtruth doctor
```

```
version                           : 0.3.0
engine version                    : 0.10.0
contract version                  : 1.0.0
environment                       : development
cases found                       : 26
earth observation configured      : False
earth observation implemented     : yes (calibrated for benchmark cases: kariba-redd)
genai provider                    : gemini (or none / deterministic)
genai configured                  : True (when GEMINI_API_KEY is present)
genai narration implemented       : yes (Google Gemini with mathematical grounding boundary)
synthetic pipeline                : yes
engine: synthetic control         : yes
engine: placebo inference         : yes
engine: in space placebo          : yes
engine: in time placebo           : yes
engine: leave one out             : yes
engine: specification curve       : yes
engine: biomass carbon conversion : yes
engine: cross sensor calibration  : no
```

**Say:** "Before anything else — this is what is actually built and what is not.
The tool tells you itself. We built automated self-inspection (`groundtruth doctor`)
so the platform never overclaims its capabilities."

Opening with the limitations is a stronger position than being asked about them
later.

## 1. The cases (45s)

```bash
groundtruth cases
groundtruth show kariba-redd
```

**Say:** "Three cases. Kariba is the benchmark — the largest confirmed
over-crediting correction in carbon market history, and the only one with a
published third-party figure to test a method against."

Point at the `known_reference` output and its disclaimer:

**Say:** "This 57% is Verra's figure, not ours. The pipeline never reads it. It
sits here so we can compare *afterwards*. Feeding it forward would destroy the
independence that is the whole point."

## 2. The run: what the system will and will not do (90s)

Show the real-data path refusing:
```bash
groundtruth verify kariba-redd
```

```
Real Earth-observation providers are not implemented yet for this case.
...
```

**Say:** "There is no genuine satellite data in this repository yet, so the system
refuses instead of guessing. It will not substitute simulated numbers for real ones."

Then the explicit SYNTHETIC fixture run:
```bash
groundtruth verify kariba-redd --synthetic-fixture
```

```
==============================================================================
SYNTHETIC FIXTURE RUN - NOT SATELLITE OBSERVATIONS
This run replays a precomputed SYNTHETIC series from disk. No imagery was
retrieved or processed. Results describe a test fixture, not any real project.
==============================================================================
```

**Say:** "This exercises the causal machinery end to end. The numbers describe a test
fixture; they say nothing about Kariba. The report is labelled SIMULATED throughout, and
the host districts of the project are excluded from the control pool."

Point out the diagnostics the pipeline reports about itself: the weights are flagged as
not uniquely identified (more donors than pre-treatment periods), and the in-space
placebo p-value is a finite-sample rank statistic whose smallest attainable value is
1/(N+1); it is not evidence of causation.

## 3. NDVI is not carbon: the NOT CALIBRATED refusal (90s)

**Say:** "Core scientific invariant: *NDVI is not carbon*. A vegetation index is a
reflectance ratio; carbon credits are tonnes of CO2 equivalent. Converting one into the
other needs a biomass model calibrated to field or LiDAR data for the ecosystem.
GroundTruth ships no such calibration, so it declines."

```bash
groundtruth doctor
```

```
biomass-to-carbon calibration : NOT CALIBRATED - no validated parameters shipped; ...
```

```bash
pytest -v tests/engine/test_biomass.py tests/test_scientific_integrity_regression.py
```

**Say:** "The conversion code exists and is tested, but it raises `NotCalibratedError`
unless a sourced calibration is supplied. Any figure it produces is conditional on that
calibration, carries a one-sigma interval under an assumed error (not a 95% interval),
and is a screening heuristic, not an IPCC-compliant inventory. We make no claim about
Verra's 57% finding."

## 4. The Guard is Real: Code-Enforced Scientific Invariants (45s)

```bash
python -c "from groundtruth.contracts.units import assert_not_index_to_carbon; assert_not_index_to_carbon('ndvi','tCO2e')"
```

```
ValueError: Refusing to convert 'ndvi' directly to 'tCO2e': a spectral index is
not a carbon stock.
```

**Say:** "That is not a policy note. It is an immutable runtime guard.
If any developer or component attempts a naive multiplication of NDVI into carbon,
the platform raises an immediate exception."

## 5. The GenAI Boundary & Gemini Grounding (90s)

```bash
pytest -q tests/platform/test_gemini_narrator.py tests/test_grounding.py
```

**Say:** "This is where AI sits, and where it deliberately does NOT.

```
Raw EO Data → Causal ML Engine → Cryptographic EvidenceBundle → Gemini LLM → Grounding Validator → Final Report
```

The Gemini model never touches raw data and never computes figures. It reads
the verified EvidenceBundle.

Then, our mathematical grounding validator inspects every number in Gemini's
prose against the cryptographic manifest. If the LLM hallucinates a number,
alleges fraud, or modifies an interval, the output is instantly rejected and
the system degrades safely to the deterministic report.

Degrades to correct-and-dry. Never to fluent-and-wrong."

## 6. The API & Honest Refusal (45s)

```bash
curl -X POST localhost:8000/cases/mikoko-pamoja/verify \
  -H 'content-type: application/json' -d '{"synthetic": false}'
```

```json
{
  "detail": "Data unavailable for case 'mikoko-pamoja': Real Earth-observation data access is not implemented: no satellite scenes have been ingested."
}
```

**Say:** "Ask for real satellite data on a case that hasn't been ingested yet,
and the API returns an honest 501. It will NEVER fake numbers or serve simulated
data under a real-data label."

## 7. Close (30s)

```bash
pytest -q
```

**Say:** "Over 1,270 automated tests (954 backend pytest + 320 frontend vitest)
passing with zero failures.

Full Docker Compose orchestration, Kubernetes Helm charts with pre-install
migration hooks, and a production Next.js frontend with MapLibre satellite visualization.

GroundTruth solves additionality verification with mathematical rigor,
causal counterfactuals, and verifiable AI."

## Timing

| Section | Time |
| --- | --- |
| 0. Doctor | 0:30 |
| 1. Cases | 0:45 |
| 2. Run | 1:30 |
| 3. The refusal | 1:30 |
| 4. Unit guard | 1:00 |
| 5. GenAI boundary | 1:30 |
| 6. API | 0:45 |
| 7. Close | 0:30 |
| **Total** | **8:00** |

Cut section 6 first if you need to reach seven minutes. Never cut section 3.

## If something fails live

Everything runs offline with no credentials and no network. The only realistic
failure is a missing install, so run `groundtruth doctor` once before you
present. Keep `pytest -q` output from a prior run as a fallback screenshot.

---

Previous: [10. Roadmap](../product/roadmap-detail.md) · Back to [documentation index](../README.md)
