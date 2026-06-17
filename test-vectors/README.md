# DSSE test vectors

This directory contains DSSE conformance vectors consumed by
`conformance/harness.py` and `.github/workflows/dsse-jcs-conformance.yml`.

## Layout

Each vector should include:

- `<name>.dsse` — DSSE envelope JSON.
- `<name>.json` — source JSON payload expected to canonicalize to the DSSE payload bytes.
- Optional `<name>.bundle` — Sigstore bundle for online/offline verifier parity checks.

## Seed vector

`smoke/basic.*` is a minimal valid vector used to ensure CI wiring remains green and
that canonicalization/parsing logic has at least one concrete fixture.
