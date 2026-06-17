# AIIR Agent-Receipt Profile

> Draft profile for portable receipts covering agent-assisted software work.
>
> Status: public draft (v0.1). Companion to the existing AIIR commit-receipt
> profile. Hosted under Apache-2.0 by the AIIR project.

AIIR receipts come in two profiles:

| Profile | Schema id | record_id prefix | Binds to |
|---|---|---|---|
| Commit | `aiir/commit_receipt.v2` | `g1-` | one git commit |
| Agent  | `aiir/agent_receipt.v0.1` | `a1-`  | one agent action |

Both profiles share the same canonicalization (`aiir-canon-0`), the same
content-addressed hash construction, the same trust ladder, and the same
in-toto wrapping path. The only difference is **what gets receipted**:
a commit, or a finer-grained agent action that may later compose into a
commit receipt.

This document specifies the agent profile.

Machine-readable artifacts:

- [schemas/agent_receipt_contract.v0.1.schema.json](../schemas/agent_receipt_contract.v0.1.schema.json)
- [schemas/agent_receipt_vectors.v0.1.schema.json](../schemas/agent_receipt_vectors.v0.1.schema.json)
- [schemas/test-vectors/agent_receipt_vectors.v0.1.json](../schemas/test-vectors/agent_receipt_vectors.v0.1.json)

Related interoperability note:

- [Agent Trace interoperability](agent-trace-interoperability.md)

---

## What problem this solves

Coding agents now read code, edit files, run tests, browse docs, open pull
requests, and trigger deployments. Today those actions are hard to compare
across tools because each vendor emits different logs, different schemas, or no
portable evidence at all.

The agent-receipt profile gives every tool one minimal way to answer five
questions:

1. Who acted?
2. What tool or surface acted?
3. What happened?
4. What artifacts were read or changed?
5. What policy decision allowed, warned, blocked, or deferred that action?

The commit-receipt profile already answers similar questions at commit
granularity. The agent profile fills the gap underneath: actions that occur
*before* a commit lands, or that never reach a commit at all (browse, review,
deploy, test runs, MCP-mediated actions).

---

## Non-goals

This profile does not attempt to do the following:

- standardize system prompts
- detect undeclared AI usage
- require a hosted control plane
- replace SLSA, in-toto, Sigstore, or SCITT
- force vendors to expose private reasoning or model internals
- ship file contents or prompt contents by default

The point is portable evidence, not intrusive telemetry.

---

## Design rules

Same rules as the commit-receipt profile:

1. **Local-first** — a tool can emit valid records offline.
2. **Deterministic** — the same record hashes the same way everywhere.
3. **Minimal** — vendors can adopt it in a day, not a quarter.
4. **Composable** — it can feed commit receipts, in-toto statements, and
   policy engines.
5. **Privacy-preserving** — prompts, file contents, and secrets are optional
   and absent by default.
6. **Surface-agnostic** — IDEs, terminals, bots, MCP servers, and CI all fit.

---

## Core record

The record is one JSON object with five logical sections:

- `actor`
- `action`
- `artifacts`
- `policy`
- `proof`

### Minimal example

```json
{
  "contract_version": "aiir/agent_receipt.v0.1",
  "record_id": "a1-ba371a1f33cae92426f311113bb802e0",
  "timestamp": "2026-04-26T18:20:00Z",
  "actor": {
    "kind": "agent",
    "tool": {
      "name": "copilot",
      "surface": "vscode-agent"
    },
    "session_ref": "sess_01"
  },
  "action": {
    "kind": "edit",
    "intent": "apply_patch",
    "summary": "Add receipt verification guard"
  },
  "artifacts": {
    "inputs": [
      { "type": "file", "ref": "aiir/cli.py", "role": "source" }
    ],
    "outputs": [
      { "type": "file", "ref": "aiir/cli.py", "role": "source" },
      { "type": "test", "ref": "tests/test_cli.py::test_export_guard", "role": "evidence" }
    ]
  },
  "policy": {
    "decision": "allowed",
    "reasons": [
      "workspace_context_loaded",
      "local_verification_required"
    ],
    "contract_ref": "aiir://policy/local-default"
  },
  "proof": {
    "canonicalization": "aiir-canon-0",
    "content_hash": "sha256:ba371a1f33cae92426f311113bb802e0... (full 256-bit hash; see test vectors)",
    "signature": null
  }
}
```

The exact byte sequences for canonical JSON and full hashes are pinned in the
[test vectors](../schemas/test-vectors/agent_receipt_vectors.v0.1.json).

### Required top-level fields

| Field | Type | Required | Meaning |
|---|---|---|---|
| `contract_version` | string | yes | Versioned profile identifier (`aiir/agent_receipt.v0.1`) |
| `record_id` | string | yes | Stable ID derived from the record core (`a1-…`) |
| `timestamp` | string | yes | RFC 3339 UTC timestamp |
| `actor` | object | yes | Who or what performed the action |
| `action` | object | yes | What happened |
| `artifacts` | object | yes | Inputs and outputs referenced by the action |
| `policy` | object | yes | Portable decision outcome |
| `proof` | object | yes | Hashing and optional signature metadata |
| `extensions` | object | no | Optional namespaced extension fields (see below) |

### Actor fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `actor.kind` | string | yes | One of `human`, `agent`, `bot`, `mixed` |
| `actor.tool.name` | string | yes | Lowercase ASCII tool label such as `copilot`, `claude-code`, `cursor`, `windsurf`, `warp`, `devin`, `github-actions`, `unknown` |
| `actor.tool.surface` | string | no | Surface such as `vscode-agent`, `cli`, `terminal-agent`, `github-app`, `gitlab-job`, `mcp` |
| `actor.session_ref` | string | no | Tool-local session or conversation identifier (see privacy rules) |

`actor.tool.name` and `actor.tool.surface` are informational labels only.
Implementations MUST normalize them to lowercase ASCII before emission. They
are NOT authenticated unless the record carries a signature whose verification
binds tool identity to a key (see *Tool identity and trust*).

### Action fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `action.kind` | string | yes | One of `read`, `edit`, `run`, `test`, `build`, `review`, `browse`, `apply`, `open_pr`, `deploy` |
| `action.intent` | string | no | Tool-native action name such as `apply_patch`, `pytest`, `open_browser`, `git_diff` |
| `action.summary` | string | no | Short human-readable explanation |

### Artifact fields

`artifacts.inputs` and `artifacts.outputs` are arrays of objects with this
shape:

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | string | yes | `file`, `commit`, `test`, `bundle`, `url`, `issue`, `pr`, `directory`, `other` |
| `ref` | string | yes | Portable reference such as a file path, URL, commit SHA, or test name |
| `digest` | string | no | Optional content hash when available |
| `role` | string | no | Optional subtype such as `source`, `result`, `evidence`, `external` |

### Policy fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `policy.decision` | string | yes | One of `allowed`, `warned`, `blocked`, `needs_review`, `not_evaluated` |
| `policy.reasons` | array[string] | no | Stable reason codes or short strings |
| `policy.contract_ref` | string | no | Link or identifier for the policy contract used |

### Proof fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `proof.canonicalization` | string | yes | Canonicalization profile identifier (`aiir-canon-0`) |
| `proof.content_hash` | string | yes | Full SHA-256 of the canonical record core |
| `proof.signature` | object or null | no | Optional signature metadata |

### Extensions

`extensions` is an optional object for vendor- or surface-specific metadata.
Keys SHOULD use a reverse-DNS prefix (`io.invariantsystems.aiir`,
`com.example.tool`) or an `x-` prefix (`x-cursor-context`). To preserve
deterministic hashing across implementations that do not understand a given
extension, **`extensions` is excluded from `record_core` in v0.1** and
therefore does not contribute to `content_hash` or `record_id`. Treat
extensions as informational metadata only at this draft stage.

---

## Canonicalization and IDs

### Profile name

The v0.1 canonicalization profile is **`aiir-canon-0`**, shared with the AIIR
commit-receipt profile.

This profile is *not* RFC 8785 JSON Canonicalization Scheme (JCS): JCS uses
ECMA-262 number serialization and does not require ASCII-safe escaping.
`aiir-canon-0` follows AIIR's existing public canonicalization rules from
[SPEC.md](../SPEC.md) section 6.5:

- lexicographic key ordering
- no structural whitespace (`","` and `":"` separators)
- ASCII-safe escaping (`ensure_ascii: true`)
- no `NaN` or `Infinity`
- decimal integer formatting
- maximum depth of 64

### Record ID derivation

```text
record_id = "a1-" + hex(SHA-256(canonical_json(record_core)))[:32]
```

`record_id` is a 128-bit truncation of the SHA-256 hash. The full 256-bit
hash is retained in `proof.content_hash`; verifiers MUST compare the full hash
when establishing record equality. The 128-bit prefix is a compact display and
indexing label, accepted as a tradeoff because:

- expected per-corpus receipt volumes (≤ 10^9) keep birthday-collision
  probability at a level acceptable for index keys, and
- any verifier that needs exact equality already has access to the full hash
  in the same record.

The `a1-` prefix is intentionally parallel to the commit-receipt profile's
`g1-` prefix.

### record_core

For `aiir/agent_receipt.v0.1`, `record_core` is the object containing:

- `contract_version`
- `timestamp`
- `actor`
- `action`
- `artifacts`
- `policy`
- `proof.canonicalization`

Implementations MUST exclude these derived, non-deterministic, or extension
fields from canonicalization:

- `record_id`
- `proof.content_hash`
- `proof.signature`
- `extensions`

---

## Privacy defaults

This profile is designed to be easy to adopt in public and enterprise settings.
That means the defaults matter.

Compliant emitters SHOULD:

- include references to files and external resources, not raw contents
- omit prompts by default
- omit chain-of-thought or hidden reasoning by default
- hash sensitive payloads before including them when reference-only is
  insufficient
- keep secrets and credentials completely out of the record

Compliant emitters MUST NOT:

- place identifiers that map to a natural person directly into
  `actor.session_ref` (use opaque or hashed values instead)
- copy raw prompts, raw model output, or raw file contents into any field

---

## Tool identity and trust

`actor.tool.name` is a free-form lowercase label. It identifies the tool only
in the same way an HTTP `User-Agent` does: as a self-declaration. A record
emitted with `actor.tool.name = "copilot"` is **not** evidence that Copilot
actually performed the action.

Tool identity becomes meaningful only at Adoption Ladder Level 2 or higher,
when the record is signed by a key that verifiers can bind to a particular
tool, vendor, organization, or workload identity (for example via a
Sigstore-like keyless signature, in-toto wrapping, or SCITT-style transparency
log).

Implementations and downstream consumers SHOULD therefore:

- treat `actor.tool.name` as informational at Levels 0 and 1
- require a signature plus a vendor-trust binding before treating the label as
  authenticated
- log unsigned records under a "self-declared, unverified" classification when
  pivoting on tool identity

---

## Verifier semantics

A conforming verifier MUST:

- recompute `canonical_json(record_core)`, compare the SHA-256 to the
  `proof.content_hash`, and reject mismatches
- recompute `record_id` and reject mismatches
- reject records whose `extensions` are present inside `record_core` (they
  must be outside the hashed core)
- treat `actor.tool.name` as informational unless a signature binding is
  verified

A conforming verifier SHOULD treat the `policy.decision` values as follows by
default:

| decision | default verifier treatment |
|---|---|
| `allowed` | accept |
| `warned` | accept with warning surfaced |
| `blocked` | reject (action should not have proceeded) |
| `needs_review` | hold (do not auto-accept; require human acknowledgment) |
| `not_evaluated` | accept *only* in advisory contexts; reject in any policy-gated context |

`not_evaluated` is the Adoption Ladder Level 0 value. Verifiers MUST NOT
silently treat it as `allowed`; production policy gates SHOULD fail closed.

---

## Adoption ladder

Same ladder shape as the commit-receipt profile.

### Level 0 — Declaration only

Emit the required fields with `policy.decision = "not_evaluated"` and no
signature. Acceptable in advisory contexts; not acceptable in policy-gated
ones.

### Level 1 — Deterministic proof

Emit a valid `proof.content_hash` and stable `record_id`. Acceptable for
content-addressed indexing and offline verification; tool identity remains
self-declared.

### Level 2 — Signed evidence

Add signature metadata or attach the record to a signed bundle. At this level
verifiers can begin treating tool identity as authenticated, subject to the
binding between key and tool.

### Level 3 — Supply-chain binding

Bind the record to a commit receipt, in-toto statement, or release artifact.

The ladder matters because vendors can start at Level 0 or 1 without a hosted
service, a PKI rollout, or a central policy engine.

---

## Mapping to current tools

| Tool or surface | Natural mapping |
|---|---|
| Copilot / VS Code Agent | `actor.tool.name = "copilot"`; `surface = "vscode-agent"`; action kinds map to read, edit, run, test, browse |
| Claude Code | `actor.tool.name = "claude-code"`; CLI and repo actions map directly |
| Cursor | `actor.tool.name = "cursor"`; agent edits and repo scans map directly |
| Windsurf | `actor.tool.name = "windsurf"`; browser and editor actions fit the same model |
| Warp | `actor.tool.name = "warp"`; terminal-native runs, tests, builds, and reviews map directly |
| CI bots | `actor.kind = "bot"`; `actor.tool.name = "github-actions"` or `"gitlab-ci"`; `surface = "github-app"` or `gitlab-job` |

The profile is intentionally about action evidence, not prompt wording. That is
why cross-vendor adoption is plausible.

---

## Relationship to the commit-receipt profile

The agent profile is a sibling, not a replacement. Both profiles share:

- the same canonicalization (`aiir-canon-0`)
- the same hash construction (SHA-256, truncated 128-bit ID)
- the same Sigstore + in-toto wrapping path
- the same trust ladder

A typical workflow:

1. An IDE agent emits one or more `aiir/agent_receipt.v0.1` records during a
   session (Level 0 or 1).
2. When the session lands as a git commit, an `aiir/commit_receipt.v2` record
   is emitted by the existing AIIR CLI or Action.
3. The commit receipt MAY reference the prior agent receipts via
   `extensions` or via in-toto subject linkage; this composition pattern is
   intentionally left flexible until v0.2.

---

## Why this should live in public

If the profile is useful, it should be publicly reviewable, independently
implementable, and safe for competitors to adopt:

- Apache-2.0 host repo
- public issues and pull requests
- stable canonical examples
- no dependency on leaked prompts
- no dependency on a private control plane

Public adoption is the point.

---

## Next steps

1. Validate the draft schema and vectors against at least one second
   implementation (a small JS or Rust verifier round-trip on the v0.1 vectors).
2. Implement a small first-party verifier in AIIR.
3. Invite IDE, terminal, MCP, and CI vendors to emit Level 0 or Level 1
   records.
4. Add signature guidance and interoperability notes for signed envelopes.
5. Specify commit↔agent composition rules in v0.2.

Until then, this document should be treated as a public draft profile with a
concrete implementation path, not a settled standard.
