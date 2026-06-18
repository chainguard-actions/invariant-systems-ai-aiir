# AIIR Witness Attestor

A [Witness](https://github.com/in-toto/witness) attestor that captures
AIIR receipts as part of an in-toto attestation pipeline.

## What this does

Witness is a pluggable framework for automating, normalizing, and verifying
software supply-chain provenance. Attestors are plugins that capture metadata
at each step of the supply chain.

This attestor runs AIIR against the current git state and captures the receipt
as a Witness attestation product. The result is an in-toto Statement v1 with:

- **predicateType**: `https://invariantsystems.io/predicates/aiir/commit_receipt/v2`
- **subject**: the git commit being attested
- **predicate**: the full AIIR receipt (AI signals, content hash, provenance)

## Usage

### Standalone (without Witness integration)

The attestor script can be used directly to generate Witness-compatible
in-toto attestations:

```bash
# Generate an AIIR attestation for the current commit
python attestor.py --commit HEAD --output attestation.intoto.json

# Generate for a range of commits
python attestor.py --range origin/main..HEAD --output-dir attestations/

# Verify existing receipts and produce attestation of verification result
python attestor.py --verify .aiir/receipts.jsonl --output verification.intoto.json
```

### With Witness run

Once integrated as a Witness attestor (Go plugin), usage would be:

```bash
# Run a build step with AIIR attestation included
witness run --step build \
  --attestors aiir \
  -- make build

# Verify the attestation chain includes AIIR
witness verify --policy policy.yaml --attestations attestations/
```

### Witness policy example

```yaml
# policy.yaml — require AIIR attestation on build steps
steps:
  build:
    name: build
    attestations:
      - type: https://invariantsystems.io/predicates/aiir/commit_receipt/v2
    functionaries:
      - type: root
        certConstraint:
          commonname: "builder@example.com"
          roots:
            - fulcio.pem
```

## Architecture

```text
Witness pipeline:
  step: source-check
    │
    ├── git attestor (built-in)     ← captures commit metadata
    ├── aiir attestor (this plugin) ← captures AI authorship receipt
    └── material attestor           ← captures file hashes
    │
    ▼
  step: build
    │
    ├── command-run attestor         ← captures build command
    └── product attestor             ← captures build outputs
    │
    ▼
  witness verify --policy policy.yaml
    │
    ▼
  Policy checks:
    ✓ All steps executed by authorized functionaries
    ✓ Source commits carry AIIR receipts (AI authorship declared)
    ✓ Build artifacts traced to attested source
```

## Files

| File | Purpose |
|---|---|
| `attestor.py` | Standalone attestor: generates in-toto Statement v1 from AIIR receipts |
| `README.md` | This file |

## Next steps

- [ ] Go implementation as a Witness attestor plugin
- [ ] Witness policy constraint for requiring AIIR attestations
- [ ] Integration test with `witness run` + `witness verify`

## References

- [Witness Documentation](https://github.com/in-toto/witness)
- [in-toto Attestation Spec v1](https://github.com/in-toto/attestation/tree/main/spec/v1)
- [AIIR Specification](../../SPEC.md)
- [AIIR in-toto support](../../ARCHITECTURE.md)
