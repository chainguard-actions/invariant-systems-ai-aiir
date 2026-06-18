#!/usr/bin/env python3
"""ClusterFuzzLite fuzz target for AIIR's hand-written CBOR decoder.

Feeds random bytes to decode_cbor_full and asserts:
  1. It never raises anything other than ValueError (fail-closed contract).
  2. Any value that is successfully decoded round-trips identically through
     the canonical encoder (_canonical_cbor.encode_cbor).

Any crash, hang, or violation of these invariants is a finding.

Copyright 2025-2026 Invariant Systems, Inc.
SPDX-License-Identifier: Apache-2.0
"""

import sys

import atheris

with atheris.instrument_imports():
    from aiir._canonical_cbor import canonical_cbor_bytes
    from aiir._verify_cbor import decode_cbor_full


def TestOneInput(data: bytes) -> None:
    """Fuzz entry point called by ClusterFuzzLite/libFuzzer."""
    try:
        value = decode_cbor_full(data)
    except ValueError:
        # Expected for invalid/truncated/unsupported CBOR input.
        return
    except Exception as exc:  # noqa: BLE001
        # Any other exception type (OverflowError, RecursionError, etc.) is a
        # finding — the contract is that only ValueError is raised for bad input.
        raise AssertionError(
            f"decode_cbor_full raised unexpected {type(exc).__name__}: {exc}"
        ) from exc

    # Round-trip: re-encode the decoded value and decode again.
    # The re-encoded bytes may differ from the input (e.g. non-canonical input
    # is normalised on encode), but decoding the canonical encoding must produce
    # the same Python value.
    try:
        canonical = canonical_cbor_bytes(value)
    except (ValueError, OverflowError):
        # Encoder rejects values outside its supported range (e.g. integers
        # >= 2**64).  That is acceptable — we only assert round-trip for
        # values that the encoder can represent.
        return

    try:
        round_tripped = decode_cbor_full(canonical)
    except ValueError as exc:
        raise AssertionError(
            f"decode_cbor_full failed on canonical bytes: {exc}"
        ) from exc

    assert round_tripped == value, (
        f"CBOR round-trip mismatch: decoded {value!r}, re-encoded, "
        f"re-decoded as {round_tripped!r}"
    )


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
