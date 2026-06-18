# Release Evidence Bundles

A **release evidence bundle** is the canonical handoff artifact for AI-assisted
release evidence. It packages a release-scoped policy decision, the receipts
that decision was made over, the policy that was applied, a governance-ready
evidence summary, and a human-readable auditor report into a single
self-contained directory that a customer security team, auditor, or incident
reviewer can receive, verify **offline**, and archive.

The bundle is the *contract*. The auditor report is a rendered *view* of the
bundle, never the source of truth: a skeptical reviewer can always drop into
the JSON artifacts and re-verify every claim.

## Quick start

```bash
aiir --release-bundle dist/aiir-release-evidence \
  --range v1.5.0..v1.6.0 \
  --receipts .aiir/receipts.jsonl \
  --policy strict
```

This produces a directory:

```text
aiir-release-evidence/
  README.md
  manifest.json
  manifest.sha256
  verify-release.json
  vsa.intoto.json
  policy.json
  receipts/
  signatures/            # present when receipts carry .sigstore sidecars
  evidence-stream.json
  evidence-summary.json
  auditor-report.html
  verifier-instructions.md
```

The process exits `0` when the release verification **PASSED** and `1` when it
**FAILED**. A failed bundle is still written. It shows exactly why the release
is not ready.

## Flags

| Flag | Meaning |
|------|---------|
| `--release-bundle OUTDIR` | Output directory for the bundle |
| `--range A..B` | Commit range to scope the release (optional) |
| `--receipts PATH` | Ledger (JSONL) or directory of receipt JSONs. Default `.aiir/receipts.jsonl` |
| `--policy PRESET\|FILE` | `strict`, `balanced`, `permissive`, or a policy JSON path |
| `--subject SUBJECT` | Subject identifier for the VSA. Default: git remote + HEAD |
| `--no-emit-report` | Skip `auditor-report.html` |
| `--overwrite` | Write into a non-empty output directory |
| `--redact-files` | Omit file paths from the report |
| `--redact-emails` | Mark emails as redacted in the manifest |

## The manifest is the anchor

`manifest.json` is the core object; every other artifact hangs off it. It lists
every file with its role and SHA-256 digest, records the policy decision, and
states the declared-provenance boundary in machine-readable form.

```json
{
  "schema": "aiir/release_bundle.v1",
  "bundle_format_version": 1,
  "created_at": "2026-06-06T00:00:00Z",
  "aiir_version": "1.6.0",
  "release": {
    "name": "v1.6.0",
    "commit_range": "v1.5.0..v1.6.0",
    "subject": "git+https://github.com/org/repo@<sha>"
  },
  "verification": {
    "result": "PASSED",
    "reason": "All checks passed",
    "vsa_path": "vsa.intoto.json",
    "verify_release_result_path": "verify-release.json"
  },
  "policy": { "path": "policy.json", "digest": { "sha256": "..." } },
  "artifacts": [
    { "path": "receipts/0000-...json", "role": "receipt", "sha256": "..." },
    { "path": "vsa.intoto.json", "role": "verification-summary-attestation", "sha256": "..." }
  ],
  "redactions": { "files": false, "emails": false },
  "boundary": {
    "declared_ai_provenance_only": true,
    "hidden_ai_detection": false,
    "build_provenance_replacement": false
  }
}
```

## The auditor report answers five questions

`auditor-report.html` is a self-contained, offline HTML document (stdlib
rendering, no external resources). It answers:

1. **What release is this about?** Repository, subject, commit range, generation time.
2. **What policy was applied?** Preset/custom, digest, enforcement, signing requirement, max AI threshold.
3. **Did it pass?** Verdict, reason, coverage, invalid receipts, missing receipts, violations.
4. **Where was AI declared?** AI-involved receipts, evidence tiers, declared systems, hot paths, unsigned risk.
5. **What does this *not* prove?** The declared-provenance boundary, restated for the reader.

## Verify a bundle independently

Every bundle ships `verifier-instructions.md` with exact commands. The essential
checks:

```bash
# 1. Manifest is intact
sha256sum -c manifest.sha256

# 2. Every receipt's content hash verifies (no trust in AIIR needed)
for f in receipts/*.json; do aiir --verify "$f" --explain || true; done

# 3. Re-run the policy decision over the bundled receipts
aiir --verify-release --receipts receipts/ --policy policy.json
```

## Boundary

A release bundle is precise about what it proves:

- A commit without a receipt is **not** proof that no AI assistance was used.
- A release bundle adds the AI-involvement layer to a supply-chain evidence
  stack that already includes build-provenance, SBOM, and SLSA artifacts.
- For the full scope statement, see
  [What AIIR does not do](../integrations/ecosystem.md#what-aiir-does-not-do).

## Worked example

See [examples/release-bundle-basic/](../../examples/release-bundle-basic) for a
committed bundle snapshot built from a small stable ledger, plus the exact
commands to regenerate and verify it from a checkout.
