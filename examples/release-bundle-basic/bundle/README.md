# AIIR Release Evidence Bundle

Self-contained evidence for an AI-assisted software release.

- **Release**: `HEAD`
- **Commit range**: `(all receipts)`
- **Decision**: **PASSED** — All checks passed
- **Generated**: 2026-06-06T19:03:01Z
- **AIIR version**: 1.6.0

## Contents

| File | Role |
|------|------|
| `manifest.json` | Anchor manifest — hashes of every artifact |
| `manifest.sha256` | SHA-256 of the manifest |
| `verify-release.json` | Full release verification result |
| `vsa.intoto.json` | in-toto Verification Summary Attestation |
| `policy.json` | Policy that was applied |
| `receipts/` | The receipts the decision was made over |
| `signatures/` | Sigstore sidecars (when present) |
| `evidence-stream.json` | Normalized evidence stream |
| `evidence-summary.json` | Governance-ready evidence summary |
| `auditor-report.html` | Human-readable auditor report |
| `verifier-instructions.md` | Exact commands to re-verify this bundle |

The auditor report is a rendered *view*. The JSON artifacts are the source of
truth — see `verifier-instructions.md` to re-verify every claim.

## Boundary

- AIIR records declared AI involvement. It does not prove hidden AI use.
- A commit without a receipt is not proof that no AI assistance was used.
- A release bundle is not a build-provenance, SBOM, or SLSA replacement; it adds the AI-involvement layer to that supply-chain evidence stack.
