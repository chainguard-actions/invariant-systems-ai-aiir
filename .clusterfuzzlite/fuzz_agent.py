#!/usr/bin/env python3
"""ClusterFuzzLite fuzz target for AIIR agent-receipt verification.

Exercises verify_agent_receipt() with arbitrary byte input.  The security
contract is that the function MUST never raise — it must always return a
dict (valid:true or valid:false).  Any crash, hang, or unhandled exception
is a genuine finding.

Copyright 2025-2026 Invariant Systems, Inc.
SPDX-License-Identifier: Apache-2.0
"""

import json
import sys

import atheris

with atheris.instrument_imports():
    from aiir._agent_receipt import (
        AGENT_RECEIPT_CONTRACT_VERSION,
        build_agent_receipt,
        verify_agent_receipt,
    )
    from aiir._core import _canonical_json, _sha256


def TestOneInput(data: bytes) -> None:
    """Fuzz entry point called by ClusterFuzzLite/libFuzzer."""
    # Path 1: arbitrary bytes decoded as loose text (exercises the non-dict fast-path).
    try:
        raw_str = data.decode("utf-8", errors="replace")
    except Exception:
        return

    try:
        result = verify_agent_receipt(raw_str)  # type: ignore[arg-type]
        assert isinstance(result, dict), "verify_agent_receipt must return a dict"
        assert "valid" in result
        assert result["valid"] is False  # non-dict input must always be invalid
    except SystemExit:
        pass

    # Path 2: JSON-parsed input (exercises every field-validation branch).
    try:
        obj = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
        return

    try:
        result2 = verify_agent_receipt(obj)  # type: ignore[arg-type]
    except SystemExit:
        return

    assert isinstance(result2, dict), "verify_agent_receipt must return a dict"
    assert "valid" in result2, "result missing 'valid' key"

    # Path 3: when the JSON object looks like an agent receipt, additionally
    # exercise canonical JSON and SHA-256 helpers on the stored fields.
    if (
        isinstance(obj, dict)
        and obj.get("contract_version") == AGENT_RECEIPT_CONTRACT_VERSION
    ):
        proof = obj.get("proof", {})
        if isinstance(proof, dict):
            stored_hash = proof.get("content_hash", "")
            if isinstance(stored_hash, str) and stored_hash.startswith("sha256:"):
                # Verify canonical JSON is stable for any sub-dict.
                for key in ("actor", "action", "artifacts", "policy"):
                    sub = obj.get(key)
                    if isinstance(sub, dict):
                        try:
                            cj = _canonical_json(sub)
                            assert _canonical_json(
                                json.loads(cj)
                            ) == cj, "canonical JSON not idempotent"
                        except (ValueError, RecursionError):
                            pass


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
