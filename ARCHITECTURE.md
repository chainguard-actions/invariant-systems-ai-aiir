# AIIR Architecture

> Architecture overview for AIIR, the reference implementation of AI Integrity Receipts.

## Current Architecture (v1.5.1 / Spec v2.0.0)

```text
┌─────────────────────────────────────────────────────────────┐
│  CLI / GitHub Action / GitLab CI / MCP Server / SDKs        │
│  (cli.py, action.yml, templates/, mcp_server.py, sdks/)     │
├─────────────────────────────────────────────────────────────┤
│  Receipt + Review Builder  Verification + Release Engine    │
│  (_receipt.py)            (_verify*.py, _verify_release.py) │
├─────────────────────────────────────────────────────────────┤
│  Detection  Evidence  Ledger  Signing  Policy  Explain      │
│  (_detect)  (_evidence)(_ledger)(_sign)(_policy)(_explain)  │
├─────────────────────────────────────────────────────────────┤
│  Canonical JSON / CBOR   Schema   Transparency   Integrations│
│  (_core, _canonical_cbor)(_schema)(_transparency)(_github/*)│
└─────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Zero runtime dependencies**: stdlib-only for trust minimization
2. **Canonical determinism**: identical inputs always produce identical receipts
3. **Separation of core and extensions**: six CORE_KEYS form the content hash;
   everything else lives in `extensions` (excluded from hash, backward-compatible)
4. **Layered verification**: hash integrity first, then structural schema
   validation, then optional Sigstore signature verification
5. **Progressive disclosure**: `--json` for machines, pretty-print for humans,
   `--detail` for deep inspection, `--explain` for non-crypto users

### Module Responsibilities

| Module | Responsibility |
| --- | --- |
| `_core.py` | Canonical JSON encoding, SHA-256 hashing, receipt ID construction |
| `_canonical_cbor.py` | Deterministic CBOR envelopes and sidecar hashing for cross-language proof surfaces |
| `_receipt.py` | Commit and review receipt builders, pretty formatting, and in-toto wrapping |
| `_detect.py` | AI-authorship detection: trailer parsing, bot patterns, and signal aggregation |
| `_editor_provenance.py` | Deterministic editor and workspace provenance capture for stronger local evidence |
| `_evidence.py` | Evidence-tier classification, evidence normalization, and import/export helpers |
| `_verify.py` | Receipt integrity verification, schema checks, and sidecar linkage |
| `_verify_cbor.py` | Canonical CBOR envelope, sidecar, and file verification |
| `_verify_inference.py` | Inference receipt and inference-chain verification |
| `_verify_release.py` | Release-scoped policy evaluation and Verification Summary Attestation (VSA) emission |
| `_release_bundle.py` | Portable release evidence bundle: manifest, VSA, receipts, evidence summary, and offline auditor report |
| `_transparency.py` | Rekor bundle, trust-root, and witness-material verification |
| `_schema.py` | Zero-dependency structural validator (JSON Schema semantics, no library) |
| `_explain.py` | Human-readable verification explanations with categorized failure diagnostics |
| `_policy.py` | Org policy engine: presets (strict/balanced/permissive), staged enforcement |
| `_ledger.py` | Append-only JSONL ledger, index management, and export helpers |
| `_stats.py` | Ledger statistics, badges, and operator-facing health summaries |
| `_sign.py` | Sigstore integration (optional dependency) |
| `_github.py` | GitHub check runs, PR comments, summaries, and commit-trailer formatting |
| `_gitlab.py` | GitLab summaries, SAST report formatting, approval helpers, and dashboard output |
| `cli.py` | Argument parsing, sub-command dispatch, output formatting, and CI entrypoints |
| `mcp_server.py` | Model Context Protocol server exposing the 7 tool surfaces over stdio |

---

## Current Product Surfaces

This file tracks the stable architectural surfaces, not every release-note
delta. For release-by-release changes, see [CHANGELOG.md](CHANGELOG.md).

### Receipt and attestation surfaces

- Commit receipts remain the core artifact: content-addressed, schema-validated, and optionally signed.
- Review receipts extend the same ledger with human review attestations and shared policy semantics.
- AIIR can wrap receipts and release verdicts in in-toto Statement v1 envelopes for downstream supply-chain tooling.
- The draft `aiir/agent_receipt.v0.1` profile sits adjacent to the commit-receipt profile rather than replacing it.

### Verification and proof surfaces

- `aiir --verify` remains the primary integrity path for receipt JSON and linked sidecars.
- `aiir --explain` and the operator docs provide human-readable failure interpretation instead of raw crypto-only output.
- `aiir --verify-release` evaluates a receipt set against policy and can emit a Verification Summary Attestation.
- Inference receipts, CBOR sidecars, and transparency material each have dedicated verification layers rather than being folded into a single opaque verifier.
- Evidence-tier classification is explicit and reusable through `_evidence.py`, so UI and CI surfaces can present the same trust-state language.

### Governance and policy surfaces

- Policy presets (`strict`, `balanced`, `permissive`) remain the stable repository gate abstraction.
- Agent attestation supports declared, transport, and environment confidence paths without changing the hashed receipt core.
- DAG binding (`tree_sha`, `parent_shas`) ties a receipt to both content and graph position.

### Transport and integration surfaces

- The CLI is still the canonical operator surface.
- The GitHub Action and GitLab component are first-party CI entrypoints over the same receipt and policy engine.
- The MCP server exposes 7 stdio tools: receipt, verify, stats, explain, policy_check, verify_release, and gitlab_summary.
- Companion SDKs extend verification outward without moving the Python reference implementation off its canonical role.

---

## Future Direction

AIIR's roadmap focuses on three themes: **deeper provenance primitives**,
**richer verification experiences**, and **tighter ecosystem integration**.
New capabilities follow the schema evolution policy below: extensions
first, promotion after proven stability.

See [SPEC.md](SPEC.md) for the canonical specification and
[CHANGELOG.md](CHANGELOG.md) for the latest shipped capabilities.

---

## Reference and Companion Implementations

AIIR's specification is designed for third-party implementation, but the
current public language surfaces are still maintained by Invariant Systems.

| Language | Package / Path | Scope | Role |
| --- | --- | --- | --- |
| Python | [`aiir`](https://pypi.org/project/aiir/) | Full generate + verify + policy + CI/MCP | Canonical reference implementation |
| JavaScript | [`@invariantsystems/aiir`](sdks/js) | Verification helpers for browser and Node | Companion verifier SDK |
| Rust | [`aiir-cbor-verify`](sdks/rust) | Canonical CBOR encode/decode/verify | Companion CBOR proof surface |
| TypeScript | [`contrib/ts-verifier/`](contrib/ts-verifier) | Verification-only experiment | Spec-driven secondary verifier |

**No external-org implementation is listed yet.** The conformance manifest
([`schemas/conformance-manifest.json`](schemas/conformance-manifest.json)),
test vectors, and CDDL grammar are published to enable external implementors.
If you are interested in building one, start with
[docs/reference/implementers.md](docs/reference/implementers.md).

---

## Schema Evolution Policy

1. **CORE_KEYS are immutable within a major version.**
   The six core fields (`type`, `schema`, `version`, `commit`, `ai_attestation`,
   `provenance`) define the content hash. Adding or removing a core key is a
   major version change.

2. **Extensions are the expansion mechanism.**
   Any new data goes into `extensions.<namespace>`. Extensions are excluded
   from the content hash and are always optional for consumers.

3. **Promotion path**: `extensions.*` → observe for 2 minor versions →
   propose RFC → promote to CORE_KEY in next major version.

4. **Deprecation**: Deprecated fields remain in the schema for one full
   major version with a `deprecated: true` annotation before removal.

---

## Backward Compatibility Guarantees

- **Receipt JSON**: Any receipt produced by v1.0.0+ will verify correctly
  with any future v1.x verifier. New fields in `extensions` are ignored
  by older verifiers.

- **CLI flags**: No existing flag will change semantics. New flags are
  additive. Default behavior changes (e.g., signed-by-default) will be
  gated behind a minor version bump with opt-out.

- **Ledger format**: The JSONL append-only ledger and `index.json`
  structure are stable within v1.x. Future ledger features add new
  index fields without removing existing ones.

- **GitHub Action**: The `v1` floating tag always points to the latest
  v1.x.x release. Breaking changes require `v2`.

---

## Integration Recipes

AIIR ships integration guides for the main operator and integration paths:

| Recipe | Path |
| --- | --- |
| Claude Code hooks | [`docs/guides/claude-code-hooks.md`](docs/guides/claude-code-hooks.md) |
| GitLab Duo + CI/CD | [`docs/integrations/gitlab-duo-recipe.md`](docs/integrations/gitlab-duo-recipe.md) |
| GitLab Pages dashboard | [`docs/integrations/gitlab-pages-dashboard.md`](docs/integrations/gitlab-pages-dashboard.md) |
| MCP server configs | [README.md § MCP Tool](README.md#-mcp-tool--let-your-ai-do-it) (Claude, Copilot, Cursor, Continue, Cline, Windsurf) |
| GitHub Action | [README.md § GitHub Action](README.md#️-github-action--automate-it-in-ci) |
| pre-commit hook | [README.md § pre-commit](README.md#-pre-commit-hook--receipt-every-commit-locally) |
| Implementation and conformance registry | [`docs/reference/implementers.md`](docs/reference/implementers.md) |

### in-toto as the Integration Bridge

The `--in-toto` flag wraps every AIIR receipt in a standard
[in-toto Statement v1](https://in-toto.io/Statement/v1) envelope:

```json
{
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [{"name": "repo@sha", "digest": {"gitCommit": "abc..."}}],
   "predicateType": "https://invariantsystems.io/predicates/aiir/commit_receipt/v2",
  "predicate": { "...the full AIIR receipt..." }
}
```

Wrapped this way, AIIR receipts fit the supply-chain attestation
ecosystem. Tools from Sigstore policy-controller to Tekton Chains to
OPA/Gatekeeper consume this shape. The predicate
type URI (`https://invariantsystems.io/predicates/aiir/commit_receipt/v2`) allows routing policies
to match on AIIR-specific content without parsing the inner receipt.

---

## Security Model

See [THREAT_MODEL.md](THREAT_MODEL.md) for the full STRIDE/DREAD analysis.

Key architectural security properties:

- **Deterministic hashing**: Canonical JSON eliminates serialization ambiguity
- **Content addressing**: Receipt ID = f(content_hash, repo, commit); unforgeable
- **Sigstore transparency**: Signed receipts are logged in the Rekor transparency log
- **Zero-dependency core**: No supply chain attack surface in the core path
- **Schema validation**: Structural checks catch malformed receipts before hash verification

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and
the adversarial review protocol.

Architecture changes require an RFC (open an issue with the `rfc` label)
and must maintain backward compatibility within the current major version.
