---
title: "AIIR Commit Receipt Format"
abbrev: "AIIR Commit Receipts"
category: info
docname: draft-invariantsystems-aiir-receipt-00
submissionType: IETF
ipr: trust200902
area: Security
workgroup: Internet Engineering Task Force
keyword: AI provenance, software supply chain, receipts, content addressing
stand_alone: yes
pi: [toc, sortrefs, symrefs]
author:
  -
    fullname: Noah
    organization: Invariant Systems, Inc.
    email: noah@invariantsystems.io
normative:
  RFC8259:
  RFC8610:
  RFC8785:
  RFC8949:
  RFC6838:
informative:
  InTotoStatement:
    title: "in-toto Attestation Framework: Statement v1"
    target: "https://in-toto.io/Statement/v1"
  Sigstore:
    title: "Sigstore"
    target: "https://sigstore.dev/"
  AIIRSpec:
    title: "AIIR Commit Receipt Specification"
    target: "https://github.com/invariant-systems-ai/aiir/blob/main/SPEC.md"
--- abstract

This document specifies the AIIR Commit Receipt format, a deterministic,
content-addressed JSON object for recording declared AI involvement in git
commits. The format defines receipt structure, canonical JSON encoding,
content hashing, receipt identifiers, verification procedures, and extension
handling. The format is intended to provide portable authorship-provenance
evidence that can be verified locally, in CI, or inside broader supply-chain
attestation systems.

--- middle

# Introduction

AI-assisted software development increasingly leaves important authorship
context outside the durable software supply chain. Git commit metadata can
record authors and commit messages, but it does not provide a deterministic,
tamper-evident claim that a commit involved an AI coding assistant, bot, or
declared tool workflow.

An AIIR Commit Receipt records commit metadata, AI-authorship signals, and
provenance metadata in a canonical JSON object. The receipt core is hashed with
SHA-256 to derive a `content_hash` and a compact `receipt_id`. Any conforming
implementation presented with the same core object produces identical values.

AIIR receipts operate at the authorship-provenance layer. They do not replace
build provenance, vulnerability scanning, or transparency logs. Receipts can,
however, be wrapped in in-toto Statement v1 envelopes {{InTotoStatement}}, signed
with Sigstore {{Sigstore}}, or attached to other supply-chain evidence flows.
This draft is derived from the public AIIR specification {{AIIRSpec}}.

# Terminology

{::boilerplate bcp14-tagged}

The following terms are used in this document:

CORE_KEYS:
: The exact top-level receipt fields that contribute to `content_hash` and
  `receipt_id`.

Receipt core:
: The receipt object filtered to CORE_KEYS.

Receipt identifier:
: The `g1-` identifier derived from the first 32 hexadecimal characters of the
  SHA-256 digest of the canonical receipt core.

Extension:
: Non-core metadata stored under `extensions`. Extensions do not affect the
  receipt content hash unless bound by an external signed envelope.

# Receipt Structure

An AIIR Commit Receipt is a JSON object with these top-level fields:

| Field | Type | In CORE_KEYS | Description |
|---|---|---:|---|
| `type` | string | yes | Constant `aiir.commit_receipt`. |
| `schema` | string | yes | Constant `aiir/commit_receipt.v2`. |
| `version` | string | yes | Semantic version of the generating tool. |
| `commit` | object | yes | Git commit metadata and DAG binding. |
| `ai_attestation` | object | yes | AI and bot authorship detection result. |
| `provenance` | object | yes | Repository and generator metadata. |
| `receipt_id` | string | no | Derived compact content identifier. |
| `content_hash` | string | no | Full SHA-256 digest of the canonical core. |
| `timestamp` | string | no | RFC 3339 UTC generation time. |
| `extensions` | object | no | Open extension object. |

The CORE_KEYS set is exactly `type`, `schema`, `version`, `commit`,
`ai_attestation`, and `provenance`.

These six keys, and only these six keys, are the input to content addressing.
Future schema versions MUST NOT add top-level fields to CORE_KEYS without
changing the schema identifier.

## Commit Object

The `commit` object contains:

| Field | Type | Required | Description |
|---|---|---:|---|
| `sha` | string | yes | Full git commit object identifier, 40 or 64 lowercase hex characters. |
| `tree_sha` | string | yes | Full git tree object identifier for the commit. |
| `parent_shas` | array | yes | Ordered parent commit identifiers; empty for root commits. |
| `author` | object | yes | Git author identity. |
| `committer` | object | yes | Git committer identity. |
| `subject` | string | yes | First line of the commit message. |
| `message_hash` | string | yes | `sha256:` plus SHA-256 of the full commit message body. |
| `diff_hash` | string | yes | `sha256:` plus SHA-256 of the full git diff. |
| `files_changed` | integer | yes | Number of changed files. |
| `files` | array | conditional | Changed file paths, capped at 100, when not redacted. |
| `files_redacted` | true | conditional | Present when file paths are redacted. |
| `files_capped` | true | optional | Present when `files` was truncated. |

Exactly one of `files` or `files_redacted` MUST be present.

The `tree_sha` and `parent_shas` fields bind the receipt to a directory state
and DAG position. Verifiers SHOULD reject receipts that omit either field for
the v2 schema.

## Git Identity

A git identity object contains required `name`, `email`, and `date` string
fields. The `date` field MAY be an RFC 3339 timestamp or a git default date
string. Producers SHOULD prefer RFC 3339 when available.

## AI Attestation Object

The `ai_attestation` object contains:

| Field | Type | Required | Description |
|---|---|---:|---|
| `is_ai_authored` | boolean | yes | True when any AI authorship signal was detected or declared. |
| `signals_detected` | array | yes | AI authorship signals. |
| `signal_count` | integer | yes | Count of AI authorship signals. |
| `detection_method` | string | yes | Detection algorithm identifier. |
| `is_bot_authored` | boolean | optional | True when bot authorship signals were detected. |
| `bot_signals_detected` | array | optional | Bot authorship signals. |
| `bot_signal_count` | integer | optional | Count of bot authorship signals. |
| `authorship_class` | string | optional | `human`, `ai_assisted`, `bot`, or `ai+bot`. |

The legacy value `ai_generated` MAY be accepted by validators for backward
compatibility but SHOULD NOT be produced for v2 receipts.

## Provenance Object

The `provenance` object contains:

| Field | Type | Required | Description |
|---|---|---:|---|
| `repository` | string or null | yes | Git remote URL with credentials stripped, or null. |
| `tool` | string | yes | Tool URI, such as `https://github.com/invariant-systems-ai/aiir@1.5.1`. |
| `generator` | string | yes | Generator identifier, such as `aiir.cli`, `aiir.github`, `aiir.gitlab`, or `aiir.mcp`. |

Producers MUST remove URL userinfo, query strings, and fragments from
`repository` before including the value in a receipt.

# Canonical JSON Encoding {#sec-canonical-json}

The canonical JSON encoding is the deterministic serialization used for content
addressing. Implementations MUST produce byte-identical output for identical
receipt cores.

The algorithm is:

1. Serialize JSON objects with keys sorted lexicographically by Unicode code
   point.
2. Use no structural whitespace. Separators MUST be exactly `,` and `:`.
3. Escape all non-ASCII characters as `\uXXXX`.
4. Reject NaN and Infinity values.
5. Recursively apply key sorting to nested objects.
6. Reject structures deeper than 64 nested levels.

For the types used in CORE_KEYS (strings, integers, booleans, null, arrays, and
objects), this encoding is byte-identical to the relevant JSON Canonicalization
Scheme behavior {{RFC8785}}. If a future schema version adds floating-point
values to CORE_KEYS, the canonicalization algorithm MUST be revised or replaced
with a full RFC 8785 implementation.

Example input:

~~~ json
{"b":1,"a":{"d":2,"c":3}}
~~~

Canonical output:

~~~
{"a":{"c":3,"d":2},"b":1}
~~~

# Content Addressing

The content hash is:

~~~
content_hash = "sha256:" + hex(SHA-256(canonical_json(core)))
~~~

The receipt identifier is:

~~~
receipt_id = "g1-" + hex(SHA-256(canonical_json(core)))[:32]
~~~

The SHA-256 input is the UTF-8 encoding of the canonical JSON string. The
`receipt_id` is a compact 128-bit identifier and MUST NOT be used as the only
integrity check. Verifiers MUST check `content_hash`.

# Extensions

The `extensions` object is open for downstream metadata. Extension data is not
part of CORE_KEYS and does not affect `content_hash` or `receipt_id`.

Receipts that rely on extension fields for policy decisions SHOULD be signed or
wrapped in a signed envelope, because unsigned extensions can be modified
without changing the core content hash.

Known extension keys include `instance_id`, `namespace`, `agent_attestation`,
`editor_provenance`, and `tool_context`.

# Verification Procedure

To verify a receipt, an implementation MUST:

1. Parse the file as UTF-8 JSON.
2. Verify that the top-level value is a JSON object or a bounded array of JSON
   objects.
3. Verify the required fields and field types.
4. Verify `type` equals `aiir.commit_receipt`.
5. Verify `schema` equals `aiir/commit_receipt.v2` for v2 receipts.
6. Verify `version` matches Semantic Versioning syntax.
7. Extract the receipt core by filtering the top-level object to CORE_KEYS.
8. Compute canonical JSON for the receipt core.
9. Compute the expected `content_hash` and `receipt_id`.
10. Compare both expected values to the receipt fields using constant-time
    comparison, such as `hmac.compare_digest`.

The receipt is valid if and only if both comparisons succeed.

On verification failure, implementations SHOULD report which check failed, but
MUST NOT expose the expected hash value. Exposing the expected hash creates a
forgery oracle.

# File Verification

When verifying receipts from files, implementations MUST reject symlinks, reject
files larger than 50 MB, parse as UTF-8 JSON, support a single receipt object or
a bounded array, and cap receipt arrays at 1000 entries.

# Signing and Attestation Envelopes

Unsigned receipts provide tamper evidence for the core object but not signer
authenticity. Anyone able to reconstruct the same core can generate the same
receipt.

Receipts MAY be signed with Sigstore {{Sigstore}}. A valid signature binds the full receipt
JSON, including extensions, to an OIDC identity and transparency log entry.

Receipts MAY also be wrapped in an in-toto Statement v1 envelope {{InTotoStatement}}. The predicate
type URI for `aiir/commit_receipt.v2` is:

~~~
https://invariantsystems.io/predicates/aiir/commit_receipt/v2
~~~

Implementations that wrap receipts in in-toto Statements MUST use a predicate
type URI matching the wrapped receipt schema.

# Security Considerations {#sec-security}

Implementations MUST use constant-time comparison for `content_hash` and
`receipt_id`. Implementations MUST NOT reveal expected hash values on failure.

Receipts contain user-controlled text from git metadata, including names, email
addresses, commit subjects, and file paths. Display layers MUST sanitize output
to prevent terminal escape, log injection, and HTML/script injection.

The `repository` field can contain secrets if collected from an unsafe remote
URL. Producers MUST strip credentials, query strings, and fragments before
including the value.

Canonicalization implementations MUST enforce a depth limit to avoid stack
exhaustion. File readers MUST reject symlinks and oversized inputs to reduce
filesystem probing and denial-of-service risk.

Extensions are mutable without changing the core content hash. Policy engines
MUST NOT treat unsigned extension values as audit-grade evidence.

# IANA Considerations

## Media Type Registration

This document requests registration of the following media type in the vendor
tree, following RFC 6838 {{RFC6838}}.

Type name:
: application

Subtype name:
: vnd.aiir.commit-receipt+json

Required parameters:
: None

Optional parameters:
: `schema`, the receipt schema identifier. When absent, consumers SHOULD inspect
  the `schema` field in the JSON body.

Encoding considerations:
: 8bit; the content is UTF-8 encoded JSON per RFC 8259 {{RFC8259}}.

Security considerations:
: See {{sec-security}}.

Interoperability considerations:
: All conforming implementations produce identical `content_hash` and
  `receipt_id` values for the same receipt core.

Published specification:
: This document.

Applications which use this media type:
: AIIR CLI, CI/CD pipelines, MCP servers, compliance systems, and supply-chain
  attestation tools.

Fragment identifier considerations:
: None.

Restrictions on usage:
: None.

Additional information:
: File extensions: `.json` and `.jsonl`. Magic number: none.

Person and email address to contact:
: Noah, `noah@invariantsystems.io`.

Intended usage:
: COMMON.

Change controller:
: Invariant Systems, Inc.

## Schema URI

The JSON Schema URI for this format is
`https://invariantsystems.io/schemas/aiir/commit_receipt.v2.schema.json`.

--- back

# CDDL Grammar

This appendix is normative for the CDDL {{RFC8610}} description of the v2
receipt shape, including the CBOR {{RFC8949}} envelope shape. The canonical JSON
algorithm in {{sec-canonical-json}} remains the normative content-addressing
serialization.

~~~ cddl
commit-receipt = {
  type:            "aiir.commit_receipt",
  schema:          "aiir/commit_receipt.v2",
  version:         semver,
  commit:          commit-object,
  ai_attestation:  ai-attestation,
  provenance:      provenance,
  receipt_id:      receipt-id,
  content_hash:    content-hash,
  timestamp:       date-time,
  extensions:      extensions,
}

commit-receipt-core = {
  type:            "aiir.commit_receipt",
  schema:          "aiir/commit_receipt.v2",
  version:         semver,
  commit:          commit-object,
  ai_attestation:  ai-attestation,
  provenance:      provenance,
}

commit-object = {
  sha:             git-sha,
  tree_sha:        git-sha / "",
  parent_shas:     [* git-sha],
  author:          git-identity,
  committer:       git-identity,
  subject:         tstr .size (0..4096),
  message_hash:    sha256-prefixed,
  diff_hash:       sha256-prefixed,
  files_changed:   uint,
  (files-present // files-redacted),
  ? files_capped:  true,
}

files-present = (files: [0*100 tstr])
files-redacted = (files_redacted: true)

git-identity = {
  name:   tstr .size (0..1024),
  email:  tstr .size (0..1024),
  date:   tstr,
}

ai-attestation = {
  is_ai_authored:         bool,
  signals_detected:       [* tstr],
  signal_count:           uint,
  detection_method:       tstr,
  ? is_bot_authored:      bool,
  ? bot_signals_detected: [* tstr],
  ? bot_signal_count:     uint,
  ? authorship_class:     authorship-class,
}

authorship-class = "human" / "ai_assisted" / "bot" /
                   "ai+bot" / "ai_generated"

provenance = {
  repository:  tstr / null,
  tool:        tool-uri,
  generator:   tstr,
}

extensions = {
  ? instance_id:  tstr,
  ? namespace:    tstr,
  * tstr => any,
}

receipt-id       = tstr .regexp "^g1-[0-9a-f]{32}$"
content-hash     = tstr .regexp "^sha256:[0-9a-f]{64}$"
semver           = tstr
git-sha          = tstr .regexp "^[0-9a-f]{40}$" /
                   tstr .regexp "^[0-9a-f]{64}$"
sha256-prefixed  = tstr .regexp "^sha256:[0-9a-f]{64}$"
date-time        = tstr
tool-uri         = tstr
~~~