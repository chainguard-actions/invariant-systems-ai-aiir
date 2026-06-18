# Compliance Mapping: AIIR Receipts

A starter mapping from AIIR commit receipts and evidence to key compliance
frameworks. This is informative guidance, not legal advice.

---

## EU AI Act — Article 12 (Record-keeping)

Article 12 of the EU AI Act requires providers of high-risk AI systems to
implement logging capabilities that enable post-hoc auditability. AIIR
provides a commit-level provenance layer that supports Art. 12 obligations
in software-development contexts.

| Art. 12 Requirement | AIIR Evidence | How to produce |
|--------------------|---------------|---------------|
| Record AI involvement in decisions | `ai_attestation.is_ai_authored`, `signals_detected`, `authorship_class` | `aiir --pretty` on each commit |
| Identify the AI tool used | `provenance.tool`, `extensions.agent_attestation.tool_id` | `aiir --agent-tool <name>` |
| Tamper-evident record | `content_hash` (SHA-256 content addressing) | Inherent; verified with `aiir --verify` |
| Record of generation time | `timestamp` (RFC 3339 UTC) | Inherent |
| Cryptographic authenticity | Sigstore signature + Rekor transparency-log entry | `aiir --sign` |
| Retention period support | Append-only JSONL ledger (`.aiir/receipts.jsonl`) | `aiir --init`, `aiir --export` for archival |

**Note**: AIIR records **declared** AI involvement from commit metadata.
Undeclared AI usage (e.g., agent-mode sessions without trailers) is not
captured. See [What AIIR does not do](../integrations/ecosystem.md#what-aiir-does-not-do) and
README § Detection scope for limitations.

---

## SOC 2 — Change Management (CC6.8 / CC8.1)

SOC 2 Type II auditors typically look for evidence that changes to production
systems are authorized, reviewed, and traceable. AIIR provides commit-level
provenance evidence for code changes.

| SOC 2 Control | AIIR Evidence | How to produce |
|--------------|---------------|---------------|
| Change authorization | `commit.author`, `commit.committer`, AI signals | Per-commit receipt in CI |
| Change traceability | `commit.sha`, `commit.tree_sha`, `commit.parent_shas` (DAG binding) | `aiir --range <range>` |
| Evidence of review | `extensions.review_outcome` (from `aiir --review`) | `aiir --review <sha> --review-outcome approved` |
| AI involvement disclosure | `authorship_class`, `signals_detected` | Inherent in receipt |
| Tamper-evident audit trail | Content hash verification | `aiir --verify .aiir/receipts.jsonl` |
| Release evidence | `aiir --verify-release --emit-vsa` (VSA in-toto Statement v1) | `aiir --verify-release --policy strict` |

---

## NIST SSDF (SP 800-218) — Produce Well-Secured Software

The NIST Secure Software Development Framework describes practices for secure
software supply chains. Relevant mapping:

| SSDF Practice | AIIR Coverage | Notes |
|--------------|---------------|-------|
| PW.1.1: Train developers in secure practices | Supports via declared AI context | Helps identify AI-generated code needing review |
| PO.3.1: Use automated tools to enforce security | `aiir --check --policy strict` as a CI gate | Fail the build when policy violated |
| RV.1.2: Maintain provenance for all components | Commit receipts as source-level provenance | Feeds SLSA attestation via `--in-toto` |
| PO.5.1: Store all forms of code based on security | Append-only signed ledger | `aiir --sign`, `aiir --export` |

---

## How to use these mappings

1. **Generate receipts** for every commit in scope:

   ```bash
   aiir --range <start>..<end> --sign --output .receipts/
   ```

2. **Enforce policy** in CI as a merge gate:

   ```bash
   aiir --check --policy .aiir/policy.json
   ```

3. **Emit a Verification Summary Attestation** (VSA) for release evidence:

   ```bash
   aiir --verify-release --policy strict --emit-vsa --output vsa.json
   ```

4. **Archive the ledger** for the audit period:

   ```bash
   aiir --export audit-$(date +%Y-%m).json
   ```

5. **Verify independently** without trusting AIIR:
   See [docs/reference/verify-independently.md](verify-independently.md).

---

## Limitations

- VSAs are emitted **unsigned** by default; pass `--sign` for cryptographic
  authenticity binding.
- AIIR is not a substitute for a full SLSA Level 2+ build provenance pipeline.
  Use `aiir --in-toto` to feed receipts into an in-toto layout.
- This mapping is informative guidance for practitioners, not legal advice.
  Consult your legal and compliance team for regulatory obligations.
