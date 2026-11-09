# GroundTruth 2.0 — Security & Scientific Integrity Architecture

**One platform. Four perspectives. One scientifically consistent source of truth.**  
*Comprehensive security policy, multi-tenant threat model, cryptographic provenance, and scientific integrity controls for GroundTruth 2.0.*

---

## 1. Security Philosophy: Scientific Integrity as a Core Security Primitive

In conventional software platforms, security is confined to authentication, authorization, and data encryption. For GroundTruth 2.0, **scientific integrity is an active security property**:

```mermaid
flowchart TD
    subgraph SecurityPerimeter["GroundTruth Security Perimeter"]
        direction TB
        C1["1. Network & Identity Security<br/>(Scrypt · Sessions · RBAC · CORS/CSRF)"]
        C2["2. Multi-Tenant Isolation<br/>(Organization Boundaries · Cross-Org 403)"]
        C3["3. Scientific Gateways (Fail-Closed)<br/>(DataUnavailableError · HTTP 501)"]
        C4["4. GenAI Grounding Verifier<br/>(Anti-Injection · Anti-Defamation)"]
        C5["5. Cryptographic Evidence Chain<br/>(SHA-256 Provenance · Immutability)"]
    end
```

A vulnerability that allows an actor to inject fabricated satellite data, claim unearned carbon additionality, or disguise simulated benchmark results as empirical observations represents an existential failure of the platform. GroundTruth's security architecture treats scientific misrepresentation with the same severity as arbitrary code execution.

---

## 2. Threat Modeling & Risk Mitigation Matrix

| Asset / Boundary | Threat Vector | Architectural Mitigation | Status |
|---|---|---|---|
| **User Credentials** | Credential stuffing, brute-force attacks, timing attacks | Scrypt key derivation ($N=32768, r=8, p=1$), constant-time password comparison, rate-limiting (5 failures/window). | **Enforced & Tested** |
| **Session Security** | Session hijacking, replay, XSS token extraction | Server-side cryptographic sessions, HttpOnly, SameSite=Lax, Secure cookies, instant revocation on logout/password reset. | **Enforced & Tested** |
| **Tenant Boundaries** | Unauthorized cross-tenant project querying or modification | Row-level tenant filtering on all queries; returns `HTTP 403 Forbidden` with immutable audit logging. | **Enforced & Tested** |
| **Scientific Data Integrity** | Serving fabricated or hand-typed satellite rasters | Task 5/5B audit quarantined all synthetic Landsat caches; fail-closed gateway raises `DataUnavailableError` (HTTP 501). | **Enforced & Tested** |
| **Causal Estimates** | SUTVA contamination (admitting project host districts into donor pool) | Programmatic exclusion of host districts and 10 km leakage belt; SMD balance tests gate the verdict. | **Enforced & Tested** |
| **GenAI Narration** | Prompt injection, hallucinated numbers, defamatory fraud allegations | Regex numeric grounding verifier restricts values to $\pm 2\%$ of `EvidenceBundle`; blocks fraud/criminal allegations; fallback to deterministic renderer. | **Enforced & Tested** |
| **Cryptographic Provenance** | Post-hoc tampering with analysis results | `spec_hash` Blake2b fingerprinting and SHA-256 evidence bundle checksums stored with write-once semantics. | **Enforced & Tested** |

---

## 3. Multi-Tenant Authorization & RBAC Architecture

GroundTruth 2.0 enforces strict tenant isolation across organizations. All incoming requests are authenticated and authorized before reaching business logic:

```mermaid
sequenceDiagram
    autonumber
    actor Client as Authenticated User (Org A)
    participant Auth as Session & RBAC Middleware
    participant Audit as Immutable AuditLog
    participant DB as Tenant-Isolated DB (Org B Data)

    Client->>Auth: GET /projects/{project_id_of_org_b}
    Auth->>Auth: Verify Session & Inspect Organization ID
    alt Organization Match
        Auth->>DB: Execute Query with tenant_id filter
        DB-->>Client: 200 OK (Project Data)
    else Tenant Mismatch (Cross-Tenant Access Attempt)
        Auth->>Audit: Record Security Violation (USER_ID, TARGET_ORG_B, IP, Action: DENIED)
        Auth-->>Client: HTTP 403 Forbidden (Cross-Tenant Access Prohibited)
    end
```

### Visual Proof of Boundary Enforcement
When an authenticated user attempts to inspect project parcels belonging to an external organization, the application immediately blocks access and renders the security denial state:

![Cross-Tenant Access Denied](docs/product/screens/cross-org-denied.png)

---

## 4. Authentication, Password Hashing & Session Lifecycle

GroundTruth rejects lightweight hashing algorithms (such as plain MD5 or SHA-256) in favor of memory-hard cryptography:

### A. Scrypt Password Hashing (`groundtruth/platform/auth/passwords.py`)
- **Parameters:** $N = 32768$ (CPU/memory cost), $r = 8$ (block size), $p = 1$ (parallelization), producing a 64-byte key.
- **Salt Generation:** 16 cryptographically secure random bytes via `secrets.token_bytes(16)`.
- **Timing Attack Mitigation:** Constant-time hash verification via `hmac.compare_digest`.
- **Rehash Migration:** Passwords hashed with outdated work parameters are automatically re-hashed upon successful login.

### B. Session Lifecycle & Cookie Security
- **Cookie Flags:** `HttpOnly = True` (blocks JavaScript access via XSS), `SameSite = "lax"`, `Secure = True` (in production).
- **Session Revocation:** Changing a password or calling `POST /auth/logout` revokes all active session tokens immediately in PostgreSQL.
- **Rate Limiting:** Failed authentication attempts trigger exponential backoff and lockouts after 5 consecutive failures per client IP.

---

## 5. Fail-Closed Scientific Gateways & Audit Remediation

The Task 5/5B independent audits demonstrated that permissive data accessors can lead to the silent presentation of fabricated data. GroundTruth 2.0 addresses this with **fail-closed gateways**:

```mermaid
flowchart TD
    Req["Request: data_mode='observed'"] --> Gateway["earth_engine_access()"]
    Gateway --> CheckRasters{"Are all historical rasters<br/>(2001-2022) present on disk?"}

    CheckRasters -- "No / Incomplete" --> FailClosed["Raise DataUnavailableError<br/>HTTP 501: Data Incomplete"]
    FailClosed --> Stop["Execution Terminated<br/>Zero Synthetic Values Exposed"]

    CheckRasters -- "Yes" --> VerifyHashes{"Do SHA-256 hashes<br/>match STAC assets?"}
    VerifyHashes -- "Mismatch" --> FailCorrupt["Raise DataCorruptedError (HTTP 500)"]
    VerifyHashes -- "Valid" --> Execute["Proceed to Causal Estimation"]
```

```python
# contracts/ports.py & platform/datasets/access.py
if not is_spatially_complete or missing_pre_treatment_panels:
    raise DataUnavailableError(
        "Earth Engine real pre-treatment panel incomplete for whole AOI. "
        "Refusing to manufacture synthetic values under REAL label."
    )
```

By failing closed, GroundTruth guarantees that an incomplete dataset produces an **honest refusal (HTTP 501)** rather than a fabricated calculation.

---

## 6. Generative AI Defense & Grounding Verification

GroundTruth isolates the Gemini LLM downstream of the analytical engine. Generated text is treated as untrusted input and subjected to rigorous grounding verification:

```mermaid
flowchart LR
    Bundle["Immutable EvidenceBundle"] --> GenAI["Gemini 1.5 Narrator"]
    GenAI --> Output["Generated Draft Report"]
    Output --> Verifier["Grounding & Content Verifier"]
    
    Verifier --> Test1{"Numeric Values within<br/>±2% of EvidenceBundle?"}
    Test1 -- "Fail" --> Reject["Discard LLM Text!<br/>Publish Deterministic Report"]

    Test1 -- "Pass" --> Test2{"Contains Fraud, Criminal,<br/>or Certainty Allegations?"}
    Test2 -- "Yes" --> Reject
    Test2 -- "No" --> Publish["Publish Grounded Narrative"]
```

### Prohibited Vocabulary Enforcement
`groundtruth.contracts.grounding` scans drafts and immediately rejects text containing defamatory or ungrounded accusations:
- **Fraud/Scam Synonyms:** "fraud", "scam", "hoax", "grift", "swindle", "ponzi", "sham".
- **Criminal Accusations:** "embezzlement", "bribery", "corruption", "theft", "kickback", "laundering".
- **Unearned Certainty:** "conclusively proved", "undeniable", "absolute certainty".

---

## 7. Vulnerability Disclosure & Bug Bounty

If you discover a security vulnerability or scientific integrity bypass in GroundTruth 2.0, please contact the maintainers directly:

- **Viraj Jadhao:** `viraj.jadhao28@gmail.com`
- **Bhumi Sirvi:** `bhumisirvi2735@gmail.com`

We will acknowledge receipt within 48 hours and provide a coordinated disclosure plan.

---

> GroundTruth 2.0 Security Specification · *PCCOE International Grand Challenge 2026*
