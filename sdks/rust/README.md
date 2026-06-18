# aiir-cbor-verify

Deterministic CBOR encoder, decoder, and verifier for
[AIIR](https://github.com/invariant-systems-ai/aiir) commit receipts.

## What it does

- **Encodes** AIIR receipts to canonical CBOR (RFC 8949 §4.2 deterministic encoding)
- **Decodes** CBOR with strict validation, rejecting non-canonical forms
- **Verifies** CBOR sidecars by decoding, validating the Layer-0 envelope structure, and checking the round-trip (decode → re-encode → compare bytes). This does not verify commit-receipt content integrity (content_hash/receipt_id); it confirms the CBOR encoding is canonical and self-consistent.

This crate proves cross-language CBOR determinism: the same canonical map produces the same
byte sequence whether encoded by the Python reference implementation or this Rust crate.

## Canonicalization rules

| Rule | Detail |
|------|--------|
| Shortest integer encoding | Integers use the smallest CBOR head (1/2/4/8 bytes) |
| No indefinite-length | All strings, arrays, and maps use definite-length encoding |
| Sorted map keys | Keys sorted bytewise over their encoded CBOR bytes (RFC 8949 §4.2.1 core deterministic encoding) |
| No NaN / Infinity | Non-finite IEEE 754 values rejected at encode time |
| Minimal float precision | Prefers f16, promotes to f32/f64 only when lossless round-trip requires it |

## Usage

```rust
use aiir_cbor_verify::{decode_full, verify_sidecar, CborValue};

// Decode and validate a CBOR sidecar (canonical envelope + round-trip check)
let cbor_bytes: &[u8] = &[/* ... */];

let (valid, errors, sha256_hex) = verify_sidecar(cbor_bytes);
if valid {
    println!("CBOR sidecar is valid (sha256: {})", sha256_hex);
} else {
    println!("CBOR sidecar invalid: {:?}", errors);
}
```

## Conformance

This crate passes the full AIIR conformance test suite:

- **24 CBOR golden vectors**: decode, re-encode, verify round-trip
- **Envelope validation**: Layer-0 structure checks
- **Sidecar verification**: CBOR → JSON → SHA-256 hash match
- **Strictness tests**: rejects non-shortest uint, indefinite-length, unsorted map keys, trailing bytes, NaN/Infinity

Tests load vectors from `schemas/cbor_test_vectors.json` in the AIIR repository.

## License

Apache-2.0 — see [LICENSE](../../LICENSE).
