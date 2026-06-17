"""Test runner for AIIR hardened conformance vectors.

Validates all five hardened vector files against the reference implementation:
  1. adversarial_conformance_vectors.json  — hostile receipt handling
  2. unicode_evasion_vectors.json          — homoglyph/invisible char determinism
  3. canonicalization_trap_vectors.json     — cross-language encoder traps
  4. cross_format_vectors.json             — JSON↔CBOR hash equivalence
  5. negative_encoding_vectors.json        — known misencoding traps

Run:
    python3 -m pytest schemas/test-vectors/test_hardened_vectors.py -v

Copyright 2025-2026 Invariant Systems, Inc.
SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiir._core import _canonical_json, _sha256
from aiir._verify import verify_receipt

SCHEMAS_DIR = Path(__file__).parent.parent
CORE_KEYS = {"type", "schema", "version", "commit", "ai_attestation", "provenance"}


# ── Adversarial conformance vectors ────────────────────────────────


def _load_adversarial():
    data = json.loads(
        (SCHEMAS_DIR / "adversarial_conformance_vectors.json").read_text("utf-8")
    )
    return [(v["id"], v) for v in data["vectors"]]


_ADV = _load_adversarial()


@pytest.mark.parametrize("vid,vector", _ADV, ids=[v for v, _ in _ADV])
def test_adversarial_conformance(vid, vector):
    """Adversarial receipts must be accepted or rejected per the vector spec."""
    result = verify_receipt(vector["receipt"])
    expected_valid = vector["expected"].get(
        "valid", not vector["expected"].get("must_reject", False)
    )
    assert result["valid"] == expected_valid, (
        f"{vid}: expected valid={expected_valid}, "
        f"got valid={result['valid']}, errors={result.get('errors', [])}"
    )
    if not expected_valid and vector["expected"].get("error_pattern"):
        errors_str = " ".join(result.get("errors", []))
        assert vector["expected"]["error_pattern"] in errors_str, (
            f"{vid}: expected error containing "
            f"{vector['expected']['error_pattern']!r}, got {result['errors']}"
        )


# ── Unicode evasion vectors ────────────────────────────────────────


def _load_unicode():
    data = json.loads((SCHEMAS_DIR / "unicode_evasion_vectors.json").read_text("utf-8"))
    return [(v["id"], v) for v in data["vectors"]]


_UNI = _load_unicode()


@pytest.mark.parametrize("vid,vector", _UNI, ids=[v for v, _ in _UNI])
def test_unicode_canonical_json(vid, vector):
    """Canonical JSON must match exactly for Unicode edge cases."""
    core = {k: v for k, v in vector["input_core"].items() if k in CORE_KEYS}
    actual = _canonical_json(core)
    assert (
        actual == vector["expected"]["canonical_json"]
    ), f"{vid}: canonical JSON mismatch"


@pytest.mark.parametrize("vid,vector", _UNI, ids=[v for v, _ in _UNI])
def test_unicode_content_hash(vid, vector):
    """Content hash must match for Unicode edge cases."""
    core = {k: v for k, v in vector["input_core"].items() if k in CORE_KEYS}
    h = _sha256(_canonical_json(core))
    assert (
        f"sha256:{h}" == vector["expected"]["content_hash"]
    ), f"{vid}: content_hash mismatch"


@pytest.mark.parametrize("vid,vector", _UNI, ids=[v for v, _ in _UNI])
def test_unicode_receipt_verifies(vid, vector):
    """Full receipt built from Unicode vector must pass verify_receipt."""
    result = verify_receipt(vector["full_receipt"])
    assert result["valid"], f"{vid}: full receipt failed: {result.get('errors')}"


# ── Canonicalization trap vectors ──────────────────────────────────


def _load_canonicalization():
    data = json.loads(
        (SCHEMAS_DIR / "canonicalization_trap_vectors.json").read_text("utf-8")
    )
    return [(v["id"], v) for v in data["vectors"]]


_CAN = _load_canonicalization()


@pytest.mark.parametrize("vid,vector", _CAN, ids=[v for v, _ in _CAN])
def test_canonicalization_json(vid, vector):
    """Canonical JSON must match for canonicalization edge cases."""
    core = {k: v for k, v in vector["input_core"].items() if k in CORE_KEYS}
    actual = _canonical_json(core)
    assert (
        actual == vector["expected"]["canonical_json"]
    ), f"{vid}: canonical JSON mismatch"


@pytest.mark.parametrize("vid,vector", _CAN, ids=[v for v, _ in _CAN])
def test_canonicalization_hash(vid, vector):
    """Content hash must match for canonicalization edge cases."""
    core = {k: v for k, v in vector["input_core"].items() if k in CORE_KEYS}
    h = _sha256(_canonical_json(core))
    assert (
        f"sha256:{h}" == vector["expected"]["content_hash"]
    ), f"{vid}: content_hash mismatch"


@pytest.mark.parametrize("vid,vector", _CAN, ids=[v for v, _ in _CAN])
def test_canonicalization_receipt_verifies(vid, vector):
    """Full receipt built from canonicalization vector must pass verify_receipt."""
    result = verify_receipt(vector["full_receipt"])
    assert result["valid"], f"{vid}: full receipt failed: {result.get('errors')}"


# ── Cross-format vectors ──────────────────────────────────────────


def _load_cross_format():
    data = json.loads((SCHEMAS_DIR / "cross_format_vectors.json").read_text("utf-8"))
    return [(v["id"], v) for v in data["vectors"]]


_XFMT = _load_cross_format()


@pytest.mark.parametrize("vid,vector", _XFMT, ids=[v for v, _ in _XFMT])
def test_cross_format_receipt_valid(vid, vector):
    """Cross-format receipts must pass verification."""
    result = verify_receipt(vector["receipt"])
    assert result["valid"], f"{vid}: receipt failed: {result.get('errors')}"


@pytest.mark.parametrize("vid,vector", _XFMT, ids=[v for v, _ in _XFMT])
def test_cross_format_hash_matches(vid, vector):
    """Content hash from JSON encoding must match the vector's expected hash."""
    core = {k: v for k, v in vector["receipt"].items() if k in CORE_KEYS}
    h = _sha256(_canonical_json(core))
    assert (
        f"sha256:{h}" == vector["json_content_hash"]
    ), f"{vid}: json_content_hash mismatch"


# ── Negative encoding vectors ─────────────────────────────────────


def _load_negative():
    data = json.loads(
        (SCHEMAS_DIR / "negative_encoding_vectors.json").read_text("utf-8")
    )
    return [(v["id"], v) for v in data["vectors"]]


_NEG = _load_negative()


@pytest.mark.parametrize("vid,vector", _NEG, ids=[v for v, _ in _NEG])
def test_negative_correct_hash_wellformed(vid, vector):
    """The 'correct' hashes in negative vectors must be well-formed."""
    if "correct_content_hash" in vector:
        ch = vector["correct_content_hash"]
        assert ch.startswith("sha256:"), f"{vid}: missing sha256: prefix"
        assert len(ch) == 71, f"{vid}: wrong length {len(ch)}"


@pytest.mark.parametrize("vid,vector", _NEG, ids=[v for v, _ in _NEG])
def test_negative_wrong_hash_differs(vid, vector):
    """Where both correct and wrong hashes exist, they MUST differ."""
    correct = vector.get("correct_content_hash")
    wrong = vector.get("wrong_content_hash")
    if correct and wrong:
        assert correct != wrong, (
            f"{vid}: correct and wrong content_hash are identical — "
            f"the trap is not actually a trap"
        )
    # neg-04 has a special field
    wrong_nfc = vector.get("wrong_content_hash_if_nfc")
    if correct and wrong_nfc:
        assert correct != wrong_nfc, (
            f"{vid}: NFC normalization produced the same hash — " f"trap is ineffective"
        )
