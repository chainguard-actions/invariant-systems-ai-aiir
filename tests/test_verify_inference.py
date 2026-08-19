"""Tests for inference receipt verification."""
# Copyright 2025-2026 Invariant Systems, Inc.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import aiir.cli as cli

from aiir._verify_inference import (
    MAX_RECEIPT_FILE_SIZE,
    is_inference_receipt,
    verify_inference_receipt,
    verify_inference_chain,
    verify_inference_receipt_file,
    _compute_inference_hash,
)


def _make_receipt(
    *,
    model_fingerprint="abc123def456",
    sampling_params=None,
    tokens=None,
    granularity="session",
    prev_hash=None,
):
    """Build a valid inference receipt dict with correct hash."""
    if sampling_params is None:
        sampling_params = {"temperature": 0.7, "top_p": 0.9, "seed": 42}
    if tokens is None:
        tokens = [101, 202, 303]

    h = _compute_inference_hash(model_fingerprint, sampling_params, tokens, granularity)
    receipt = {
        "model_fingerprint": model_fingerprint,
        "sampling_params": sampling_params,
        "tokens": tokens,
        "granularity": granularity,
        "hash": h,
    }
    if prev_hash is not None:
        receipt["prev_hash"] = prev_hash
    return receipt


class TestIsInferenceReceipt(unittest.TestCase):
    """is_inference_receipt format detection."""

    def test_valid_inference_receipt(self):
        r = _make_receipt()
        self.assertTrue(is_inference_receipt(r))

    def test_commit_receipt_is_not_inference(self):
        r = {
            "type": "aiir.commit_receipt",
            "model_fingerprint": "x",
            "sampling_params": {},
            "tokens": [],
            "granularity": "session",
        }
        self.assertFalse(is_inference_receipt(r))

    def test_missing_fields(self):
        self.assertFalse(is_inference_receipt({"model_fingerprint": "x"}))
        self.assertFalse(is_inference_receipt({"model_fingerprint": "x", "tokens": []}))
        self.assertFalse(is_inference_receipt({}))

    def test_non_dict(self):
        self.assertFalse(is_inference_receipt("not a dict"))
        self.assertFalse(is_inference_receipt(None))
        self.assertFalse(is_inference_receipt([]))


class TestVerifyInferenceReceipt(unittest.TestCase):
    """Single inference receipt verification."""

    def test_valid_receipt(self):
        r = _make_receipt()
        result = verify_inference_receipt(r)
        self.assertTrue(result["valid"])
        self.assertEqual(result["receipt_type"], "inference_receipt")
        self.assertEqual(result["granularity"], "session")
        self.assertEqual(result["token_count"], 3)
        self.assertEqual(result["errors"], [])

    def test_tampered_hash(self):
        r = _make_receipt()
        r["hash"] = "0" * 64
        result = verify_inference_receipt(r)
        self.assertFalse(result["valid"])
        self.assertTrue(any("mismatch" in e for e in result["errors"]))

    def test_tampered_tokens(self):
        r = _make_receipt()
        r["tokens"].append(999)
        result = verify_inference_receipt(r)
        self.assertFalse(result["valid"])

    def test_receipt_hash_alias(self):
        """'receipt_hash' is accepted as alias for 'hash'."""
        r = _make_receipt()
        r["receipt_hash"] = r.pop("hash")
        result = verify_inference_receipt(r)
        self.assertTrue(result["valid"])

    def test_missing_hash(self):
        r = _make_receipt()
        del r["hash"]
        result = verify_inference_receipt(r)
        self.assertFalse(result["valid"])
        self.assertTrue(any("missing hash" in e for e in result["errors"]))

    def test_invalid_granularity(self):
        r = _make_receipt()
        r["granularity"] = "invalid"
        result = verify_inference_receipt(r)
        self.assertFalse(result["valid"])
        self.assertTrue(any("granularity" in e for e in result["errors"]))

    def test_missing_model_fingerprint(self):
        r = _make_receipt()
        del r["model_fingerprint"]
        result = verify_inference_receipt(r)
        self.assertFalse(result["valid"])

    def test_missing_sampling_params(self):
        r = _make_receipt()
        del r["sampling_params"]
        result = verify_inference_receipt(r)
        self.assertFalse(result["valid"])

    def test_missing_tokens(self):
        r = _make_receipt()
        del r["tokens"]
        result = verify_inference_receipt(r)
        self.assertFalse(result["valid"])

    def test_non_dict_input(self):
        result = verify_inference_receipt("not a dict")
        self.assertFalse(result["valid"])

    def test_all_granularities(self):
        for g in ("session", "forward-pass", "token"):
            r = _make_receipt(granularity=g)
            result = verify_inference_receipt(r)
            self.assertTrue(result["valid"], f"granularity={g} should be valid")

    def test_model_fingerprint_truncated(self):
        """Long fingerprints are truncated in result for display."""
        fp = "a" * 64
        r = _make_receipt(model_fingerprint=fp)
        result = verify_inference_receipt(r)
        self.assertTrue(result["valid"])
        self.assertTrue(result["model_fingerprint"].endswith("..."))


class TestVerifyInferenceChain(unittest.TestCase):
    """Chain of inference receipts."""

    def test_empty_chain(self):
        result = verify_inference_chain([])
        self.assertTrue(result["valid"])
        self.assertEqual(result["total"], 0)

    def test_single_receipt_chain(self):
        r = _make_receipt()
        result = verify_inference_chain([r])
        self.assertTrue(result["valid"])
        self.assertEqual(result["valid_hashes"], 1)

    def test_valid_chain_with_linkage(self):
        r1 = _make_receipt(tokens=[1, 2, 3])
        r1_json = json.dumps(r1, sort_keys=True, separators=(",", ":"))
        r1_hash = hashlib.sha256(r1_json.encode("utf-8")).hexdigest()

        r2 = _make_receipt(tokens=[4, 5, 6], prev_hash=r1_hash)
        result = verify_inference_chain([r1, r2])
        self.assertTrue(result["valid"])
        self.assertEqual(result["valid_hashes"], 2)
        self.assertEqual(result["valid_links"], 1)

    def test_broken_chain_link(self):
        r1 = _make_receipt(tokens=[1, 2, 3])
        r2 = _make_receipt(tokens=[4, 5, 6], prev_hash="0" * 64)
        result = verify_inference_chain([r1, r2])
        self.assertFalse(result["valid"])
        self.assertTrue(any("chain link broken" in e for e in result["errors"]))

    def test_chain_too_long(self):
        from aiir._verify_inference import MAX_CHAIN_LENGTH

        receipts = [_make_receipt()] * (MAX_CHAIN_LENGTH + 1)
        result = verify_inference_chain(receipts)
        self.assertFalse(result["valid"])
        self.assertTrue(any("too long" in e for e in result["errors"]))

    def test_non_dict_entry_does_not_crash(self):
        result = verify_inference_chain([_make_receipt(), None])
        self.assertFalse(result["valid"])
        self.assertTrue(any("receipt is not a dict" in e for e in result["errors"]))

    def test_invalid_prev_hash_type_does_not_crash(self):
        r1 = _make_receipt(tokens=[1, 2, 3])
        r2 = _make_receipt(tokens=[4, 5, 6])
        r2["prev_hash"] = 123
        result = verify_inference_chain([r1, r2])
        self.assertFalse(result["valid"])
        self.assertTrue(any("invalid prev_hash" in e for e in result["errors"]))

    def test_non_canonical_previous_receipt_reports_error(self):
        r1 = _make_receipt(tokens=[1, 2, 3])
        r1["extra"] = object()
        r2 = _make_receipt(tokens=[4, 5, 6], prev_hash="a" * 64)
        result = verify_inference_chain([r1, r2])
        self.assertFalse(result["valid"])
        self.assertTrue(
            any("previous receipt is not canonical JSON" in e for e in result["errors"])
        )


class TestVerifyInferenceReceiptFile(unittest.TestCase):
    """File-level verification."""

    def test_valid_file(self):
        r = _make_receipt()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(r, f)
            f.flush()
            result = verify_inference_receipt_file(f.name)
        os.unlink(f.name)
        self.assertTrue(result["valid"])

    def test_file_not_found(self):
        result = verify_inference_receipt_file("/nonexistent/path.json")
        self.assertFalse(result["valid"])

    def test_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not json")
            f.flush()
            result = verify_inference_receipt_file(f.name)
        os.unlink(f.name)
        self.assertFalse(result["valid"])

    def test_stat_failure(self):
        with (
            patch("aiir._verify_inference.Path.exists", return_value=True),
            patch("aiir._verify_inference.Path.is_symlink", return_value=False),
            patch("aiir._verify_inference.Path.stat", side_effect=OSError("boom")),
        ):
            result = verify_inference_receipt_file("/tmp/inference.json")
        self.assertFalse(result["valid"])
        self.assertTrue(any("cannot stat file" in e for e in result["errors"]))

    def test_file_too_large(self):
        with (
            patch("aiir._verify_inference.Path.exists", return_value=True),
            patch("aiir._verify_inference.Path.is_symlink", return_value=False),
            patch(
                "aiir._verify_inference.Path.stat",
                return_value=SimpleNamespace(st_size=MAX_RECEIPT_FILE_SIZE + 1),
            ),
        ):
            result = verify_inference_receipt_file("/tmp/inference.json")
        self.assertFalse(result["valid"])
        self.assertTrue(any("file too large" in e for e in result["errors"]))

    def test_envelope_format(self):
        """Handles {"receipts": [...]} envelope."""
        r = _make_receipt()
        envelope = {"note": "test chain", "receipts": [r]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(envelope, f)
            f.flush()
            result = verify_inference_receipt_file(f.name)
        os.unlink(f.name)
        self.assertTrue(result["valid"])

    def test_symlink_rejected(self):
        r = _make_receipt()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(r, f)
            f.flush()
            link_path = f.name + ".link"
            os.symlink(f.name, link_path)
            result = verify_inference_receipt_file(link_path)
        os.unlink(f.name)
        os.unlink(link_path)
        self.assertFalse(result["valid"])

    def test_array_file(self):
        """Array of inference receipts verified as chain."""
        r1 = _make_receipt(tokens=[10, 20])
        r2 = _make_receipt(tokens=[30, 40])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([r1, r2], f)
            f.flush()
            result = verify_inference_receipt_file(f.name)
        os.unlink(f.name)
        self.assertTrue(result["valid"])
        self.assertEqual(result["valid_hashes"], 2)

    def test_json_scalar_rejected(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump("not an object", f)
            f.flush()
            result = verify_inference_receipt_file(f.name)
        os.unlink(f.name)
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"], ["expected JSON object or array"])


class TestAutoDetectionInVerifyFile(unittest.TestCase):
    """verify_receipt_file (main) auto-detects inference receipts."""

    def test_auto_detect_single(self):
        from aiir._verify import verify_receipt_file

        r = _make_receipt()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(r, f)
            f.flush()
            result = verify_receipt_file(f.name)
        os.unlink(f.name)
        self.assertTrue(result["valid"])
        self.assertEqual(result.get("receipt_type"), "inference_receipt")

    def test_auto_detect_chain(self):
        from aiir._verify import verify_receipt_file

        r1 = _make_receipt(tokens=[1])
        r2 = _make_receipt(tokens=[2])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([r1, r2], f)
            f.flush()
            result = verify_receipt_file(f.name)
        os.unlink(f.name)
        self.assertTrue(result["valid"])
        self.assertEqual(result["valid_hashes"], 2)

    def test_auto_detect_chain_with_non_dict_entry_returns_invalid(self):
        from aiir._verify import verify_receipt_file

        r1 = _make_receipt(tokens=[1])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([r1, None], f)
            f.flush()
            result = verify_receipt_file(f.name)
        os.unlink(f.name)
        self.assertFalse(result["valid"])
        self.assertTrue(any("receipt is not a dict" in e for e in result["errors"]))


class TestInferenceVerifyCli(unittest.TestCase):
    def _run_verify(self, payload):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(payload, f)
            f.flush()
            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
                rc = cli.main(["--verify", f.name])
        os.unlink(f.name)
        return rc, stdout.getvalue(), stderr.getvalue()

    def test_cli_verify_single_inference_success(self):
        rc, stdout, stderr = self._run_verify(_make_receipt())
        self.assertEqual(rc, 0)
        self.assertIn("Inference receipt verified", stderr)
        self.assertIn('"receipt_type": "inference_receipt"', stdout)

    def test_cli_verify_inference_chain_success(self):
        r1 = _make_receipt(tokens=[1, 2])
        r2 = _make_receipt(tokens=[3, 4])
        rc, stdout, stderr = self._run_verify([r1, r2])
        self.assertEqual(rc, 0)
        self.assertIn("Inference chain verified", stderr)
        self.assertIn('"valid_hashes": 2', stdout)

    def test_cli_verify_single_inference_failure(self):
        receipt = _make_receipt()
        receipt["hash"] = "0" * 64
        rc, _stdout, stderr = self._run_verify(receipt)
        self.assertEqual(rc, 1)
        self.assertIn("Inference receipt verification failed", stderr)

    def test_cli_verify_inference_chain_failure(self):
        rc, _stdout, stderr = self._run_verify([_make_receipt(), None])
        self.assertEqual(rc, 1)
        self.assertIn("Inference chain verification failed", stderr)
        self.assertIn("receipt is not a dict", stderr)


if __name__ == "__main__":
    unittest.main()
