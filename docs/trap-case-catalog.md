# AIIR Trap-Case Catalog

This catalog maps common AIIR failure patterns to operational and business
consequences.

Use it when the system is technically green but you still need to decide what
the result means for a maintainer, reviewer, auditor, or release operator.

## Trap cases

| Trap case | What it looks like | Business consequence | Immediate operator action |
|---|---|---|---|
| Unsigned receipt treated as proof of origin | Receipt verifies, but no Sigstore signature is present | Audit overclaim; weak evidence presented as strong evidence | Reclassify as integrity-only evidence and rerun in a signed workflow if origin matters |
| Known AI work classified as `human` | Commit involved chat or agent tooling, but the receipt shows no AI signals | False confidence in disclosure completeness | Treat as missing declaration; add durable markers or move to a stronger capture path |
| Receipt verifies against the wrong commit history | Receipt is valid, but the branch was rewritten or the reviewer is looking at a different SHA | Review or release evidence points at the wrong change | Re-anchor on commit SHA first, then regenerate or relink the receipt |
| Policy passes but the policy is too weak | `balanced` or permissive settings pass a release that compliance would reject | Green gate masks governance mismatch | Review the policy as a business control, not just a technical control |
| Signature verifies without identity pinning | Sigstore verification succeeds, but signer identity was not constrained | You know it was signed, not whether it was signed by the right workflow | Re-verify with `--signer-identity` and `--signer-issuer` pinned |
| Public receipts leak too much file structure | Receipt includes sensitive path names in `files` | Public metadata disclosure beyond what the team intended | Use `--redact-files` or keep public evidence at the signed-summary level |
| Local CI passes, public evidence packet drifts | Repo version and website/release surfaces disagree | Release consumers see inconsistent claims and versions | Sync public surfaces before release; do not ship contradictory evidence |
| Tamper-evident receipt mistaken for code-quality approval | Receipt exists and verifies, so reviewers assume the change is safe | Process shortcut replaces actual code review | Separate provenance review from correctness/security review |

## Fast classification

| If the problem is about... | Then AIIR is mainly giving you... | Human responsibility still required |
|---|---|---|
| Receipt bytes, IDs, hashes, signatures | Cryptographic evidence | Decide whether the signer and context are acceptable |
| Missing or incomplete declaration | A disclosure warning | Decide whether the team process is acceptable |
| Policy failure or success | A gate result | Decide whether the policy itself matches the business requirement |
| Release readiness | Strong signals, not final judgment | Decide whether evidence, docs, and public surfaces are coherent enough to ship |

## Use this catalog with

- [operator-model.md](operator-model.md) for the five-minute view
- [residual-risk.md](residual-risk.md) for what AIIR still cannot safely decide
- [THREAT_MODEL.md](../THREAT_MODEL.md) for the full attack and mitigation record
