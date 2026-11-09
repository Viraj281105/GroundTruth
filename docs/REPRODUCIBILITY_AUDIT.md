# GroundTruth 2.0 — Reproducibility & Audit Trail Architecture

**Specification**: Version 2.0  
**Status**: Implemented (`platform.audit.ledger`)  
**Objective**: Deterministic, Cryptographically Verifiable Environmental MRV  

---

## 1. The Reproducibility Mandate

In environmental credit verification, legal due diligence, and carbon audits, an analytical conclusion is worthless if it cannot be independently reproduced by a third party.

GroundTruth 2.0 guarantees **deterministic mathematical reproducibility**:
> *Given the identical input geometry, identical dataset hashes, identical analytical parameters, and identical software commit revision, GroundTruth will produce bit-for-bit identical numerical findings.*

---

## 2. Merkle Root Hash Binding

Every assessment compiled by GroundTruth constructs a hierarchical cryptographic Merkle tree that binds seven immutable components into a single root digest:

```
                                  [ MERKLE ROOT HASH ]
                                           │
             ┌─────────────────────────────┴─────────────────────────────┐
             ▼                                                           ▼
       [ INPUTS HASH ]                                            [ FINDINGS HASH ]
       (Geometry + Params)                                      (ATT + Placebos + CARs)
             │                                                           │
     ┌───────┴───────┐                                           ┌───────┴───────┐
     ▼               ▼                                           ▼               ▼
[Geometry]     [Datasets &]                                [Intermediate]    [Final]
(GeoJSON)       [Commit SHA]                                 (Zonal Series)  (Findings)
```

### The 7 Essential Audit Fields
Every `AuditRecord` persistently captures:
1. **`geometry_hash`**: SHA-256 digest of the validated GeoJSON treatment polygon coordinates.
2. **`dataset_hashes`**: Key-value mapping of every dataset identifier to its specific content SHA-256 hash.
3. **`analytical_parameters`**: Complete JSON dictionary of hyperparameters (pre-treatment cutoff year, donor pool radius, ridge penalty $\lambda$, SUTVA buffer km, cloud threshold).
4. **`code_commit_sha`**: Exact Git commit SHA of the running engine (`platform.audit.ledger.get_current_git_commit()`).
5. **`model_version`**: Canonical version string of the analytical engine (e.g. `scm-convex-v2.0`).
6. **`intermediate_outputs_hash`**: SHA-256 digest of raw zonal time-series, monthly NDVI tables, and SCL cloud statistics.
7. **`final_findings_hash`**: SHA-256 digest of the final estimation results (estimated ATT, standard error, empirical p-value, claim verification statuses, and CAR items).

---

## 3. Cryptographic Formulation

The Merkle root digest $H_{\text{root}}$ is computed as:

$$H_{\text{inputs}} = \text{SHA256}(H_{\text{geom}} \parallel H_{\text{datasets}} \parallel H_{\text{params}} \parallel H_{\text{commit}})$$
$$H_{\text{outputs}} = \text{SHA256}(H_{\text{intermediate}} \parallel H_{\text{findings}} \parallel H_{\text{model}})$$
$$H_{\text{root}} = \text{SHA256}(H_{\text{inputs}} \parallel H_{\text{outputs}})$$

Where $\parallel$ represents canonical JSON UTF-8 byte concatenation.

---

## 4. Third-Party Audit Verification Protocol

Any independent environmental auditor or MRV consultant can verify an assessment without trusting GroundTruth's operational servers via `POST /api/v2/audit/verify-reproducibility`:

### Request
```json
{
  "project_id": "kariba",
  "audit_record_id": "AUDIT-2026-kariba-001",
  "expected_merkle_root": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "input_files": {
    "boundary_geojson": "..."
  },
  "analytical_parameters": {
    "intervention_year": 2011,
    "donor_pool_size": 24,
    "sutva_buffer_km": 15.0
  }
}
```

### Verification Algorithm
1. The engine checks out the designated `code_commit_sha` in an isolated execution sandbox.
2. The engine re-computes $H_{\text{geom}}$, $H_{\text{datasets}}$, and $H_{\text{params}}$ from the provided payload.
3. The deterministic synthetic control estimator executes headlessly.
4. The resulting findings and intermediate tables are hashed to derive $H_{\text{recalculated}}$.
5. If $H_{\text{recalculated}} = H_{\text{expected}}$, the audit verification returns:
   ```json
   {
     "status": "verified",
     "deterministic_reproducibility": true,
     "bit_for_bit_match": true,
     "discrepancies": []
   }
   ```
If any parameter, code line, or boundary coordinate was altered, the cryptographic digest immediately mismatches, alerting the auditor to tampering or drift.

