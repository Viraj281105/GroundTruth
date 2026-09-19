# Security architecture

The threat model, reporting process and current gaps live in
[`SECURITY.md`](../../SECURITY.md). This document covers the *design* —
how the system is structured to make certain failures impossible rather than
merely unlikely.

**Status: the design is settled; most controls are not built.** The service is
not exposed publicly, which bounds current risk — but "not exposed yet" is a
deployment fact, not a security control.

---

## Trust boundaries

```
 browser ──HTTPS──► API ──► engine (no I/O, no credentials)
    │                │
    │                ├──► database        credentials from env
    │                ├──► object storage  credentials from env
    │                ├──► Earth Engine    service account from env
    │                └──► GenAI provider  API key from env
    │
 untrusted input     the only place credentials exist
```

**The engine holds no credentials and opens no sockets.** That is not primarily
a security decision — it comes from reproducibility (ADR-002, ADR-006) — but it
removes the entire analytical core from the credential-handling surface. The
engine cannot leak a key it never sees.

## Secrets

| Control | Status |
| --- | --- |
| Credentials as `SecretStr`, never logged | Implemented |
| `.env` gitignored, `.env.example` names only | Implemented |
| `groundtruth doctor` reports presence, never value | Implemented |
| Platform secret store in production | Planned |
| Rotation procedure documented | Planned |

If a key is committed: **rotate at the provider first**, then rewrite history. A
key removed from history is still a key that was published.

## Input handling

| Surface | Treatment |
| --- | --- |
| API request bodies | Validated by Pydantic at the boundary; structured errors, no stack traces |
| Case YAML | Validated on load; unknown fields ignored, malformed rejected |
| Dataset responses | Treated as data; non-finite values rejected rather than imputed |
| GenAI output | **Verified, never trusted.** See below. |

## The GenAI boundary as a security control

The model receives only the evidence bundle and the deterministic report —
never raw web content, user documents or dataset metadata. That removes the
usual prompt-injection surface by construction.

If a future feature lets user-supplied text reach a prompt (a project
description, an analyst note), it is data rather than instruction, **and the
grounding verifier still applies to the output**. The verifier is the last line:
even a fully compromised prompt cannot get an ungrounded number or an accusation
into a published report, because the check runs on the output rather than
trusting the input.

This is the general pattern worth preserving — validate the output, not only the
input.

## Planned controls

| Control | Where it lands |
| --- | --- |
| Authentication on write endpoints | Production hardening |
| Rate limiting on analysis submission | Production hardening |
| Audit log: who requested which analysis | Production hardening |
| Security headers | Production hardening |
| Dependency vulnerability scanning | CI |
| Evidence bundle signing | Future |

## Evidence integrity

Provenance proves **derivation**, not **authenticity**. Anyone with write access
to the store could alter a bundle, and fingerprints would be recomputed.

Signing closes that gap and is a future item. Until then, integrity rests on
access control and on bundles being immutable by convention (a re-run is a new
`run_id`, never an update) — which is enforced in the store design but not
cryptographically.

## Scientific integrity as a security property

The failure that matters most here is not a conventional vulnerability. It is
**the system producing a confident, wrong, publishable claim about a real
project**.

The controls are the same rules enforced everywhere else:

| Rule | Enforcement |
| --- | --- |
| Simulated data cannot be labelled observed | `AnalysisRequest` validator |
| Spectral indices cannot become carbon | `assert_not_index_to_carbon` |
| Generated text cannot contain unverifiable numbers | Grounding verifier |
| Generated text cannot allege wrongdoing | Prohibited-assertion patterns |
| A failed robustness gate cannot become a weak positive | Verdict gate chain |
| An unavailable provider cannot silently serve fixtures | `DataUnavailableError`, no fallback |

Each is enforced in code and asserted in the CI `scientific-integrity` job,
because a convention would not survive a deadline.
