# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""
AIIR internal — inference receipt verification (verify-only).

Recognises and validates the integrity of inference receipts without
including the emitter.  An inference receipt binds model output tokens
to inference parameters via SHA-256 content addressing.

Format recognition:
    An inference receipt is a JSON object with at least:
    - model_fingerprint  (str, hex SHA-256 of model weights/ID)
    - sampling_params    (dict, inference configuration)
    - tokens             (list, output tokens — ints or strings)
    - granularity        (str, one of "session" | "forward-pass" | "token")
    - hash or receipt_hash (str, hex SHA-256)

Verification:
    Recomputes hash = SHA-256(canonical({model_fingerprint, sampling_params,
    tokens, granularity})) and checks it matches the stored hash.

Chain verification:
    When given a list of receipts, checks both hash integrity and prev_hash
    linkage (each receipt's prev_hash should equal SHA-256(prev receipt JSON)).

This module is verify-only: it checks existing receipts but does NOT
generate new ones.  Receipt generation is outside the scope of the
public AIIR CLI.

"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any, Dict, List

from aiir._core import MAX_RECEIPT_FILE_SIZE

# ── Constants ──────────────────────────────────────────────────────────

VALID_GRANULARITIES = frozenset({"session", "forward-pass", "token"})
MAX_CHAIN_LENGTH = 10_000  # DoS guardrail

# ── Format recognition ─────────────────────────────────────────────────


def is_inference_receipt(data: Any) -> bool:
    """Return True if *data* looks like an inference receipt (not a commit receipt)."""
    if not isinstance(data, dict):
        return False
    # Must NOT be a commit receipt
    if data.get("type") == "aiir.commit_receipt":
        return False
    # Must have the 4 core inference receipt fields
    return all(
        k in data
        for k in ("model_fingerprint", "sampling_params", "tokens", "granularity")
    )


# ── Hash computation (verify-only) ────────────────────────────────────


def _canonical_inference_bytes(
    model_fingerprint: str,
    sampling_params: Dict[str, Any],
    tokens: list,
    granularity: str,
) -> bytes:
    """Canonical byte representation for hash verification.

    Uses sorted-key JSON with no whitespace, encoded as UTF-8.
    This matches the reference implementation's canonical form.
    """
    obj = {
        "granularity": granularity,
        "model_fingerprint": model_fingerprint,
        "sampling_params": sampling_params,
        "tokens": tokens,
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _compute_inference_hash(
    model_fingerprint: str,
    sampling_params: Dict[str, Any],
    tokens: list,
    granularity: str,
) -> str:
    """Compute expected hash for an inference receipt."""
    data = _canonical_inference_bytes(
        model_fingerprint, sampling_params, tokens, granularity
    )
    return hashlib.sha256(data).hexdigest()


# ── Single receipt verification ────────────────────────────────────────


def verify_inference_receipt(receipt: Dict[str, Any]) -> Dict[str, Any]:
    """Verify an inference receipt's hash integrity.

    Returns a dict with:
        valid (bool): True if the hash matches the committed fields.
        errors (list[str]): Human-readable error descriptions.
        receipt_type (str): Always "inference_receipt".
        granularity (str): The receipt's granularity level.
        model_fingerprint (str): The model fingerprint (truncated for display).
    """
    result: Dict[str, Any] = {
        "valid": False,
        "errors": [],
        "receipt_type": "inference_receipt",
    }

    # ── Structural validation ──
    if not isinstance(receipt, dict):
        result["errors"].append("receipt is not a dict")
        return result

    model_fp = receipt.get("model_fingerprint")
    if not isinstance(model_fp, str) or not model_fp:
        result["errors"].append("missing or invalid model_fingerprint")
        return result

    sampling = receipt.get("sampling_params")
    if not isinstance(sampling, dict):
        result["errors"].append("missing or invalid sampling_params")
        return result

    tokens = receipt.get("tokens")
    if not isinstance(tokens, list):
        result["errors"].append("missing or invalid tokens")
        return result

    granularity = receipt.get("granularity")
    if granularity not in VALID_GRANULARITIES:
        result["errors"].append(
            f"invalid granularity: {granularity!r} (expected one of {sorted(VALID_GRANULARITIES)})"
        )
        return result

    # Accept both "hash" and "receipt_hash" (the reference impl uses "hash",
    # sample files use "receipt_hash")
    stored_hash = receipt.get("hash") or receipt.get("receipt_hash", "")
    if not isinstance(stored_hash, str) or not stored_hash:
        result["errors"].append(
            "missing hash (expected 'hash' or 'receipt_hash' field)"
        )
        return result

    # ── Hash verification ──
    expected = _compute_inference_hash(model_fp, sampling, tokens, granularity)

    # Constant-time comparison
    hash_ok = hmac.compare_digest(stored_hash.encode("utf-8"), expected.encode("utf-8"))

    result["valid"] = hash_ok
    result["granularity"] = granularity
    result["model_fingerprint"] = (
        model_fp[:16] + "..." if len(model_fp) > 16 else model_fp
    )
    result["token_count"] = len(tokens)

    if not hash_ok:
        result["errors"].append(
            "hash mismatch — receipt content does not match stored hash"
        )

    return result


# ── Chain verification ─────────────────────────────────────────────────


def verify_inference_chain(
    receipts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Verify a chain of inference receipts (hash + linkage).

    Returns:
        valid (bool): True if all hashes match and chain links are intact.
        valid_hashes (int): Count of receipts with valid hashes.
        valid_links (int): Count of valid prev_hash links.
        total (int): Total receipts in the chain.
        errors (list[str]): Human-readable error descriptions.
    """
    if not receipts:
        return {
            "valid": True,
            "valid_hashes": 0,
            "valid_links": 0,
            "total": 0,
            "errors": [],
        }

    if len(receipts) > MAX_CHAIN_LENGTH:
        return {
            "valid": False,
            "valid_hashes": 0,
            "valid_links": 0,
            "total": len(receipts),
            "errors": [
                f"chain too long ({len(receipts)} receipts, max {MAX_CHAIN_LENGTH})"
            ],
        }

    valid_hashes = 0
    valid_links = 0
    all_ok = True
    errors: List[str] = []

    for i, raw in enumerate(receipts):
        r_result = verify_inference_receipt(raw)
        if r_result["valid"]:
            valid_hashes += 1
        else:
            all_ok = False
            errors.append(f"receipt[{i}]: {', '.join(r_result['errors'])}")

        # Chain linkage — check prev_hash against SHA-256 of previous receipt's JSON
        if i > 0 and isinstance(raw, dict):
            prev_hash = raw.get("prev_hash")
            if prev_hash is not None:
                if not isinstance(prev_hash, str) or not prev_hash:
                    all_ok = False
                    errors.append(f"receipt[{i}]: invalid prev_hash")
                    continue
                try:
                    prev_json = json.dumps(
                        receipts[i - 1], sort_keys=True, separators=(",", ":")
                    )
                except (TypeError, ValueError):
                    all_ok = False
                    errors.append(
                        f"receipt[{i}]: previous receipt is not canonical JSON"
                    )
                    continue
                expected_prev = hashlib.sha256(prev_json.encode("utf-8")).hexdigest()
                if hmac.compare_digest(
                    prev_hash.encode("utf-8"), expected_prev.encode("utf-8")
                ):
                    valid_links += 1
                else:
                    all_ok = False
                    errors.append(
                        f"receipt[{i}]: chain link broken (prev_hash mismatch)"
                    )

    return {
        "valid": all_ok,
        "valid_hashes": valid_hashes,
        "valid_links": valid_links,
        "total": len(receipts),
        "errors": errors,
    }


# ── File verification ──────────────────────────────────────────────────


def verify_inference_receipt_file(filepath: str) -> Dict[str, Any]:
    """Load and verify an inference receipt JSON file.

    Handles single receipts, arrays, and the {"receipts": [...]} envelope.
    """
    fpath = Path(filepath)
    if not fpath.exists():
        return {
            "valid": False,
            "errors": [f"File not found: {filepath}"],
            "receipt_type": "inference_receipt",
        }
    if fpath.is_symlink():
        return {
            "valid": False,
            "errors": ["refusing to verify symlink"],
            "receipt_type": "inference_receipt",
        }

    try:
        file_size = fpath.stat().st_size
    except OSError as e:
        return {
            "valid": False,
            "errors": [f"cannot stat file: {e}"],
            "receipt_type": "inference_receipt",
        }

    if file_size > MAX_RECEIPT_FILE_SIZE:
        return {
            "valid": False,
            "errors": [f"file too large ({file_size} bytes)"],
            "receipt_type": "inference_receipt",
        }

    try:
        data = json.loads(fpath.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {
            "valid": False,
            "errors": [f"invalid JSON: {e}"],
            "receipt_type": "inference_receipt",
        }

    # Unwrap envelope: {"receipts": [...]} or {"note": ..., "receipts": [...]}
    if (
        isinstance(data, dict)
        and "receipts" in data
        and isinstance(data["receipts"], list)
    ):
        data = data["receipts"]

    if isinstance(data, dict):
        return verify_inference_receipt(data)
    elif isinstance(data, list):
        return verify_inference_chain(data)
    else:
        return {
            "valid": False,
            "errors": ["expected JSON object or array"],
            "receipt_type": "inference_receipt",
        }
