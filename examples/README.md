# AIIR Examples

Concrete examples of AIIR in action — receipts, verification, CI checks, and policy evaluation.

## Signed Bundle Example

Start with the real end-to-end example in [Signed Sigstore bundle](sigstore-bundle/).

That directory contains:

- `receipt.artifact` — the exact signed receipt bytes captured from this repository
- `receipt.artifact.sigstore` — the matching Sigstore bundle with Fulcio certificate and Rekor entry
- `receipt.tampered.json` — the same receipt after a field change without recomputing the hash

Use that example when you need one stable pass case, one stable fail case, and
the exact GitHub Actions signer identity values for `cosign` or
`sigstore-python` verification.

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

This check is enforceable via branch protection rules — require `aiir/verify`
to pass before merging.

## Example Policy Evaluation

```bash
# Initialize a policy for your org
$ aiir --policy-init moderate
📋 Created .aiir/policy.json (moderate preset)

# Verify a release against policy and emit a VSA
$ aiir --verify-release --policy .aiir/policy.json --output vsa.json

Release Verification Summary
  Commits evaluated: 47
  Receipts found:    47 (100% coverage)
  AI-authored:       12 (25.5%)
  Policy result:     PASS

  VSA written to vsa.json (in-toto Statement v1, signed)
```

The VSA (Verification Summary Attestation) is an [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md)
that auditors and downstream systems can consume directly.

## Example Badge

Add to your README after integrating AIIR:

```markdown
[![AIIR Receipted](https://img.shields.io/badge/AIIR-Receipted%20✓-blue)](https://github.com/invariant-systems-ai/aiir)
```

Result: [![AIIR Receipted](https://img.shields.io/badge/AIIR-Receipted%20✓-blue)](https://github.com/invariant-systems-ai/aiir)

## More Examples

- [Signed Sigstore bundle](sigstore-bundle/) — real AIIR receipt, matching bundle, and tampered negative case
- [GitHub Actions integration](github-actions/) — full workflow with signing
- [GitLab CI integration](gitlab-demo/) — MR comments, compliance pipeline
- [MCP server setup](../README.md#-mcp-tool--let-your-ai-do-it) — Claude, VS Code, Cursor, Continue, Windsurf
