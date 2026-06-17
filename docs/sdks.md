# AIIR SDKs

Public guide to the language-specific AIIR surfaces in this repository.

AIIR has one reference implementation and two language SDKs today:

- The Python package is the reference implementation. It generates receipts,
  verifies receipts, emits release attestations, evaluates policy, and exposes
  the CLI, GitHub Action, GitLab CI component, and MCP server.
- The JavaScript package is a zero-dependency verifier for browsers and Node.
- The Rust crate is a deterministic CBOR encoder, decoder, and verifier for
  AIIR sidecars.

For the public implementation registry, see [implementers.md](implementers.md).

---

## SDK matrix

| Surface | Package | Status | Conformance level | Best fit |
|---|---|---|---|---|
| Python reference | `aiir` | Reference implementation | 3 (Full) | Receipt generation, verification, policy, CI/CD, MCP |
| JavaScript | `@invariantsystems/aiir` | Published SDK | 1 (Verify) | Browser verification, Node services, TypeScript apps |
| Rust | `aiir-cbor-verify` | Published crate | 3 (Full) | Canonical CBOR tooling, sidecar verification, Rust pipelines |

### Conformance levels

| Level | Meaning |
|---|---|
| 1 — Verify | Can verify existing receipts |
| 2 — Generate | Level 1 plus canonical JSON generation |
| 3 — Full | Level 2 plus canonical CBOR round-trip fidelity |

---

## Python reference implementation

The Python package is the canonical source of behavior for AIIR.

Use it when you need to:

- generate commit receipts
- verify receipts and signatures
- evaluate policy and emit Verification Summary Attestations
- run the CLI, MCP server, GitHub Action, or GitLab CI integration

Primary references:

- [README.md](../README.md)
- [docs/api.md](api.md)
- [SPEC.md](../SPEC.md)

Install:

```bash
pip install aiir
```

---

## JavaScript SDK

Package: `@invariantsystems/aiir`

The JavaScript SDK is a zero-dependency verifier for AIIR commit receipts.
It works in modern browsers and in Node.js 18+.

Use it when you need to:

- verify receipts in a browser or frontend app
- verify receipts in Node.js or TypeScript services
- reuse canonical JSON and SHA-256 helpers outside Python

Current public scope:

- `verify(receipt)`
- `canonicalJson(obj)`
- `sha256(str)`
- `constantTimeEqual(a, b)`

Install:

```bash
npm install @invariantsystems/aiir
```

Primary references:

- [sdks/js/README.md](../sdks/js/README.md)
- [sdks/js/aiir-verify.js](../sdks/js/aiir-verify.js)

Conformance notes:

- Intended level: 1 (Verify)
- Verified against encoder interop vectors and full receipt verification cases
- Uses Web Crypto / SubtleCrypto with Node crypto fallback

---

## Rust crate

Crate: `aiir-cbor-verify`

The Rust crate focuses on deterministic CBOR handling for AIIR receipts. It is
for systems that need strict sidecar validation or cross-language CBOR parity
with the Python reference implementation.

Use it when you need to:

- encode canonical CBOR for AIIR receipts
- decode CBOR with strict validation
- verify CBOR sidecars against the JSON receipt hash

Primary references:

- [sdks/rust/README.md](../sdks/rust/README.md)
- [sdks/rust/src/lib.rs](../sdks/rust/src/lib.rs)

Conformance notes:

- Intended level: 3 (Full)
- Validated against `schemas/cbor_test_vectors.json`
- Rejects non-canonical CBOR encodings

---

## Conformance test inputs

Every SDK or third-party implementation should validate against the published
AIIR vectors before claiming compatibility.

- [schemas/test_vectors.json](../schemas/test_vectors.json) — core verification vectors
- [schemas/test-vectors/encoder_interop_vectors.json](../schemas/test-vectors/encoder_interop_vectors.json) — canonical JSON, content-hash, and receipt-ID interop vectors
- [schemas/cbor_test_vectors.json](../schemas/cbor_test_vectors.json) — canonical CBOR vectors
- [schemas/conformance-manifest.json](../schemas/conformance-manifest.json) — machine-readable implementation and vector registry

For the normative rules behind those vectors, see [SPEC.md](../SPEC.md).

---

## Adding another SDK

To publish another AIIR SDK or verifier:

1. Implement the relevant conformance level.
2. Run the matching public vector set.
3. Add your implementation to [implementers.md](implementers.md) with links to the results.
4. Keep security invariants intact: no relaxed hashing rules, no non-canonical JSON, and constant-time hash comparison where secrets or equality checks are involved.

If you are building a verifier rather than a full generator, Level 1 is the
minimum public bar.
