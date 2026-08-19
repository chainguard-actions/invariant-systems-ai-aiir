#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Invariant Systems AI
"""
Atheris-based coverage-guided fuzzing for AIIR security-critical functions.

This harness targets the same entry points as Hypothesis property tests but
uses coverage-guided mutation (libFuzzer via Atheris) to explore code paths
that random generation alone might miss.

Run locally:
    pip install atheris
    python tests/fuzz_atheris.py -max_total_time=60

CI integration:
    The tests/test_fuzz.py (Hypothesis) provides equivalent coverage in CI.
    This file exists for:
      1. OpenSSF Scorecard Fuzzing detection (fuzzedWithPythonAtheris probe)
      2. Deep fuzzing campaigns beyond random generation

Targets:
    - Receipt schema validation (_schema.py)
    - Signature verification (_verify.py)
    - AI detection heuristics (_detect.py)
    - JSON canonicalization (_receipt.py)
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def fuzz_schema_validation(data: bytes) -> None:
    """Fuzz the receipt schema validator with arbitrary JSON-like input."""
    from aiir._schema import validate_receipt_schema

    try:
        payload = json.loads(data)
        if not isinstance(payload, dict):
            return
        validate_receipt_schema(payload)
    except (json.JSONDecodeError, TypeError, ValueError, KeyError):
        pass  # Expected for malformed fuzz input; only crashes are interesting.


def fuzz_verify_receipt(data: bytes) -> None:
    """Fuzz the receipt verifier with arbitrary bytes."""
    from aiir._verify import verify_receipt

    try:
        payload = json.loads(data)
        if not isinstance(payload, dict):
            return
        verify_receipt(payload)
    except (json.JSONDecodeError, TypeError, ValueError, KeyError):
        pass  # Expected for malformed fuzz input; only crashes are interesting.


def fuzz_detect_ai(data: bytes) -> None:
    """Fuzz AI detection with arbitrary commit message bytes."""
    from aiir._detect import detect_ai_signals

    try:
        message = data.decode("utf-8", errors="replace")
        detect_ai_signals(message)
    except (TypeError, ValueError, UnicodeDecodeError):
        pass  # Expected for malformed fuzz input; only crashes are interesting.


def fuzz_canonicalize(data: bytes) -> None:
    """Fuzz JSON canonicalization with arbitrary input."""
    from aiir._core import _canonical_json

    try:
        payload = json.loads(data)
        _canonical_json(payload)
    except (json.JSONDecodeError, TypeError, ValueError, RecursionError):
        pass  # Expected for malformed fuzz input; only crashes are interesting.


def fuzz_verify_agent_receipt(data: bytes) -> None:
    """Fuzz verify_agent_receipt with arbitrary JSON/bytes.

    Security invariant: the function MUST never raise — it must always return
    a dict with valid=False for any malformed input.  Any uncaught exception
    (other than SystemExit from instrumentation) is a genuine finding.
    """
    from aiir._agent_receipt import verify_agent_receipt

    # Try to parse as JSON; if that fails, pass a raw non-dict to exercise the
    # isinstance guard at the top of verify_agent_receipt.
    try:
        payload = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
        # Pass raw bytes decoded as string — exercises the non-dict fast-path.
        try:
            payload = data.decode("utf-8", errors="replace")
        except Exception:
            return

    # The security contract: NEVER raises, ALWAYS returns a dict.
    try:
        result = verify_agent_receipt(payload)  # type: ignore[arg-type]
    except SystemExit:
        return
    # If we reach here, result must be a dict — any other outcome is a crash.
    assert isinstance(result, dict), f"verify_agent_receipt returned {type(result)}"
    assert "valid" in result, "verify_agent_receipt result missing 'valid' key"


def main() -> None:
    """Entry point for Atheris fuzzing."""
    try:
        import atheris  # type: ignore[import-untyped]
    except ImportError:
        print("atheris not installed — install with: pip install atheris")
        sys.exit(0)

    # Register all fuzz targets with coverage instrumentation
    atheris.instrument_all()

    targets = [
        fuzz_schema_validation,
        fuzz_verify_receipt,
        fuzz_detect_ai,
        fuzz_canonicalize,
        fuzz_verify_agent_receipt,
    ]

    # Pick target based on env or default to schema validation
    import os

    target_name = os.environ.get("FUZZ_TARGET", "schema")
    target_map: dict = {
        "schema": fuzz_schema_validation,
        "verify": fuzz_verify_receipt,
        "detect": fuzz_detect_ai,
        "canonicalize": fuzz_canonicalize,
        "agent_receipt": fuzz_verify_agent_receipt,
    }
    target = target_map.get(target_name, targets[0])

    atheris.Setup(sys.argv, target)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
