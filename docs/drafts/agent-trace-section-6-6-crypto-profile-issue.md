# Draft Issue: Define A Cryptographic Profile Hook For Agent Trace Records

## Title

Define a cryptographic profile hook for Agent Trace records

## Body

### Summary

For Agent Trace use cases that need audit-grade tamper evidence, the
specification should define a narrow, implementation-neutral cryptographic
profile hook. The goal is not to require signing for every trace record. The
goal is to make it possible for independent implementations to compute the same
digest over the same record bytes and, when needed, attach or reference a
signature or transparency entry.

If section 6.6 is the right home for vendor metadata or extension handling, this
could fit there as an optional profile for records that need stronger integrity
semantics.

### Problem

Agent Trace records may be used in workflows where the trace is later reviewed
by security teams, auditors, policy engines, or release gates. In those cases,
metadata alone is not enough: consumers need to know which fields were included
in the digest, how those fields were serialized, which algorithms are allowed,
and whether extension or vendor metadata is covered by the hash.

Without a defined profile hook, vendors can still add their own digests or
signatures, but those proofs will be hard to compare across tools and hard for
third-party verifiers to reproduce.

### Proposal

Add an optional cryptographic profile mechanism that defines, at minimum:

1. **Hash input model**: the exact set of fields included in the digest input.
2. **Serialization or canonicalization**: the deterministic bytes to hash.
3. **Digest algorithm agility**: a field or registry for algorithms such as
   SHA-256, plus rules for future algorithms.
4. **Extension handling**: whether vendor metadata is included, excluded, or
   profile-selected.
5. **Test vectors**: at least one canonical record, canonical byte string or
   equivalent representation, expected digest, and negative vector.
6. **Optional signature reference**: a way to attach or reference signatures,
   envelopes, or transparency-log entries without requiring any one signing
   system.

The profile should be optional. Producers that only need portable event
metadata can ignore it. Producers that need audit-grade evidence can emit it.

### Non-Goals

- Do not require all Agent Trace records to be signed.
- Do not require one specific signing system, transparency log, or vendor.
- Do not require exposing prompts, hidden reasoning, model internals, or file
  contents.
- Do not make the core Agent Trace data model depend on any one implementation.

### Existing Implementation Experience

AIIR is one public implementation that may be useful as prior art, not as a
required dependency. It already publishes:

- deterministic canonicalization rules (`aiir-canon-0`)
- content-addressed IDs and full SHA-256 hashes
- signed and unsigned verification semantics
- public JSON schemas and test vectors
- a threat model that distinguishes metadata, integrity, and authenticated
  origin

That experience suggests the most important spec distinction is between fields
that are merely metadata and fields that are included in the digest input.

### Acceptance Criteria

A good resolution would let an independent implementer answer these questions
without contacting the original producer:

- Which bytes do I hash for this Agent Trace record?
- Which fields are excluded from the hash?
- Is vendor metadata covered by the digest?
- Which digest algorithm is in use?
- How do I verify the digest against a published test vector?
- If a signature is present, what is signed and where is the signature recorded?

### Suggested Wording Direction

The spec could define an optional `cryptographic_profile` or equivalent profile
reference. Exact field names should follow the existing Agent Trace style, but
the semantics should be explicit: profile identifier, digest algorithm, digest
input rules, digest value, extension handling, and optional signature or
transparency reference.

This keeps the core format portable while leaving a clean path for
tamper-evident and independently verifiable Agent Trace records.
