# Specification curve — pre-registered plan

**Status: NOT RUN.** Blocked on roadmap milestone M3 (first real estimate).

## Question

Does the sign and rough magnitude of the estimated effect survive across
alternative, equally defensible specifications?

## Why this matters more than a headline number

Any single specification can be selected, consciously or not, because it gives
a satisfying answer. A curve across all defensible specifications shows whether
the finding is a property of the data or a property of one analytic choice.

## Dimensions varied

| Dimension | Values |
| --- | --- |
| Indicator | NDVI, EVI, Hansen forest area |
| Pre-period length | 8, 10, 12 years |
| Treatment date | Crediting start, validation date |
| Donor pool cap | 20, 35, 50 |
| Covariate weighting | Equal, rainfall-emphasised, access-emphasised |
| Caliper | 2.0 SD, 3.0 SD, none |
| Ridge penalty | 0.0, 0.01, 0.1 |

Run as a one-at-a-time sweep around a pre-registered centre, not a full
factorial, so each deviation is attributable.

## Reporting

- Every specification is plotted, ordered by estimate
- The centre specification is marked but not privileged
- Sign agreement is reported as a fraction
- The full range is reported as a sensitivity envelope, explicitly labelled as
  such rather than as a confidence interval

## Commitment

Specifications that flip the sign are reported as limitations of that case.
They are never dropped from the set.
