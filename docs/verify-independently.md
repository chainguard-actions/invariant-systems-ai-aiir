# Verify AIIR Receipts Independently

**You received an AIIR receipt and want to verify it without trusting the AIIR
tool. This walkthrough shows every step using only standard tools.**

---

## What you're verifying

An AIIR receipt is a JSON document with a content-addressed hash. Verification
checks that the receipt has not been modified since it was created. If the
receipt is signed, you can also verify _who_ created it.

## Prerequisites

- Python 3.9+ or any language with SHA-256 and JSON
- `jq` (optional, for readability)
- `cosign` or `sigstore-python` (only for signature verification)

## Try the checked-in example

The repository includes one real signed example under
[`examples/sigstore-bundle/`](../examples/sigstore-bundle/).

From the repo root:

```bash
python3 -m aiir --verify examples/sigstore-bundle/receipt.artifact --explain
python3 scripts/check_rekor_bundle.py \
  --artifact examples/sigstore-bundle/receipt.artifact \
  --bundle examples/sigstore-bundle/receipt.artifact.sigstore
python3 -m aiir --verify examples/sigstore-bundle/receipt.tampered.json --explain
```

The passing example uses a neutral artifact filename instead of `.json` so the
checked-in bytes stay identical to the signed blob.

The bundle certificate for the passing example pins this workflow identity:

```text
https://github.com/invariant-systems-ai/aiir/.github/workflows/dogfood.yml@refs/heads/main
```

With this OIDC issuer:

```text
https://token.actions.githubusercontent.com
```

If you have `cosign`, you can verify the checked-in example directly:

```bash
cosign verify-blob examples/sigstore-bundle/receipt.artifact \
  --bundle examples/sigstore-bundle/receipt.artifact.sigstore \
  --certificate-identity "https://github.com/invariant-systems-ai/aiir/.github/workflows/dogfood.yml@refs/heads/main" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com"
```

---

## Step 1 — Inspect the receipt

```bash
cat receipt.json | python3 -m json.tool
```

A receipt looks like:

```json
{
  "type": "aiir.commit_receipt",
  "schema": "aiir/commit_receipt.v2",
  "receipt_id": "g1-a3f8b2c1d4e5f6a7...",
  "content_hash": "sha256:7f3a8b...",
  "timestamp": "2026-03-06T09:48:59Z",
  "commit": { ... },
  "ai_attestation": { ... },
  "provenance": { ... }
}
```

The `content_hash` is a SHA-256 hash of the receipt's core fields. The
`receipt_id` is derived from a prefix (`g1-`) plus the first 32 hex chars
of that hash.

## Step 2 — Recompute the content hash (no AIIR needed)

The verification algorithm is:

1. Extract the **core** object: `{type, schema, version, commit, ai_attestation, provenance}`
2. Serialize as canonical JSON: sorted keys, no whitespace, no trailing newline
3. SHA-256 hash the resulting bytes
4. The hex digest must match `content_hash` (after stripping the `sha256:` prefix)

```python
#!/usr/bin/env python3
"""Verify an AIIR receipt without the AIIR CLI — stdlib only."""

import hashlib
import json
import sys

CORE_KEYS = ("type", "schema", "version", "commit", "ai_attestation", "provenance")

def verify_receipt(path: str) -> bool:
    with open(path) as f:
        receipt = json.load(f)

    # 1. Extract core fields
    core = {k: receipt[k] for k in CORE_KEYS if k in receipt}

    # 2. Canonical JSON (sorted keys, no whitespace)
    canonical = json.dumps(core, sort_keys=True, separators=(",", ":"))

    # 3. SHA-256
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # 4. Compare
    expected = receipt.get("content_hash", "").removeprefix("sha256:")
    rid_hex = receipt.get("receipt_id", "").removeprefix("g1-")

    hash_ok = digest == expected
    rid_ok = digest[:32] == rid_hex[:32]

    print(f"Content hash: {'PASS' if hash_ok else 'FAIL'}")
    print(f"  computed: sha256:{digest}")
    print(f"  expected: {receipt.get('content_hash', '(missing)')}")
    print(f"Receipt ID:  {'PASS' if rid_ok else 'FAIL'}")

    return hash_ok and rid_ok

if __name__ == "__main__":
    ok = verify_receipt(sys.argv[1])
    sys.exit(0 if ok else 1)
```

```bash
python3 verify_standalone.py receipt.json
```

If this passes, the receipt has not been modified.

## Step 3 — Verify a Sigstore signature (optional)

If the receipt has a `.sigstore` sidecar bundle:

```bash
# Using cosign
cosign verify-blob receipt.json \
  --bundle receipt.json.sigstore \
  --certificate-identity "https://github.com/OWNER/REPO/.github/workflows/aiir.yml@refs/heads/main" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com"

# Or using sigstore-python
pip install sigstore
python -m sigstore verify identity receipt.json \
  --bundle receipt.json.sigstore \
  --cert-identity "https://github.com/OWNER/REPO/.github/workflows/aiir.yml@refs/heads/main" \
  --cert-oidc-issuer "https://token.actions.githubusercontent.com"
```

Replace `OWNER/REPO` with the repository that generated the receipt.

Signature verification proves:

- The receipt was signed by the claimed CI identity
- The signature is recorded in the Rekor transparency log
- The signing certificate was issued by Fulcio with the claimed OIDC token

## Step 3a — Verify offline Rekor and witness material

If a release ships offline transparency artifacts, AIIR can verify them without
calling Rekor or a witness service.

Required inputs:

- the artifact itself
- a Sigstore bundle or reduced `aiir.rekor.bundle.v1` document
- an `aiir.trust.v1` trust root with the log key and trusted witness keys
- an optional raw witnessed checkpoint note when witness quorum is required

```bash
# Main CLI surface
aiir --artifact dist/aiir-1.3.0-py3-none-any.whl \
  --rekor-bundle dist/rekor-bundle.json \
  --trust-root aiir-trust.json \
  --witnessed-checkpoint dist/witnessed-checkpoint.txt \
  --require-witnesses release

# Standalone helper script
python3 scripts/check_rekor_bundle.py \
  --artifact dist/aiir-1.3.0-py3-none-any.whl \
  --bundle dist/rekor-bundle.json \
  --trust-root aiir-trust.json \
  --witnessed-checkpoint dist/witnessed-checkpoint.txt \
  --require-witnesses release
```

This verifies, offline:

- the artifact hash bound into the Rekor entry material
- the inclusion proof against the signed checkpoint root
- the checkpoint's Ed25519 signed-note signature
- the optional consistency proof from the bundled checkpoint to the witnessed checkpoint
- the witness cosignatures under the configured `N-of-M` policy

The trust root schema is published at [schemas/trust_root.v1.schema.json](../schemas/trust_root.v1.schema.json), and
the reduced Rekor bundle schema is published at
[schemas/rekor_bundle.v1.schema.json](../schemas/rekor_bundle.v1.schema.json).

For AIIR's own GitHub releases, the release pipeline now also publishes
per-artifact `.publish.attestation`, raw `rekor-*.json`, and
`*.rekor-bundle.json` assets plus `VERIFY-OFFLINE.md`. The `.publish.attestation`
and raw Rekor entry files mirror the public PEP 740 release evidence surface;
the offline bundles cover the Rekor side automatically. They do not include a
production trust root or witnessed checkpoint yet, so full witness quorum
verification still requires an extra `aiir-trust.json` and
`witnessed-checkpoint.txt` from your own witness layer. The repo-owned
automation for those assets lives in the dedicated
[.github/workflows/offline-rekor-release.yml](../.github/workflows/offline-rekor-release.yml)
workflow.

For a concrete `2-of-3` rollout, see
[examples/witness-quorum/policy.yaml](../examples/witness-quorum/policy.yaml),
[examples/witness-quorum/trust-root.example.json](../examples/witness-quorum/trust-root.example.json),
and [examples/witness-quorum/VERIFY.md](../examples/witness-quorum/VERIFY.md).
The accompanying draft workflow at
[examples/github-actions/.github/workflows/aiir-witnessed-release-draft.yml](../examples/github-actions/.github/workflows/aiir-witnessed-release-draft.yml)
shows how to publish those files once your own Rekor v2 / witness client has
produced the raw proofs.

## Step 4 — Cross-check against the git commit

The receipt's `commit.sha` should match an actual commit in the repository:

```bash
git log --format="%H %s" | grep "$(jq -r .commit.sha receipt.json)"
```

You can also verify that `commit.author`, `commit.subject`, and
`commit.files_changed` match the actual commit metadata.

## Step 5 — Verify conformance test vectors

The AIIR specification includes 25 test vectors with precomputed hashes:

```bash
curl -sO https://raw.githubusercontent.com/invariant-systems-ai/aiir/main/schemas/test_vectors.json
python3 -c "
import json, hashlib
with open('test_vectors.json') as f:
    vectors = json.load(f)['vectors']
passed = 0
for v in vectors:
    canonical = json.dumps(v['core'], sort_keys=True, separators=(',', ':'))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    ok = digest == v['expected_hash'].removeprefix('sha256:')
    passed += ok
    if not ok:
        print(f'FAIL: {v[\"name\"]}')
print(f'{passed}/{len(vectors)} vectors passed')
"
```

If all 25 pass, your verification implementation matches the specification.

---

## Summary

| Check                          | Requires network?         | Requires AIIR CLI?                       |
| ------------------------------ | ------------------------- | ---------------------------------------- |
| Content hash                   | No                        | No                                       |
| Receipt ID                     | No                        | No                                       |
| Rekor + witness offline bundle | No                        | No (helper script) / Optional (AIIR CLI) |
| Sigstore signature             | Yes (transparency log)    | No (cosign or sigstore-python)           |
| Git commit cross-check         | No (if you have the repo) | No                                       |
| Conformance vectors            | No (once downloaded)      | No                                       |

Everything except live Sigstore identity verification works fully offline with
standard tools once the release includes the transparency bundle, trust root,
and witnessed checkpoint files.

---

## Reference

- [SPEC.md §8 — Content Addressing](../SPEC.md) — normative verification algorithm
- [schemas/test_vectors.json](../schemas/test_vectors.json) — 25 conformance vectors
- [THREAT_MODEL.md](../THREAT_MODEL.md) — what AIIR defends against
- [Browser verifier](https://invariantsystems.io/verify) — client-side verification, no upload
