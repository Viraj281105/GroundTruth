# Evidence provenance

An evidence bundle is a result JSON plus the input files that produced it. The
provenance manifest pins them together:

- `result.canonical_sha256`: SHA-256 of the result in canonical JSON (sorted keys, no whitespace).
- `inputs`: SHA-256 of each input file, plus `engine_version` and `seed`.
- `manifest_sha256`: hash over all other manifest fields.

```
python -m groundtruth.provenance build result.json --input data.csv --seed 42 --out manifest.json
python -m groundtruth.provenance verify manifest.json result.json --input data.csv
```

## Signing (Sigstore cosign, keyless)

`sign` and `verify-sig` shell out to `cosign sign-blob` / `verify-blob`. If cosign is not
installed the CLI exits 2 with a clear error. Keyless signing uses OIDC: locally cosign
opens a browser login; in GitHub Actions the ambient workflow identity is used
(`id-token: write`), see `.github/workflows/sign-evidence.yml`. Verification must name the
expected signer identity (`--identity-regexp`) and issuer.

```
python -m groundtruth.provenance sign manifest.json --bundle manifest.sigstore.json
python -m groundtruth.provenance verify-sig manifest.json --bundle manifest.sigstore.json \
  --identity-regexp 'https://github.com/<org>/GroundTruth/.*'
```

Container images are published to GHCR with SBOM and provenance attestations
(`publish-images.yml`); `security.yml` produces a Syft SBOM and vulnerability scans.
Data is versioned with DVC using a local-only remote (see `data/README.md`).
