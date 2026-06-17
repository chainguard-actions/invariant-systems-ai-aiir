# Commitment Receipts

AIIR commitment receipts extend the receipt model beyond git commits.

Use them when you need a content-addressed, locally verifiable declaration for
artifacts such as:

- evaluation plans
- manifest files
- benchmark matrices
- release input bundles
- precomputed public hashes

They are designed to stay generic. The receipt records a named subject, a short
human summary, and one or more declared artifacts. Each artifact can be a file,
a directory, or a precomputed `sha256:` digest.

## CLI examples

Single file:

```bash
aiir \
  --commitment-artifact plan.json \
  --commitment-name nisq-eval-plan \
  --commitment-summary "Declared evaluation plan before rerun" \
  --output .receipts
```

Directory bundle:

```bash
aiir \
  --commitment-artifact public-bundle/ \
  --commitment-name nisq-public-bundle \
  --commitment-summary "Public evidence bundle prepared for release" \
  --output .receipts
```

Precomputed digest:

```bash
aiir \
  --commitment-digest packet-sha=sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef \
  --commitment-name nisq-packet-hash \
  --commitment-summary "Published packet digest after rebuild" \
  --output .receipts
```

Add Sigstore-backed chronology:

```bash
aiir \
  --commitment-artifact plan.json \
  --commitment-name nisq-eval-plan \
  --commitment-summary "Declared evaluation plan before rerun" \
  --output .receipts \
  --sign
```

`--sign` reuses AIIR's existing Sigstore integration. The receipt JSON stays
portable and locally verifiable. The signature sidecar adds identity binding and
Rekor-backed inclusion material when you need stronger chronology claims.

For real signed fixtures, see:

- [examples/commitment-receipt-bundle/](../examples/commitment-receipt-bundle/) for a digest-only commitment receipt
- [examples/commitment-directory-bundle/](../examples/commitment-directory-bundle/) for a directory-bound commitment receipt

Both package the matching Sigstore bundle plus a tampered negative case you can
verify locally.

## Receipt shape

Core fields:

- `type`: `aiir.commitment_receipt`
- `schema`: `aiir/commitment_receipt.v1`
- `version`: emitting AIIR version
- `subject`: `{ "name": ..., "kind": ... }`
- `statement`: `{ "summary": ... }`
- `artifacts`: declared files, directories, or digests
- `provenance`: emitting tool, generator, and optional repository URL

Derived fields:

- `content_hash`: `sha256:` over the canonical JSON of the core fields
- `receipt_id`: `c1-` prefix plus the truncated canonical hash
- `timestamp`: emission time

Directories are hashed deterministically as a canonical manifest of their
members. Files store their byte-level `sha256:` digest directly. Declared digest
artifacts preserve the supplied `sha256:` value as-is.

## Verification model

`aiir --verify receipt.json` recomputes the canonical hash from the receipt core
and confirms that both `content_hash` and `receipt_id` still match.

This proves integrity, not authorship. For authenticity or public chronology,
sign the receipt and verify the Sigstore bundle as well.

The examples tree now includes three public verification fixtures:

- [examples/sigstore-bundle/](../examples/sigstore-bundle/) for a signed commit receipt
- [examples/commitment-receipt-bundle/](../examples/commitment-receipt-bundle/) for a signed digest-binding commitment receipt
- [examples/commitment-directory-bundle/](../examples/commitment-directory-bundle/) for a signed directory-binding commitment receipt

## Non-goals

- AIIR commitment receipts are not a transparency log by themselves.
- They do not replace SLSA build provenance.
- They do not prove that a plan was followed, only that the declared artifact
  set was committed to in a tamper-evident way.
