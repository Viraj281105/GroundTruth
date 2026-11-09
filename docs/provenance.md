# Evidence Provenance & Cryptographic Verification

**Package**: `packages/groundtruth/src/groundtruth/provenance/`  
**Standards**: RFC 8785 (Canonical JSON), SHA-256 Digest Chains, Sigstore Cosign (Keyless OIDC), DVC Data Versioning.

In GroundTruth 2.0, an evidence bundle is cryptographically bound to its raw input datasets, sensor masks, and analytical code commits.

```mermaid
graph TD
    subgraph InputAssets["1. Immutable Input Assets"]
        SatelliteRasters["Raw STAC Satellite COGs (SHA-256)"]
        ClimateGrids["CHIRPS Precipitation NetCDF (SHA-256)"]
        BoundaryGeoJSON["Project Polygon GeoJSON (SHA-256)"]
        CodeGit["Repository Commit (GIT_SHA: e19e73...)"]
    end

    subgraph ProvenanceManifest["2. Provenance Manifest (RFC 8785)"]
        Manifest["manifest.json<br/>• inputs: Array of SHA-256 Hashes<br/>• engine_version & declared seed<br/>• result_canonical_sha256<br/>• manifest_sha256"]
    end

    subgraph SigstoreAttestation["3. Public Cryptographic Attestation"]
        Cosign["Sigstore Cosign Engine"]
        Rekor[("Rekor Public Transparency Log<br/>• Keyless Identity Attestation<br/>• Inclusion Proof")]
        SigstoreBundle["manifest.sigstore.json"]
    end

    InputAssets --> Manifest
    Manifest --> Cosign
    Cosign --> Rekor
    Rekor --> SigstoreBundle
```

![Auditor Dashboard](product/screens/auditor-dashboard.png)

---

## 1. Provenance Manifest Architecture

The provenance manifest cryptographically locks the result JSON to its inputs:
- `result.canonical_sha256`: SHA-256 digest computed across canonical JSON (lexicographically sorted keys, no whitespace).
- `inputs`: Map of input file paths to their individual SHA-256 content digests.
- `engine_version`: Engine git commit and semver release.
- `seed`: Declared pseudo-random number generator seed.
- `manifest_sha256`: Digest computed over all preceding fields.

```bash
# Build provenance manifest from result bundle and inputs
python -m groundtruth.provenance build result.json \
    --input data/processed/climate.json \
    --input data/processed/sentinel2.zarr \
    --seed 20260101 \
    --out manifest.json

# Independently verify manifest integrity
python -m groundtruth.provenance verify manifest.json result.json \
    --input data/processed/climate.json \
    --input data/processed/sentinel2.zarr
```

---

## 2. Keyless Attestation with Sigstore Cosign

GroundTruth 2.0 signs verification bundles using keyless OpenID Connect (OIDC) identities via Sigstore Cosign:

```bash
# Sign manifest using ambient GitHub Actions workflow identity
python -m groundtruth.provenance sign manifest.json --bundle manifest.sigstore.json

# Verify signature against GitHub repository identity
python -m groundtruth.provenance verify-sig manifest.json \
    --bundle manifest.sigstore.json \
    --identity-regexp 'https://github.com/GroundTruth/.*'
```

Container images deployed to production are signed with GitHub Container Registry (GHCR) attestations, including CycloneDX Software Bills of Materials (SBOMs) to defend against supply-chain tampering.
