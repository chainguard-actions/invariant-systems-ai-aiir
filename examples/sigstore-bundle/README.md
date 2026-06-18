# AIIR Example: Signed Sigstore Bundle

This example is a real AIIR commit receipt plus the matching Sigstore bundle
captured from AIIR's own GitHub Actions dogfood workflow.

It gives integrators three things in one place:

- one passing receipt with a real Rekor-linked bundle
- one failing receipt with the same hash fields left in place after tampering
- exact signer identity values for `cosign` or `sigstore-python` verification

## Files

- `receipt.artifact`: valid `aiir/commit_receipt.v2` receipt for commit `df0abcca94b42f04aa0593e6bf088397e4b441dd`
- `receipt.artifact.sigstore`: matching Sigstore bundle for `receipt.artifact`
- `receipt.tampered.json`: same receipt with a modified commit subject and unchanged `content_hash` and `receipt_id`

The passing example uses a neutral artifact filename instead of `.json` so the
checked-in bytes stay identical to the signed blob.

## Signer Identity

The bundle certificate pins this GitHub Actions workflow identity:

```text
https://github.com/invariant-systems-ai/aiir/.github/workflows/dogfood.yml@refs/heads/main
```

Other certificate claims visible in the bundle:

- OIDC issuer: `https://token.actions.githubusercontent.com`
- Repository: `invariant-systems-ai/aiir`
- Ref: `refs/heads/main`
- Trigger: `push`
- Run URL: `https://github.com/invariant-systems-ai/aiir/actions/runs/23840792263/attempts/1`

## Verify The Passing Example

From the repo root:

```bash
python3 -m aiir --verify examples/sigstore-bundle/receipt.artifact --explain
python3 scripts/check_rekor_bundle.py \
  --artifact examples/sigstore-bundle/receipt.artifact \
  --bundle examples/sigstore-bundle/receipt.artifact.sigstore
```

If you have `cosign` installed:

```bash
cosign verify-blob examples/sigstore-bundle/receipt.artifact \
  --bundle examples/sigstore-bundle/receipt.artifact.sigstore \
  --certificate-identity "https://github.com/invariant-systems-ai/aiir/.github/workflows/dogfood.yml@refs/heads/main" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com"
```

If you prefer `sigstore-python`:

```bash
python -m sigstore verify identity examples/sigstore-bundle/receipt.artifact \
  --bundle examples/sigstore-bundle/receipt.artifact.sigstore \
  --cert-identity "https://github.com/invariant-systems-ai/aiir/.github/workflows/dogfood.yml@refs/heads/main" \
  --cert-oidc-issuer "https://token.actions.githubusercontent.com"
```

## Verify The Failing Example

```bash
python3 -m aiir --verify examples/sigstore-bundle/receipt.tampered.json --explain
```

This should fail because the `commit.subject` field was changed without
recomputing `content_hash` or `receipt_id`.

## Why This Example Exists

The repo and website already described signed receipts conceptually. This
directory is the concrete public fixture for integrators who need one stable
receipt, one stable bundle, and one stable negative case.
