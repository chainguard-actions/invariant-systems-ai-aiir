# AIIR Examples

Concrete examples of AIIR in action: receipts, verification, CI checks, and policy evaluation.

## Start Here: The Contradiction

If you want the shortest first-contact artifact, start with [This verifies. Why does strict fail?](verify-pass-strict-fail).

That example is intentionally small:

- `unsigned/receipt.json` verifies cleanly
- `unsigned/` fails `aiir --verify-release --policy strict`
- `signed/` passes strict policy with the same receipt bytes plus the matching `.sigstore` bundle

Use it when you need the smallest possible demonstration that integrity is not the same thing as release-ready evidence. The directory is intentionally small, and its README shows the exact directory-local commands to run it from this checkout.

## Signed Bundle Example

Start with the real end-to-end example in [Signed Sigstore bundle](sigstore-bundle).

That directory contains:

- `receipt.artifact`: the exact signed receipt bytes captured from this repository
- `receipt.artifact.sigstore`: the matching Sigstore bundle with Fulcio certificate and Rekor entry
- `receipt.tampered.json`: the same receipt after a field change without recomputing the hash

Use that example when you need one stable pass case, one stable fail case, and
the exact GitHub Actions signer identity values for `cosign` or
`sigstore-python` verification.

## Signed Commitment Digest Example

For the parallel non-git example, use [Signed commitment receipt bundle](commitment-receipt-bundle).

That directory contains:

- `receipt.artifact`: a real `aiir.commitment_receipt` digest binding
- `receipt.artifact.sigstore`: the matching Sigstore bundle for that receipt
- `receipt.tampered.json`: a negative case with the statement changed and the hash fields left untouched

Use that example when you need one stable signed commitment receipt, one stable
negative case, and an example that binds a declared digest rather than a git
commit.

## Signed Commitment Directory Example

For the matching multi-file example, use [Signed commitment directory bundle](commitment-directory-bundle).

That directory contains:

- `receipt.artifact`: a real `aiir.commitment_receipt` directory binding
- `receipt.artifact.sigstore`: the matching Sigstore bundle for that receipt
- `receipt.tampered.json`: a negative case with the statement changed and the hash fields left untouched

Use that example when you need one stable signed commitment receipt for a
directory artifact, one stable negative case, and a public fixture that shows
deterministic member-manifest binding.

## Release Evidence Bundle Example

For the full handoff artifact, use [Release evidence bundle](release-bundle-basic).

That directory contains:

- `receipts.jsonl`: a small, stable input ledger (3 commits, one AI-assisted)
- `bundle/`: a committed snapshot of a generated release evidence bundle

Use that example when you need to show a customer security team or auditor a
self-contained, offline-verifiable evidence packet: receipts, policy decision,
Verification Summary Attestation, evidence summary, and a human-readable auditor
report. See [docs/guides/release-bundles.md](../docs/guides/release-bundles.md) for the full
command reference.

## Example Verification

```bash
$ aiir --verify examples/sigstore-bundle/receipt.artifact --explain

✅ All good! 1 receipt verified -- integrity intact.
  g1-92edbfc760df552f6941c... commit=df0abcca94b4 ✔

VERIFICATION PASSED

What was checked:
  1. Recomputed the SHA-256 hash of the receipt's core fields
     (type, schema, version, commit, ai_attestation, provenance).
  2. Compared the recomputed content_hash against the stored value — they match.
  3. Derived receipt_id from the same hash — it matches.

What this means:
  The receipt has not been modified since it was created. The commit metadata,
  AI attestation, and provenance are exactly as recorded.

What this does NOT prove:
  Integrity only proves the receipt hasn't been tampered with. It does not
  prove WHO generated it. For authenticity, verify a Sigstore signature.
```

## Example CI Check Output

When AIIR runs in GitHub Actions with `checks: write` permission, it creates
a **Check Run** visible on every PR:

```text
┌──────────────────────────────────────────────────────────┐
│  ✅ AIIR Verification                                    │
│                                                          │
│  Commit: a3f8b2c1d4e5  (feat: add new auth middleware)   │
│  AI involvement detected: yes (copilot)                  │
│  Files touched: 4                                        │
│  Receipt verified: ✅                                     │
│  Policy: PASS                                            │
│  Signer: github-actions (sigstore)                       │
│                                                          │
│  Coverage: 3/3 commits receipted (100%)                  │
└──────────────────────────────────────────────────────────┘
```

This check is enforceable via branch protection rules. Require `aiir/verify`
to pass before merging.

## Example Policy Evaluation

```bash
# Initialize a policy for your org (use 'strict' or 'permissive' presets)
$ aiir --policy-init strict
📋 Created .aiir/policy.json (strict preset)

# Verify a release against policy and emit a VSA (note: VSA is emitted unsigned
# unless you also pass --sign; add --sign for cryptographic authenticity)
$ aiir --verify-release --policy .aiir/policy.json --emit-vsa --output vsa.json

Release Verification Summary
  Commits evaluated: 47
  Receipts found:    47 (100% coverage)
  AI-authored:       12 (25.5%)
  Policy result:     PASS

  VSA written to vsa.json (in-toto Statement v1, unsigned — add --sign for signing)
```

The VSA (Verification Summary Attestation) is an [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md)
that auditors and downstream systems can consume directly.

> **Note**: `--emit-vsa` is the correct flag. VSAs are emitted unsigned by
> default; pass `--sign` to add a Sigstore signature for cryptographic
> authenticity binding. The `moderate` policy preset does not exist;
> use `strict` or `permissive`.

## Example Badge

Add to your README after integrating AIIR:

```markdown
[![AIIR Receipted](https://img.shields.io/badge/AIIR-Receipted%20✓-blue)](https://github.com/invariant-systems-ai/aiir)
```

Result: [![AIIR Receipted](https://img.shields.io/badge/AIIR-Receipted%20✓-blue)](https://github.com/invariant-systems-ai/aiir)

## More Examples

- [This verifies. Why does strict fail?](verify-pass-strict-fail): minimal trust break: integrity passes, strict release policy fails, then passes once signing evidence is present
- [Signed commitment directory bundle](commitment-directory-bundle): real signed directory binding plus tampered negative case
- [Signed commitment receipt bundle](commitment-receipt-bundle): real signed digest binding plus tampered negative case
- [Signed Sigstore bundle](sigstore-bundle): real AIIR receipt, matching bundle, and tampered negative case
- [GitHub Actions integration](github-actions): full workflow with signing
- [GitLab CI integration](gitlab-demo): MR comments, compliance pipeline
- [MCP server setup](../README.md#-mcp-tool--let-your-ai-do-it): Claude, VS Code, Cursor, Continue, Windsurf
