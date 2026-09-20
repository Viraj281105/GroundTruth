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
engine version                    : 0.3.0
contract version                  : 1.0.0
environment                       : development
cases found                       : 3
earth observation configured      : False
earth observation implemented     : no - see docs/product/roadmap-detail.md M1
genai provider                    : none
genai configured                  : False
genai narration implemented       : no - deterministic renderer is used
synthetic pipeline                : yes
engine: synthetic control         : yes
engine: placebo inference         : yes
engine: leave one out             : yes
engine: specification curve       : no
engine: biomass carbon conversion : no
```

**Say:** "Before anything else — this is what is actually built and what is not.
The tool tells you itself. Everything you are about to see runs on simulated
data, and it will keep saying so."

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

## 2. The run (90s)

```bash
groundtruth verify kariba-redd --synthetic
```

Let the banner land:

```
==============================================================================
SIMULATED DATA RUN
This run uses the synthetic fixture provider. The numbers below describe a
test fixture and say nothing about any real project.
==============================================================================
```

Walk the evidence table: point estimate with a sensitivity envelope, pre-period
RMSPE, post/pre RMSPE ratio, permutation p-value, donor counts, balance, and the
leave-one-out shift.

**Say:** "Every row has a unit, an interval where one exists, a method and a
source. Nothing is a bare number."

## 3. The refusal — the centrepiece (90s)

Point at the verdict:

> **Outcome: Inconclusive** — A robust incremental effect on the observed
> indicator was estimated, but the developer's claim is not expressed in
> commensurable units, so no comparison against the claim can be made without a
> biomass conversion step.

**Say:** "This is the most important slide in the demo.

The pipeline found a robust effect. It passed every robustness gate — donor
count, pre-treatment fit, placebo, leave-one-out, covariate balance. And it
still refuses to give you a verdict against the claim.

Why? The effect is on NDVI. The claim is in tonnes of CO2. NDVI is a reflectance
ratio; carbon is a mass. There is no arithmetic that turns one into the other —
it needs a biomass model with its own error budget, and we have not built that
yet.

Most systems would have multiplied by something and given you a confident
percentage. This one tells you it cannot, and tells you exactly what is
missing."

## 4. The guard is real, not a comment (60s)

```bash
python -c "from groundtruth.contracts.units import assert_not_index_to_carbon; assert_not_index_to_carbon('ndvi','tCO2e')"
```

```
ValueError: Refusing to convert 'ndvi' directly to 'tCO2e': a spectral index is
not a carbon stock.
```

**Say:** "That is not a note in the documentation. It is enforced in code, and a
test asserts it for every index and every carbon unit."

## 5. The GenAI boundary (90s)

```bash
pytest -q tests/test_grounding.py
```

**Say:** "This is where the AI sits, and where it does not.

The analytical engine produces a verified evidence bundle. The language model
receives that bundle and narrates it. It never sees raw data, and it never
computes anything.

Then every number it writes is checked back against the bundle. If it invents a
figure, or alleges fraud, or says something is proven, the output is thrown away
and we publish the deterministic report instead.

These tests include a narrator that hallucinates an over-issuance figure and
alleges fraud. Watch what happens: the output is discarded, and the invented
number does not appear anywhere in the published report.

The system degrades to correct-and-dry. Never to fluent-and-wrong."

## 6. The API (45s)

```bash
uvicorn apps.api.main:app --port 8000
```

Open `http://localhost:8000/docs`, then:

```bash
curl -X POST localhost:8000/cases/kariba-redd/verify \
  -H 'content-type: application/json' -d '{"synthetic": false}'
```

```json
{"detail": "Observed-data verification is not implemented: the Earth Engine
reducer chain has not landed. Set synthetic=true to exercise the pipeline on
simulated data."}
```

**Say:** "Ask for real data and you get a 501. It will not serve you simulated
numbers under a real-data label."

## 7. Close (30s)

```bash
pytest -q
```

**Say:** "163 tests, CI on three Python versions, including a job that asserts
the claims we just made: no index is reported as carbon, the GenAI layer cannot
invent a number, and no case claims to have been analysed when it has not.

What is built is the machinery, and it is correct — it recovers a known effect
and distinguishes it from a null. What is next is pointing it at real
Sentinel-2 data and running Kariba for real. Whatever it says, we will publish
it."

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
