# AIIR Example: Signed Commitment Directory Bundle

This example is a real AIIR commitment receipt plus the matching Sigstore
bundle for a declared directory artifact.

It gives integrators three things in one place:

- one passing commitment receipt with a real Rekor-linked bundle
- one failing receipt with the same hash fields left in place after tampering
- one concrete directory binding that shows how AIIR records a deterministic
  manifest of members instead of a single file hash

## Files

- `receipt.artifact`: valid `aiir/commitment_receipt.v1` receipt for a published public evidence capsule mirror
- `receipt.artifact.sigstore`: matching Sigstore bundle for `receipt.artifact`
- `receipt.tampered.json`: same receipt with a modified statement and unchanged `content_hash` and `receipt_id`

The passing example uses a neutral artifact filename instead of `.json` so the
checked-in bytes stay identical to the signed blob.

## What It Binds

The receipt subject is `nisq-public-evidence-capsule-mirror` with kind
`paper_public_capsule`.

Its single declared artifact is a directory binding for:

```text
capsule/
```

with digest:

```text
sha256:c115f54b327d809e0fdd88405554f2e4eb381c373dbac145ff09411ad58a6da6
```

The receipt records the directory manifest structure as well:

- `entry_count`: `84`
- `file_count`: `82`
- `allowlist_path`: `capsule/PUBLIC_ARCHIVE_FILESET.txt`
- `checksum_manifest_path`: `capsule/checksums.sha256`

## Signer Identity

The bundle certificate pins this signer identity:

```text
noah@invariantsystems.io
```

Other key verification values:

- OIDC issuer: `https://accounts.google.com`
- Receipt ID: `c1-83519087f75ad9c1237fdf5c25592bf3`
- Receipt content hash: `sha256:83519087f75ad9c1237fdf5c25592bf3ab4d389ee00fdac700ba05dbe47d3e4a`

## Verify The Passing Example

From the repo root:

```bash
python3 -m aiir \
  --verify examples/commitment-directory-bundle/receipt.artifact \
  --verify-signature \
  --signer-identity "noah@invariantsystems.io" \
  --signer-issuer "https://accounts.google.com" \
  --explain

python3 scripts/check_rekor_bundle.py \
  --artifact examples/commitment-directory-bundle/receipt.artifact \
  --bundle examples/commitment-directory-bundle/receipt.artifact.sigstore
```

If you prefer `sigstore-python`:

```bash
python -m sigstore verify identity examples/commitment-directory-bundle/receipt.artifact \
  --bundle examples/commitment-directory-bundle/receipt.artifact.sigstore \
  --cert-identity "noah@invariantsystems.io" \
  --cert-oidc-issuer "https://accounts.google.com"
```

## Verify The Failing Example

```bash
python3 -m aiir --verify examples/commitment-directory-bundle/receipt.tampered.json --explain
```

This should fail because the `statement.summary` field was changed without
recomputing `content_hash` or `receipt_id`.

## Why This Example Exists

The digest-binding example shows how AIIR binds a precomputed published hash.
This directory-binding example shows the parallel case for a multi-file public
capsule, including the deterministic member manifest and checksum anchor.
