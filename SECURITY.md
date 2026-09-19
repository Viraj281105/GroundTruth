# Security

## Reporting a vulnerability

Open a GitHub issue for anything non-sensitive. For anything that could be
exploited before a fix ships, contact the maintainers directly rather than
filing publicly:

- Viraj Jadhao — viraj.jadhao28@gmail.com
- Bhumi Sirvi — bhumisirvi2735@gmail.com

We will acknowledge within a few days. This is a student research project with
no formal SLA; we will be honest about timelines rather than promise one we
cannot meet.

## Threat model

GroundTruth handles no personal data and stores no user accounts today. The
assets worth protecting are:

| Asset | Threat | Status |
| --- | --- | --- |
| Earth-observation API credentials | Leak via logs, commits or error messages | Mitigated: secrets are `SecretStr`, never logged; `.env` gitignored |
| GenAI provider keys | Same | Mitigated the same way |
| Evidence integrity | A result altered after the fact, or a simulated run presented as real | Partial: provenance fingerprints and `data_mode` validation. Signing is a future item. |
| Report integrity | A model inserting an unverifiable figure or an accusation | Mitigated: grounding verification with fallback to the deterministic renderer |
| Availability | Unbounded analysis requests exhausting compute | **Not mitigated.** No rate limiting or auth yet; the service is not exposed beyond a demo. |

## Specific concerns

### Secrets

Every credential is read from the environment into a `SecretStr` on
`platform.config.Settings`. Nothing logs a secret value. `.env` is gitignored;
`.env.example` documents the names only. `groundtruth doctor` reports whether a
credential is *present*, never what it is.

If a key is ever committed, rotate it at the provider first, then rewrite
history. Rotation first — a key removed from history is still a key that was
published.

### Prompt injection

The GenAI layer is downstream of every number and receives only the evidence
bundle and the deterministic report — never raw web content, user-supplied
documents or dataset metadata. That removes the usual injection surface.

If a future feature lets a user supply text that reaches a prompt (a project
description, an analyst note), it must be treated as data, not instruction, and
the grounding verifier still applies to the output. The verifier is the last
line: even a fully compromised prompt cannot get an ungrounded number or an
accusation into a published report, because the check runs on the output rather
than trusting the input.

### Supply chain

Dependencies are pinned by lower bound and installed from PyPI. The engine core
depends only on numpy, pandas and pydantic; heavy geospatial and provider SDKs
sit behind optional extras so they are absent unless needed. Fewer installed
packages is fewer things to audit.

### Data handling

Project boundaries and Earth-observation data are public or licensed for
research use. The contents of `data/` are gitignored: large binary rasters do
not belong in git, and the licence terms of some products do not permit
redistribution.

## What is not secured yet

Stated plainly, because pretending otherwise would be worse:

- No authentication or authorisation on the API
- No rate limiting
- No audit log of who requested which analysis
- No signing of evidence bundles
- No CSRF protection (no cookie-based session exists yet)
- No dependency vulnerability scanning in CI

These are tracked as production-hardening work. The service is not exposed
publicly, so current risk is bounded — but "not exposed yet" is a deployment
fact, not a security control, and it will stop being true.

## Scientific integrity as a security property

One class of failure matters more here than conventional vulnerabilities: the
system producing a confident, wrong, publishable claim about a real project.

The controls are the same rules enforced everywhere else — simulated data cannot
be labelled observed, spectral indices cannot become carbon, generated text
cannot contain unverifiable numbers or accusations, and a failed robustness gate
cannot become a weak positive. They are enforced in code and asserted in CI
because a convention would not survive a deadline.
