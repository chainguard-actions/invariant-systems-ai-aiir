# Agent Trace Interoperability

> Public interoperability note. This page is descriptive, not a normative AIIR
> profile and not a request for Agent Trace to adopt AIIR wholesale.

AIIR and Agent Trace can occupy complementary layers.

- **Agent Trace** can be the portable attribution and event format that tools
  emit across IDEs, terminals, CI, and hosted agents.
- **AIIR** can be the deterministic, content-addressed evidence layer that
  preserves, signs, verifies, and policy-checks those records when a workflow
  needs tamper-evidence.

The safe integration posture is additive: AIIR can bind or reference Agent Trace
records for audit-grade use cases, while Agent Trace remains implementation
neutral.

---

## Layering Model

| Layer | Primary job | Interoperability boundary |
| --- | --- | --- |
| Agent Trace | Portable attribution and action metadata | Defines the event shape tools can exchange |
| AIIR agent receipts | Deterministic hashing, IDs, and optional signatures for agent actions | Can record Agent Trace artifacts as inputs or outputs |
| AIIR commit receipts | Commit-level provenance and release policy evidence | Can summarize or link lower-level agent records |
| Sigstore / in-toto / transparency logs | Identity binding and public evidence publication | Can sign or publish AIIR receipts and wrapped statements |

This keeps each layer narrow. Agent Trace does not need to become a signing
system, and AIIR does not need to become the portable event vocabulary for every
agent tool.

---

## Interoperability Patterns

### 1. AIIR Receipts Reference Agent Trace Records

An AIIR agent receipt can include an Agent Trace file, bundle, URL, or digest as
an artifact reference. In the AIIR agent-receipt profile, `artifacts` are part
of the hashed core, so a digest placed there is covered by `proof.content_hash`.

Example shape, shortened for clarity:

```json
{
  "artifacts": {
    "inputs": [
      {
        "type": "bundle",
        "ref": "agent-trace/session-2026-05-11.json",
        "digest": "sha256:...",
        "role": "external"
      }
    ],
    "outputs": []
  }
}
```

This pattern is useful when a tool already emits Agent Trace and a repository
wants a local, content-addressed evidence record without changing the trace
producer.

### 2. Agent Trace Records Reference AIIR Receipts

An Agent Trace record can point to an AIIR receipt using implementation-specific
metadata. Suggested experimental keys, if the Agent Trace extension model allows
namespaced metadata:

```json
{
  "io.invariantsystems.aiir.profile": "aiir/agent_receipt.v0.1",
  "io.invariantsystems.aiir.record_id": "a1-...",
  "io.invariantsystems.aiir.content_hash": "sha256:...",
  "io.invariantsystems.aiir.receipt_uri": "https://example.invalid/receipts/a1-....json"
}
```

Those fields are cross-references only unless the Agent Trace specification
defines which metadata participates in its own hash input or signature envelope.
Embedding an AIIR pointer in otherwise-unbound metadata does not make the Agent
Trace record tamper-evident by itself.

### 3. AIIR Commitment Receipts Bind Agent Trace Bundles

For a directory or bundle of Agent Trace records, an AIIR commitment receipt can
bind the directory manifest or declared digests before publication. This is a
good fit for release packets, audit handoffs, or evidence bundles where the
individual trace records should remain in their native format.

---

## What Is Cryptographically Bound

The distinction between evidence and metadata is important:

| Placement | AIIR binding status |
| --- | --- |
| AIIR `artifacts.inputs[*].digest` or `artifacts.outputs[*].digest` in the agent-receipt core | Covered by the AIIR content hash |
| AIIR commit-receipt core fields | Covered by the AIIR content hash |
| AIIR `extensions` fields in the current draft profile | Informational only; excluded from the content hash |
| Agent Trace vendor metadata pointing to AIIR | Informational unless Agent Trace defines a hash/signature profile for that metadata |
| Unsigned AIIR receipt | Tamper-evident integrity, not authenticated origin |
| Signed AIIR receipt | Integrity plus signer identity, subject to the verifier's trust policy |

When in doubt, verifiers should treat cross-format links as pointers until they
can recompute the relevant hash and verify the relevant signature or trust
policy.

---

## Suggested Agent Trace Spec Hook

For Agent Trace use cases that need tamper-evidence, the key spec hook is a
narrow cryptographic profile. A useful profile would define:

- the exact hash input model for an Agent Trace record
- the serialization or canonicalization rules used before hashing
- algorithm agility, at least for digest algorithms
- whether extension or vendor metadata is included, excluded, or profile-defined
- test vectors for independent implementations
- an optional signature or transparency reference model

The hook should stay implementation-neutral. AIIR can be cited as one existing
implementation with public canonicalization rules, test vectors, and a threat
model, but the Agent Trace specification should not require AIIR.

See [drafts/agent-trace-section-6-6-crypto-profile-issue.md](drafts/agent-trace-section-6-6-crypto-profile-issue.md)
for a ready-to-file issue draft.

---

## Non-Goals

This note does not propose to:

- replace the Agent Trace data model
- make Agent Trace depend on AIIR
- standardize prompts, hidden reasoning, or model internals
- treat self-declared tool labels as authenticated identity
- claim that metadata-only links are tamper-evident

The goal is a clean evidence bridge: Agent Trace records what happened in a
portable way; AIIR can make selected records deterministic, signable, and
verifiable when a workflow needs that stronger property.
