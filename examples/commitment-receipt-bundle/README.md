# AIIR Example: Signed Commitment Receipt Bundle

This example is a real AIIR commitment receipt plus the matching Sigstore
bundle captured from the public NISQ evidence sidecar flow.

It gives integrators three things in one place:

- one passing commitment receipt with a real Rekor-linked bundle
- one failing receipt with the same hash fields left in place after tampering
- one concrete digest-only binding that is not tied to a git commit

## Files

- `receipt.artifact`: valid `aiir/commitment_receipt.v1` receipt for the published NISQ Zenodo tarball digest
- `receipt.artifact.sigstore`: matching Sigstore bundle for `receipt.artifact`
- `receipt.tampered.json`: same receipt with a modified statement and unchanged `content_hash` and `receipt_id`

The passing example uses a neutral artifact filename instead of `.json` so the
checked-in bytes stay identical to the signed blob.

## What It Binds

The receipt subject is `nisq-zenodo-release-packet-digest` with kind
`release_digest_binding`.

Its single declared artifact is a precomputed digest binding for:

```text
nisq-readiness-evidence-capsule-v2026.05.01-zenodo.tar.gz
```

with digest:

```text
sha256:e5511fbf5cafbe9fce809f9b9820d27027852430e4e8f1feee6bfaad2b219d67
```

## Signer Identity

The bundle certificate pins this signer identity:

```text
noah@invariantsystems.io
```

Other key verification values:

- OIDC issuer: `https://accounts.google.com`
- Receipt ID: `c1-d471841487c192f5eff89b8dd5ff79a2`
- Receipt content hash: `sha256:d471841487c192f5eff89b8dd5ff79a20a161dbb7a60ed7ce6bbf24db552b56e`

## Verify The Passing Example

From the repo root:

```bash
python3 -m aiir \
  --verify examples/commitment-receipt-bundle/receipt.artifact \
  --verify-signature \
  --signer-identity "noah@invariantsystems.io" \
  --signer-issuer "https://accounts.google.com" \
  --explain

python3 scripts/check_rekor_bundle.py \
  --artifact examples/commitment-receipt-bundle/receipt.artifact \
  --bundle examples/commitment-receipt-bundle/receipt.artifact.sigstore
```

If you prefer `sigstore-python`:

```bash
python -m sigstore verify identity examples/commitment-receipt-bundle/receipt.artifact \
  --bundle examples/commitment-receipt-bundle/receipt.artifact.sigstore \
  --cert-identity "noah@invariantsystems.io" \
  --cert-oidc-issuer "https://accounts.google.com"
```

## Verify The Failing Example

```bash
python3 -m aiir --verify examples/commitment-receipt-bundle/receipt.tampered.json --explain
```

This should fail because the `statement.summary` field was changed without
recomputing `content_hash` or `receipt_id`.

## Why This Example Exists

The repo already had a signed commit-receipt example. This directory is the
parallel fixture for AIIR's generic commitment receipt surface: a stable pass
case, a stable fail case, and a real signed digest-only declaration that users
can verify independently.
