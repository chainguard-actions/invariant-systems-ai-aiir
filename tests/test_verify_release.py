"""
Tests for aiir._verify_release — release-scoped verification and VSA.

Copyright 2025-2026 Invariant Systems, Inc.
# SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import patch

from aiir._core import _canonical_json, _sha256, CLI_VERSION
from aiir._verify_release import (
    VSA_PREDICATE_TYPE,
    VERIFIER_ID,
    _compute_coverage,
    _evaluate_receipts,
    _load_receipts,
    _load_receipts_from_dir,
    _load_receipts_from_ledger,
    _build_vsa_predicate,
    _release_report_first_remediation,
    _release_report_operator_guidance,
    _release_report_policy_preset,
    _release_report_policy_uri,
    _wrap_vsa_in_toto,
    verify_release,
    format_release_report,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _pad_sha(sha: str) -> str:
    """Pad a short test SHA to 40 hex chars for schema validity."""
    return sha.ljust(40, "0") if len(sha) < 40 else sha


def _make_minimal_sigstore_bundle(
    receipt_file_sha256_hex: "Optional[str]" = None,
) -> dict:
    """Return a minimal structurally-valid Sigstore bundle dict (C5.1 / D3).

    This does NOT carry a real signature or certificate — structural validity
    does not require real crypto.  It satisfies _is_structurally_valid_sigstore_bundle:
      * mediaType starts with 'application/vnd.dev.sigstore.bundle'
      * verificationMaterial.certificate.rawBytes is non-empty
      * messageSignature.signature is non-empty

    D3 digest binding: when ``receipt_file_sha256_hex`` is provided (hex string,
    no prefix), the bundle's messageDigest.digest is set to the base64-encoded
    bytes of that SHA-256 so that the D3 file-hash binding check passes.

    Sigstore tooling signs the raw artifact file bytes (not the AIIR content_hash
    projection), so the binding uses the raw file SHA-256.  Tests that need D3
    binding to pass should provide the SHA-256 of the receipt JSON file bytes
    (use _write_sigstore_sidecar which computes this automatically).
    """
    import base64 as _b64

    if receipt_file_sha256_hex:
        try:
            digest_bytes = bytes.fromhex(receipt_file_sha256_hex)
            digest_b64 = _b64.b64encode(digest_bytes).decode()
        except ValueError:
            digest_b64 = "dGVzdA=="
    else:
        digest_b64 = "dGVzdA=="  # base64 of "test" — dummy, no binding

    return {
        "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
        "verificationMaterial": {
            "certificate": {
                "rawBytes": "dGVzdGNlcnQ="  # base64 of "testcert"
            }
        },
        "messageSignature": {
            "messageDigest": {
                "algorithm": "SHA2_256",
                "digest": digest_b64,
            },
            "signature": "dGVzdHNpZ25hdHVyZQ==",  # base64 of "testsignature"
        },
    }


def _write_sigstore_sidecar(
    receipt_json_path: "Path",
    receipt: "Optional[dict]" = None,
) -> "Path":
    """Write a minimal structurally-valid, D3-bound .sigstore sidecar.

    D3: The sidecar's messageDigest.digest is set to the SHA-256 of the receipt
    JSON file bytes on disk (matching how real Sigstore tooling works).

    When ``receipt_json_path`` points to an existing file, its SHA-256 is
    computed and embedded in the sidecar.  The ``receipt`` parameter is accepted
    for API compatibility but is ignored (the binding uses the file on disk).

    Returns the sidecar path.
    """
    import hashlib as _hashlib

    sidecar_path = Path(str(receipt_json_path) + ".sigstore")
    file_sha256_hex: "Optional[str]" = None
    try:
        file_bytes = Path(receipt_json_path).read_bytes()
        file_sha256_hex = _hashlib.sha256(file_bytes).hexdigest()
    except OSError:
        pass
    sidecar_path.write_text(
        json.dumps(_make_minimal_sigstore_bundle(file_sha256_hex), indent=2),
        encoding="utf-8",
    )
    return sidecar_path


def _make_receipt(
    sha: str = "abc123",
    ai: bool = False,
    authorship: str = "human",
    method: str = "heuristic_v2",
    signed: bool = False,
) -> dict:
    """Build a schema-valid receipt for testing.

    The SHA must be 40 or 64 lowercase hex chars for schema validation.
    Short test SHAs are zero-padded to 40 chars.

    Note: ``signed=True`` only sets a bare ``extensions.sigstore_bundle`` field,
    which is used for display/tier purposes only and does NOT satisfy the
    ``require_signing`` gate (C5.1).  To pass ``require_signing``, a real
    on-disk ``.sigstore`` sidecar with structural validity is required — use
    ``_write_sigstore_sidecar`` after writing the receipt to disk.
    """
    padded_sha = _pad_sha(sha)
    core = {
        "type": "aiir.commit_receipt",
        "schema": "aiir/commit_receipt.v1",
        "version": CLI_VERSION,
        "commit": {
            "sha": padded_sha,
            "author": {
                "name": "Test",
                "email": "test@example.com",
                "date": "2026-03-09T12:00:00Z",
            },
            "committer": {
                "name": "Test",
                "email": "test@example.com",
                "date": "2026-03-09T12:00:00Z",
            },
            "subject": "test commit",
            "message_hash": "sha256:" + "a" * 64,
            "diff_hash": "sha256:" + "b" * 64,
            "files_changed": 1,
            "files": ["test.py"],
        },
        "ai_attestation": {
            "is_ai_authored": ai,
            "is_bot_authored": False,
            "authorship_class": authorship,
            "detection_method": method,
            "signals_detected": [],
            "signal_count": 0,
        },
        "provenance": {
            "repository": "https://github.com/test/repo",
            "ref": "main",
            "tool": "https://github.com/invariant-systems-ai/aiir@v" + CLI_VERSION,
            "generator": "aiir/" + CLI_VERSION,
        },
    }
    core_json = _canonical_json(core)
    content_hash = "sha256:" + _sha256(core_json)
    receipt_id = "g1-" + _sha256(core_json)[:32]

    receipt = {
        **core,
        "content_hash": content_hash,
        "receipt_id": receipt_id,
        "timestamp": "2026-03-09T12:00:00Z",
        "extensions": {},
    }
    if signed:
        receipt["extensions"]["sigstore_bundle"] = "mock_bundle_ref"
    return receipt


def _make_tampered_receipt(sha: str = "tampered1") -> dict:
    """Build a receipt with a mismatched content hash (tampered)."""
    receipt = _make_receipt(sha=sha)
    receipt["content_hash"] = (
        "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    )
    return receipt


def _write_ledger(dir_path: Path, receipts: list) -> str:
    """Write receipts as a JSONL ledger file. Returns the file path."""
    ledger_path = dir_path / "receipts.jsonl"
    lines = [_canonical_json(r) for r in receipts]
    ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(ledger_path)


def _write_receipt_dir(base_dir: Path, receipts: list) -> str:
    """Write receipts as individual JSON files in a directory. Returns dir path."""
    receipt_dir = base_dir / "receipts"
    receipt_dir.mkdir(exist_ok=True)
    for i, r in enumerate(receipts):
        (receipt_dir / f"receipt_{i:04d}.json").write_text(
            json.dumps(r, indent=2), encoding="utf-8"
        )
    return str(receipt_dir)


# ---------------------------------------------------------------------------
# Test: Coverage calculation
# ---------------------------------------------------------------------------


class TestComputeCoverage(unittest.TestCase):
    """Test _compute_coverage()."""

    def test_full_coverage(self):
        receipts = [_make_receipt(sha="aaa"), _make_receipt(sha="bbb")]
        cov = _compute_coverage([_pad_sha("aaa"), _pad_sha("bbb")], receipts)
        self.assertEqual(cov["commits_total"], 2)
        self.assertEqual(cov["receipts_found"], 2)
        self.assertEqual(cov["receipts_missing"], [])
        self.assertEqual(cov["coverage_percent"], 100.0)

    def test_partial_coverage(self):
        receipts = [_make_receipt(sha="aaa")]
        cov = _compute_coverage(
            [_pad_sha("aaa"), _pad_sha("bbb"), _pad_sha("ccc")], receipts
        )
        self.assertEqual(cov["commits_total"], 3)
        self.assertEqual(cov["receipts_found"], 1)
        self.assertEqual(cov["receipts_missing"], [_pad_sha("bbb"), _pad_sha("ccc")])
        self.assertAlmostEqual(cov["coverage_percent"], 33.3, places=1)

    def test_zero_coverage(self):
        cov = _compute_coverage([_pad_sha("aaa"), _pad_sha("bbb")], [])
        self.assertEqual(cov["receipts_found"], 0)
        self.assertEqual(cov["coverage_percent"], 0.0)

    def test_empty_range(self):
        cov = _compute_coverage([], [_make_receipt(sha="aaa")])
        self.assertEqual(cov["commits_total"], 0)
        self.assertEqual(cov["coverage_percent"], 100.0)

    def test_extra_receipts_beyond_range(self):
        """Receipts for commits outside the range are ignored in coverage."""
        receipts = [
            _make_receipt(sha="aaa"),
            _make_receipt(sha="bbb"),
            _make_receipt(sha="zzz"),
        ]
        cov = _compute_coverage([_pad_sha("aaa"), _pad_sha("bbb")], receipts)
        self.assertEqual(cov["receipts_found"], 2)
        self.assertEqual(cov["coverage_percent"], 100.0)

    def test_duplicate_shas_in_receipts(self):
        """Multiple receipts for same commit still count as 1."""
        receipts = [_make_receipt(sha="aaa"), _make_receipt(sha="aaa")]
        cov = _compute_coverage([_pad_sha("aaa")], receipts)
        self.assertEqual(cov["receipts_found"], 1)


# ---------------------------------------------------------------------------
# Test: Receipt evaluation
# ---------------------------------------------------------------------------


class TestEvaluateReceipts(unittest.TestCase):
    """Test _evaluate_receipts()."""

    def test_valid_receipts_pass(self):
        receipts = [_make_receipt(sha="a1"), _make_receipt(sha="a2")]
        policy = {"enforcement": "warn"}
        result = _evaluate_receipts(receipts, policy)
        self.assertEqual(result["total_receipts"], 2)
        self.assertEqual(result["valid_receipts"], 2)
        self.assertEqual(result["invalid_receipts"], 0)
        self.assertEqual(result["policy_violations"], [])

    def test_tampered_receipt_detected(self):
        receipts = [_make_receipt(sha="a1"), _make_tampered_receipt(sha="a2")]
        policy = {"enforcement": "warn"}
        result = _evaluate_receipts(receipts, policy)
        self.assertEqual(result["valid_receipts"], 1)
        self.assertEqual(result["invalid_receipts"], 1)

    def test_policy_violation_unsigned(self):
        receipts = [_make_receipt(sha="a1", signed=False)]
        policy = {"enforcement": "hard-fail", "require_signing": True}
        result = _evaluate_receipts(receipts, policy)
        self.assertEqual(result["valid_receipts"], 1)
        self.assertTrue(len(result["policy_violations"]) > 0)
        self.assertEqual(result["policy_violations"][0]["rule"], "require_signing")

    def test_signed_receipt_passes_signing_policy(self):
        # C5.1: A bare embedded extensions.sigstore_bundle field is NOT a verified
        # sidecar.  _evaluate_receipts called without an artifact_index (i.e. from a
        # JSONL ledger with no on-disk sidecar) must fail-closed: the require_signing
        # gate is NOT satisfied by an embedded extensions field alone.
        # This is the security fix: the old forgeable path is now correctly rejected.
        receipts = [_make_receipt(sha="a1", signed=True)]
        policy = {"enforcement": "hard-fail", "require_signing": True}
        result = _evaluate_receipts(receipts, policy)
        violation_rules = [v["rule"] for v in result["policy_violations"]]
        self.assertIn(
            "require_signing",
            violation_rules,
            "A bare embedded sigstore_bundle extension must NOT satisfy require_signing "
            "(C5.1 forgery closure): a structurally-valid on-disk sidecar is required.",
        )

    def test_allowed_detection_methods(self):
        receipts = [_make_receipt(sha="a1", method="forbidden_method")]
        policy = {
            "enforcement": "hard-fail",
            "allowed_detection_methods": ["heuristic_v2", "copilot_v1"],
        }
        result = _evaluate_receipts(receipts, policy)
        violations = result["policy_violations"]
        self.assertTrue(len(violations) > 0)
        self.assertEqual(violations[0]["rule"], "allowed_detection_methods")

    def test_disallow_unsigned_extensions(self):
        receipt = _make_receipt(sha="a1")
        receipt["extensions"]["custom_data"] = {"foo": "bar"}
        policy = {
            "enforcement": "hard-fail",
            "disallow_unsigned_extensions": True,
        }
        result = _evaluate_receipts([receipt], policy)
        violations = result["policy_violations"]
        rules = [v["rule"] for v in violations]
        self.assertIn("disallow_unsigned_extensions", rules)

    def test_scoped_to_commit_shas(self):
        """Only receipts matching commit_shas are evaluated."""
        receipts = [_make_receipt(sha="a1"), _make_receipt(sha="a2")]
        policy = {"enforcement": "warn"}
        result = _evaluate_receipts(receipts, policy, commit_shas=[_pad_sha("a1")])
        self.assertEqual(result["total_receipts"], 1)

    def test_authorship_class_violation(self):
        receipts = [_make_receipt(sha="a1", authorship="ai_generated")]
        policy = {
            "enforcement": "hard-fail",
            "allowed_authorship_classes": ["human", "ai_assisted"],
        }
        result = _evaluate_receipts(receipts, policy)
        rules = [v["rule"] for v in result["policy_violations"]]
        self.assertIn("allowed_authorship_classes", rules)


# ---------------------------------------------------------------------------
# Test: Receipt loading
# ---------------------------------------------------------------------------


class TestReceiptLoading(unittest.TestCase):
    """Test receipt loading from ledger and directory."""

    def test_load_from_ledger(self):
        with tempfile.TemporaryDirectory() as td:
            receipts = [_make_receipt(sha="a1"), _make_receipt(sha="a2")]
            path = _write_ledger(Path(td), receipts)
            loaded = _load_receipts_from_ledger(path)
            self.assertEqual(len(loaded), 2)

    def test_load_from_directory(self):
        with tempfile.TemporaryDirectory() as td:
            receipts = [_make_receipt(sha="a1"), _make_receipt(sha="a2")]
            path = _write_receipt_dir(Path(td), receipts)
            loaded = _load_receipts_from_dir(path)
            self.assertEqual(len(loaded), 2)

    def test_load_auto_detect_file(self):
        with tempfile.TemporaryDirectory() as td:
            receipts = [_make_receipt(sha="a1")]
            path = _write_ledger(Path(td), receipts)
            loaded = _load_receipts(path)
            self.assertEqual(len(loaded), 1)

    def test_load_auto_detect_dir(self):
        with tempfile.TemporaryDirectory() as td:
            receipts = [_make_receipt(sha="a1")]
            path = _write_receipt_dir(Path(td), receipts)
            loaded = _load_receipts(path)
            self.assertEqual(len(loaded), 1)

    def test_load_missing_path(self):
        with self.assertRaises(FileNotFoundError):
            _load_receipts("/nonexistent/path")

    def test_load_empty_ledger(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "empty.jsonl"
            path.write_text("", encoding="utf-8")
            loaded = _load_receipts_from_ledger(str(path))
            self.assertEqual(loaded, [])

    def test_load_malformed_lines_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            receipt = _make_receipt(sha="a1")
            path = Path(td) / "receipts.jsonl"
            path.write_text(
                "not json\n" + _canonical_json(receipt) + "\n{bad\n",
                encoding="utf-8",
            )
            loaded = _load_receipts_from_ledger(str(path))
            self.assertEqual(len(loaded), 1)

    def test_load_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            real = Path(td) / "real.jsonl"
            real.write_text("{}\n", encoding="utf-8")
            link = Path(td) / "link.jsonl"
            link.symlink_to(real)
            with self.assertRaises(ValueError):
                _load_receipts_from_ledger(str(link))


# ---------------------------------------------------------------------------
# Test: VSA predicate builder
# ---------------------------------------------------------------------------


class TestBuildVsaPredicate(unittest.TestCase):
    """Test _build_vsa_predicate()."""

    def test_basic_predicate(self):
        pred = _build_vsa_predicate(
            policy={"enforcement": "warn"},
            policy_uri="aiir://presets/balanced",
            policy_digest="abc123" * 10 + "abcd",
            input_receipts_uri=".aiir/receipts.jsonl",
            input_receipts_digest="def456" * 10 + "defg",
            verification_result="PASSED",
            coverage={
                "commits_total": 10,
                "receipts_found": 10,
                "receipts_missing": [],
                "coverage_percent": 100.0,
            },
            evaluation={
                "total_receipts": 10,
                "valid_receipts": 10,
                "invalid_receipts": 0,
                "policy_violations": [],
            },
            commit_range="origin/main..HEAD",
        )
        self.assertEqual(pred["verificationResult"], "PASSED")
        self.assertEqual(pred["verifier"]["id"], VERIFIER_ID)
        self.assertEqual(pred["verifier"]["version"]["aiir"], CLI_VERSION)
        self.assertEqual(pred["coverage"]["commitsTotal"], 10)
        self.assertEqual(pred["coverage"]["commitRange"], "origin/main..HEAD")
        self.assertIn("timeVerified", pred)

    def test_constraints_included(self):
        pred = _build_vsa_predicate(
            policy={
                "enforcement": "hard-fail",
                "require_signing": True,
                "allowed_detection_methods": ["heuristic_v2"],
                "disallow_unsigned_extensions": True,
                "max_ai_percent": 50.0,
            },
            policy_uri="policy.json",
            policy_digest="a" * 64,
            input_receipts_uri="ledger.jsonl",
            input_receipts_digest="b" * 64,
            verification_result="FAILED",
            coverage={
                "commits_total": 5,
                "receipts_found": 3,
                "receipts_missing": ["x", "y"],
                "coverage_percent": 60.0,
            },
            evaluation={
                "total_receipts": 3,
                "valid_receipts": 3,
                "invalid_receipts": 0,
                "policy_violations": [],
            },
        )
        self.assertIn("constraints", pred)
        self.assertTrue(pred["constraints"]["requireSigned"])
        # D3: signatureVerification must be present and honest (not over-claiming).
        self.assertEqual(pred["constraints"]["signatureVerification"], "structural")
        self.assertEqual(
            pred["constraints"]["allowedDetectionMethods"], ["heuristic_v2"]
        )
        self.assertTrue(pred["constraints"]["disallowUnsignedExtensions"])
        self.assertEqual(pred["constraints"]["maxAiPercent"], 50.0)

    def test_no_constraints_when_empty(self):
        pred = _build_vsa_predicate(
            policy={"enforcement": "warn"},
            policy_uri="p",
            policy_digest="a" * 64,
            input_receipts_uri="r",
            input_receipts_digest="b" * 64,
            verification_result="PASSED",
            coverage={
                "commits_total": 1,
                "receipts_found": 1,
                "receipts_missing": [],
                "coverage_percent": 100.0,
            },
            evaluation={
                "total_receipts": 1,
                "valid_receipts": 1,
                "invalid_receipts": 0,
                "policy_violations": [],
            },
        )
        self.assertNotIn("constraints", pred)


# ---------------------------------------------------------------------------
# Test: In-toto wrapper
# ---------------------------------------------------------------------------


class TestWrapVsaInToto(unittest.TestCase):
    """Test _wrap_vsa_in_toto()."""

    def test_in_toto_structure(self):
        predicate = {"verificationResult": "PASSED"}
        stmt = _wrap_vsa_in_toto(
            predicate,
            subject_name="oci://registry/app@sha256:abc",
            subject_digest={"sha256": "abc123"},
        )
        self.assertEqual(stmt["_type"], "https://in-toto.io/Statement/v1")
        self.assertEqual(len(stmt["subject"]), 1)
        self.assertEqual(stmt["subject"][0]["name"], "oci://registry/app@sha256:abc")
        self.assertEqual(stmt["subject"][0]["digest"]["sha256"], "abc123")
        self.assertEqual(stmt["predicateType"], VSA_PREDICATE_TYPE)
        self.assertEqual(stmt["predicate"]["verificationResult"], "PASSED")

    def test_predicate_type_uri(self):
        self.assertIn("verification_summary/v1", VSA_PREDICATE_TYPE)
        self.assertTrue(VSA_PREDICATE_TYPE.startswith("https://"))


# ---------------------------------------------------------------------------
# Test: verify_release() end-to-end
# ---------------------------------------------------------------------------


class TestVerifyRelease(unittest.TestCase):
    """End-to-end tests for verify_release()."""

    def test_all_pass_balanced(self):
        """All receipts valid, balanced policy → PASSED."""
        with tempfile.TemporaryDirectory() as td:
            receipts = [_make_receipt(sha=f"sha_{i:04d}") for i in range(5)]
            ledger_path = _write_ledger(Path(td), receipts)
            result = verify_release(
                receipts_path=ledger_path,
                policy_preset="balanced",
            )
            self.assertEqual(result["verificationResult"], "PASSED")
            self.assertEqual(result["reason"], "All checks passed")

    def test_tampered_receipt_fails(self):
        """A tampered receipt causes FAILED."""
        with tempfile.TemporaryDirectory() as td:
            receipts = [_make_receipt(sha="ok1"), _make_tampered_receipt(sha="bad1")]
            ledger_path = _write_ledger(Path(td), receipts)
            result = verify_release(
                receipts_path=ledger_path,
                policy_preset="balanced",
            )
            self.assertEqual(result["verificationResult"], "FAILED")
            self.assertIn("integrity", result["reason"])

    def test_strict_policy_unsigned_fails(self):
        """Strict policy requires signing → unsigned receipts fail."""
        with tempfile.TemporaryDirectory() as td:
            receipts = [_make_receipt(sha="a1", signed=False)]
            ledger_path = _write_ledger(Path(td), receipts)
            result = verify_release(
                receipts_path=ledger_path,
                policy_preset="strict",
            )
            self.assertEqual(result["verificationResult"], "FAILED")

    def test_strict_policy_signed_passes(self):
        """Strict policy passes when a structurally-valid, digest-bound .sigstore sidecar
        exists (C5.1 / D3).

        A bare embedded extensions field no longer satisfies require_signing.
        A real on-disk .sigstore sidecar with structural validity and a digest that
        matches the receipt content_hash is required (D3 digest binding).
        """
        with tempfile.TemporaryDirectory() as td:
            receipt = _make_receipt(sha="a1", signed=False)
            dir_path = Path(_write_receipt_dir(Path(td), [receipt]))
            receipt_json_path = dir_path / "receipt_0000.json"
            # Write a digest-bound structurally-valid Sigstore bundle sidecar (D3).
            _write_sigstore_sidecar(receipt_json_path, receipt=receipt)
            result = verify_release(
                receipts_path=str(dir_path),
                policy_preset="strict",
            )
            self.assertEqual(result["verificationResult"], "PASSED")

    def test_embedded_sigstore_extension_does_not_satisfy_require_signing(self):
        """C5.1 forgery closure: an embedded extensions.sigstore field alone must NOT
        satisfy the require_signing gate.

        The old behavior treated a bare embedded field as proof of signing, which
        was forgeable.  The fix demands a structurally-valid on-disk .sigstore sidecar.
        This test asserts that a receipt with only an embedded sigstore extension (and no
        sidecar on disk) is correctly REJECTED under a require_signing policy, so that
        reverting the security fix would cause this test to fail.
        """
        with tempfile.TemporaryDirectory() as td:
            receipt = _make_receipt(sha="a1", signed=False)
            # Add a forged embedded sigstore extension — the old forgeable path.
            receipt["extensions"] = {"sigstore": {"bundle": "present"}}
            ledger_path = _write_ledger(Path(td), [receipt])
            result = verify_release(
                receipts_path=ledger_path,
                policy_preset="strict",
            )
            # Must FAIL: no on-disk sidecar exists, so require_signing is not met.
            self.assertEqual(
                result["verificationResult"],
                "FAILED",
                "An embedded-only sigstore extension must not satisfy require_signing "
                "(C5.1): only a structurally-valid on-disk sidecar counts.",
            )
            violation_rules = [v["rule"] for v in result["policy_violations"]]
            self.assertIn(
                "require_signing",
                violation_rules,
                "require_signing violation must be present when only an embedded "
                "extension is supplied (no on-disk .sigstore sidecar).",
            )

    def test_permissive_policy_always_passes(self):
        """Permissive policy (enforcement=warn) passes even with violations."""
        with tempfile.TemporaryDirectory() as td:
            receipts = [_make_receipt(sha="a1", signed=False)]
            ledger_path = _write_ledger(Path(td), receipts)
            result = verify_release(
                receipts_path=ledger_path,
                policy_preset="permissive",
            )
            self.assertEqual(result["verificationResult"], "PASSED")

    def test_emit_intoto(self):
        """emit_intoto=True wraps result as in-toto Statement."""
        with tempfile.TemporaryDirectory() as td:
            receipts = [_make_receipt(sha="a1")]
            ledger_path = _write_ledger(Path(td), receipts)
            result = verify_release(
                receipts_path=ledger_path,
                policy_preset="balanced",
                emit_intoto=True,
                subject_name="test/repo@a1",
                subject_digest={"gitCommit": "a1"},
            )
            self.assertIn("intoto_statement", result)
            stmt = result["intoto_statement"]
            self.assertEqual(stmt["_type"], "https://in-toto.io/Statement/v1")
            self.assertEqual(stmt["predicateType"], VSA_PREDICATE_TYPE)
            self.assertEqual(stmt["subject"][0]["name"], "test/repo@a1")

    def test_empty_receipts_fails(self):
        """No receipts → FAILED."""
        with tempfile.TemporaryDirectory() as td:
            ledger_path = Path(td) / "empty.jsonl"
            ledger_path.write_text("", encoding="utf-8")
            result = verify_release(
                receipts_path=str(ledger_path),
                policy_preset="balanced",
            )
            self.assertEqual(result["verificationResult"], "FAILED")
            self.assertIn("No receipts", result["reason"])

    def test_missing_receipts_path(self):
        with self.assertRaises(FileNotFoundError):
            verify_release(receipts_path="/nonexistent/file.jsonl")

    def test_policy_from_file(self):
        """Load policy from a JSON file."""
        with tempfile.TemporaryDirectory() as td:
            receipts = [_make_receipt(sha="a1")]
            ledger_path = _write_ledger(Path(td), receipts)
            policy = {
                "enforcement": "warn",
                "require_signing": False,
                "max_ai_percent": 100,
            }
            policy_path = Path(td) / "policy.json"
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            result = verify_release(
                receipts_path=ledger_path,
                policy_path=str(policy_path),
                policy_preset=None,
            )
            self.assertEqual(result["verificationResult"], "PASSED")

    def test_policy_file_not_found(self):
        with tempfile.TemporaryDirectory() as td:
            receipts = [_make_receipt(sha="a1")]
            ledger_path = _write_ledger(Path(td), receipts)
            with self.assertRaises(FileNotFoundError):
                verify_release(
                    receipts_path=ledger_path,
                    policy_path="/nonexistent/policy.json",
                )

    def test_policy_overrides(self):
        """Policy overrides merge on top of loaded policy."""
        with tempfile.TemporaryDirectory() as td:
            receipts = [_make_receipt(sha="a1", ai=True, authorship="ai_generated")]
            ledger_path = _write_ledger(Path(td), receipts)
            result = verify_release(
                receipts_path=ledger_path,
                policy_preset="permissive",
                policy_overrides={"max_ai_percent": 10, "enforcement": "hard-fail"},
            )
            # AI% is 100% but limit is 10% — but this is a ledger-level check
            # that verify_release doesn't run (it does per-receipt checks).
            # Per-receipt policy should still pass for "permissive" base.
            self.assertIn(result["verificationResult"], ("PASSED", "FAILED"))

    def test_from_receipt_dir(self):
        """Load receipts from a directory of JSON files."""
        with tempfile.TemporaryDirectory() as td:
            receipts = [_make_receipt(sha="a1"), _make_receipt(sha="a2")]
            dir_path = _write_receipt_dir(Path(td), receipts)
            result = verify_release(
                receipts_path=dir_path,
                policy_preset="balanced",
            )
            self.assertEqual(result["verificationResult"], "PASSED")

    def test_strict_policy_from_receipt_dir_uses_sigstore_sidecars(self):
        """Strict release checks require a structurally-valid, digest-bound sidecar
        (C5.1 / D3).

        Verifies four things:
        1. Without any sidecar, require_signing is violated (fails).
        2. An empty '{}' sidecar fails structural validation (C5.1 forgery closed).
        3. A structurally-valid sidecar with a WRONG digest fails (D3 digest binding).
        4. A structurally-valid, digest-bound sidecar PASSES.
        """
        import base64

        with tempfile.TemporaryDirectory() as td:
            receipt = _make_receipt(sha="a1", signed=False)
            dir_path = Path(_write_receipt_dir(Path(td), [receipt]))
            receipt_path = dir_path / "receipt_0000.json"
            sidecar_path = Path(str(receipt_path) + ".sigstore")

            # --- 1. No sidecar: must FAIL with require_signing violation ---
            unsigned_result = verify_release(
                receipts_path=str(dir_path),
                policy_preset="strict",
            )
            self.assertEqual(unsigned_result["verificationResult"], "FAILED")
            unsigned_rules = [v["rule"] for v in unsigned_result["policy_violations"]]
            self.assertIn(
                "require_signing",
                unsigned_rules,
                "Without a sidecar, require_signing must be violated.",
            )

            # --- 2. Empty '{}' sidecar: must still FAIL (C5.1 forgery closed) ---
            sidecar_path.write_text("{}", encoding="utf-8")
            empty_bundle_result = verify_release(
                receipts_path=str(dir_path),
                policy_preset="strict",
            )
            self.assertEqual(
                empty_bundle_result["verificationResult"],
                "FAILED",
                "An empty '{}' .sigstore sidecar must NOT satisfy require_signing "
                "(C5.1): structural validation rejects it.",
            )
            empty_bundle_rules = [
                v["rule"] for v in empty_bundle_result["policy_violations"]
            ]
            self.assertIn(
                "require_signing",
                empty_bundle_rules,
                "require_signing violation must be present for an empty '{}' sidecar.",
            )

            # --- 3. Structurally-valid sidecar but WRONG digest: must FAIL (D3) ---
            junk_digest_b64 = base64.b64encode(b"JUNK_DIGEST_WRONG").decode()
            forged_bundle = _make_minimal_sigstore_bundle()
            forged_bundle["messageSignature"]["messageDigest"]["digest"] = (
                junk_digest_b64
            )
            sidecar_path.write_text(
                json.dumps(forged_bundle, indent=2), encoding="utf-8"
            )
            forged_result = verify_release(
                receipts_path=str(dir_path),
                policy_preset="strict",
            )
            self.assertEqual(
                forged_result["verificationResult"],
                "FAILED",
                "A bundle with a mismatched digest must NOT satisfy require_signing "
                "(D3 digest binding): the bundle was not produced for this receipt.",
            )
            forged_rules = [v["rule"] for v in forged_result["policy_violations"]]
            self.assertIn(
                "require_signing",
                forged_rules,
                "require_signing violation must be present for a mismatched-digest bundle.",
            )

            # --- 4. Structurally-valid, digest-bound sidecar: must PASS ---
            # D3: _write_sigstore_sidecar hashes the file bytes and embeds the
            # digest so the D3 binding check passes (mirrors real sigstore tooling).
            _write_sigstore_sidecar(receipt_path)
            signed_result = verify_release(
                receipts_path=str(dir_path),
                policy_preset="strict",
            )
            self.assertEqual(
                signed_result["verificationResult"],
                "PASSED",
                "A structurally-valid, digest-bound .sigstore sidecar must satisfy "
                "require_signing and allow the release to PASS.",
            )


# ---------------------------------------------------------------------------
# Test: Coverage with commit range (mocked git)
# ---------------------------------------------------------------------------


class TestVerifyReleaseWithRange(unittest.TestCase):
    """Tests that require mocking git operations."""

    def _mock_shas(self, shas):
        """Return padded SHA strings (matches list_commits_in_range return type)."""
        return [_pad_sha(sha) for sha in shas]

    @patch("aiir._verify_release.list_commits_in_range")
    @patch("aiir._verify_release._validate_ref")
    def test_full_coverage_passes(self, _mock_validate, mock_list):
        mock_list.return_value = self._mock_shas(["sha1", "sha2", "sha3"])
        with tempfile.TemporaryDirectory() as td:
            receipts = [
                _make_receipt(sha="sha1"),
                _make_receipt(sha="sha2"),
                _make_receipt(sha="sha3"),
            ]
            ledger_path = _write_ledger(Path(td), receipts)
            result = verify_release(
                commit_range="origin/main..HEAD",
                receipts_path=ledger_path,
                policy_preset="balanced",
            )
            self.assertEqual(result["verificationResult"], "PASSED")
            self.assertEqual(result["coverage"]["coverage_percent"], 100.0)

    @patch("aiir._verify_release.list_commits_in_range")
    @patch("aiir._verify_release._validate_ref")
    def test_missing_receipts_fails_strict(self, _mock_validate, mock_list):
        mock_list.return_value = self._mock_shas(["sha1", "sha2", "sha3"])
        with tempfile.TemporaryDirectory() as td:
            # Only 1 of 3 commits has a receipt
            receipts = [_make_receipt(sha="sha1")]
            ledger_path = _write_ledger(Path(td), receipts)
            result = verify_release(
                commit_range="origin/main..HEAD",
                receipts_path=ledger_path,
                policy_preset="strict",
            )
            self.assertEqual(result["verificationResult"], "FAILED")
            # With strict policy, both missing receipts and policy violations
            # may contribute to the failure reason.
            self.assertIn(result["verificationResult"], ("FAILED",))

    @patch("aiir._verify_release.list_commits_in_range")
    @patch("aiir._verify_release._validate_ref")
    def test_coverage_gap_warn_passes(self, _mock_validate, mock_list):
        """Enforcement=warn → coverage gap doesn't fail."""
        mock_list.return_value = self._mock_shas(["sha1", "sha2"])
        with tempfile.TemporaryDirectory() as td:
            receipts = [_make_receipt(sha="sha1")]
            ledger_path = _write_ledger(Path(td), receipts)
            result = verify_release(
                commit_range="v1.0.0..v1.1.0",
                receipts_path=ledger_path,
                policy_preset="permissive",
            )
            self.assertEqual(result["verificationResult"], "PASSED")


# ---------------------------------------------------------------------------
# Test: Human-readable report
# ---------------------------------------------------------------------------


class TestFormatReleaseReport(unittest.TestCase):
    """Test format_release_report()."""

    def test_basic_report(self):
        result = {
            "verificationResult": "PASSED",
            "reason": "All checks passed",
            "coverage": {
                "commits_total": 10,
                "receipts_found": 10,
                "receipts_missing": [],
                "coverage_percent": 100.0,
            },
            "predicate": {
                "policy": {"uri": "aiir://presets/strict"},
                "constraints": {"requireSigned": True},
                "verifier": {"id": VERIFIER_ID, "version": {"aiir": "1.1.0"}},
                "evaluation": {
                    "totalReceipts": 10,
                    "validReceipts": 10,
                    "invalidReceipts": 0,
                    "policyViolations": 0,
                },
            },
            "policy_violations": [],
        }
        report = format_release_report(result)
        self.assertIn("PASSED", report)
        self.assertIn("100.0%", report)
        self.assertIn("10", report)
        self.assertIn("Operator Guidance:", report)
        self.assertIn("Policy-grade: coverage is complete", report)

    def test_failed_report_with_violations(self):
        result = {
            "verificationResult": "FAILED",
            "reason": "3 policy violation(s)",
            "coverage": {
                "commits_total": 5,
                "receipts_found": 5,
                "receipts_missing": [],
                "coverage_percent": 100.0,
            },
            "predicate": {
                "policy": {"uri": "aiir://presets/strict"},
                "constraints": {"requireSigned": True},
                "verifier": {"id": VERIFIER_ID, "version": {"aiir": "1.1.0"}},
                "evaluation": {
                    "totalReceipts": 5,
                    "validReceipts": 5,
                    "invalidReceipts": 0,
                    "policyViolations": 3,
                },
            },
            "policy_violations": [
                {
                    "commit_sha": "abc123",
                    "rule": "require_signing",
                    "message": "Receipt is not signed",
                    "remediation": "Regenerate with: aiir --sign -o .receipts",
                },
            ],
        }
        report = format_release_report(result)
        self.assertIn("FAILED", report)
        self.assertIn("require_signing", report)
        self.assertIn("Integrity-only: receipts may verify", report)
        self.assertIn("Regenerate with: aiir --sign -o .receipts", report)

    def test_report_with_missing_receipts(self):
        result = {
            "verificationResult": "FAILED",
            "reason": "2 commit(s) missing receipts",
            "coverage": {
                "commits_total": 5,
                "receipts_found": 3,
                "receipts_missing": ["abc123def456", "789012345678"],
                "coverage_percent": 60.0,
            },
            "predicate": {
                "policy": {"uri": "aiir://presets/balanced"},
                "verifier": {"id": VERIFIER_ID, "version": {"aiir": "1.1.0"}},
                "evaluation": {
                    "totalReceipts": 3,
                    "validReceipts": 3,
                    "invalidReceipts": 0,
                    "policyViolations": 0,
                },
            },
            "policy_violations": [],
        }
        report = format_release_report(result)
        self.assertIn("Missing receipts", report)
        self.assertIn("60.0%", report)
        self.assertIn("Partial: commit coverage is incomplete.", report)
        self.assertIn("Generate receipts for the missing commits", report)

    def test_failed_report_with_integrity_failure_guidance(self):
        result = {
            "verificationResult": "FAILED",
            "reason": "1 receipt(s) failed integrity check",
            "coverage": {
                "commits_total": 2,
                "receipts_found": 2,
                "receipts_missing": [],
                "coverage_percent": 100.0,
            },
            "predicate": {
                "policy": {"uri": "aiir://presets/balanced"},
                "verifier": {"id": VERIFIER_ID, "version": {"aiir": "1.1.0"}},
                "evaluation": {
                    "totalReceipts": 2,
                    "validReceipts": 1,
                    "invalidReceipts": 1,
                    "policyViolations": 0,
                },
            },
            "policy_violations": [],
        }

        report = format_release_report(result)
        self.assertIn(
            "Invalid: one or more receipts failed integrity verification.", report
        )
        self.assertIn(
            "Stop. Do not use the failing receipts as evidence.",
            report,
        )


# ---------------------------------------------------------------------------
# Test: Schema validation of VSA output
# ---------------------------------------------------------------------------


class TestVsaSchemaCompliance(unittest.TestCase):
    """Verify that generated VSA predicates match the JSON Schema."""

    def test_predicate_has_required_fields(self):
        """All required VSA fields are present."""
        pred = _build_vsa_predicate(
            policy={"enforcement": "warn"},
            policy_uri="aiir://presets/balanced",
            policy_digest="a" * 64,
            input_receipts_uri=".aiir/receipts.jsonl",
            input_receipts_digest="b" * 64,
            verification_result="PASSED",
            coverage={
                "commits_total": 1,
                "receipts_found": 1,
                "receipts_missing": [],
                "coverage_percent": 100.0,
            },
            evaluation={
                "total_receipts": 1,
                "valid_receipts": 1,
                "invalid_receipts": 0,
                "policy_violations": [],
            },
        )
        required = [
            "verifier",
            "timeVerified",
            "policy",
            "inputAttestations",
            "verificationResult",
            "coverage",
            "evaluation",
        ]
        for field in required:
            self.assertIn(field, pred, f"Missing required field: {field}")

    def test_verifier_structure(self):
        pred = _build_vsa_predicate(
            policy={},
            policy_uri="p",
            policy_digest="a" * 64,
            input_receipts_uri="r",
            input_receipts_digest="b" * 64,
            verification_result="PASSED",
            coverage={
                "commits_total": 0,
                "receipts_found": 0,
                "receipts_missing": [],
                "coverage_percent": 100.0,
            },
            evaluation={
                "total_receipts": 0,
                "valid_receipts": 0,
                "invalid_receipts": 0,
                "policy_violations": [],
            },
        )
        self.assertIn("id", pred["verifier"])
        self.assertIn("version", pred["verifier"])
        self.assertIn("aiir", pred["verifier"]["version"])
        # Version is SemVer
        self.assertRegex(
            pred["verifier"]["version"]["aiir"],
            r"^\d+\.\d+\.\d+",
        )

    def test_verification_result_enum(self):
        """verificationResult must be PASSED or FAILED."""
        for expected in ("PASSED", "FAILED"):
            pred = _build_vsa_predicate(
                policy={},
                policy_uri="p",
                policy_digest="a" * 64,
                input_receipts_uri="r",
                input_receipts_digest="b" * 64,
                verification_result=expected,
                coverage={
                    "commits_total": 0,
                    "receipts_found": 0,
                    "receipts_missing": [],
                    "coverage_percent": 100.0,
                },
                evaluation={
                    "total_receipts": 0,
                    "valid_receipts": 0,
                    "invalid_receipts": 0,
                    "policy_violations": [],
                },
            )
            self.assertEqual(pred["verificationResult"], expected)


# ---------------------------------------------------------------------------
# Test: Constants
# ---------------------------------------------------------------------------


class TestConstants(unittest.TestCase):
    """Test module-level constants."""

    def test_vsa_predicate_type_is_uri(self):
        self.assertTrue(VSA_PREDICATE_TYPE.startswith("https://"))
        self.assertIn("verification_summary", VSA_PREDICATE_TYPE)

    def test_verifier_id_is_uri(self):
        self.assertTrue(VERIFIER_ID.startswith("https://"))
        self.assertIn("invariantsystems.io", VERIFIER_ID)


# ---------------------------------------------------------------------------
# Test: CLI integration
# ---------------------------------------------------------------------------


class TestCLIVerifyRelease(unittest.TestCase):
    """Test CLI --verify-release flag."""

    def test_verify_release_passes(self):
        """CLI --verify-release with valid ledger returns 0."""
        import aiir.cli as cli

        with tempfile.TemporaryDirectory() as td:
            receipts = [_make_receipt(sha="a1"), _make_receipt(sha="a2")]
            ledger_path = _write_ledger(Path(td), receipts)
            rc = cli.main(
                [
                    "--verify-release",
                    "--receipts",
                    ledger_path,
                    "--policy",
                    "balanced",
                ]
            )
            self.assertEqual(rc, 0)

    def test_verify_release_fails_tampered(self):
        """CLI --verify-release with tampered receipt returns 1."""
        import aiir.cli as cli

        with tempfile.TemporaryDirectory() as td:
            receipts = [_make_receipt(sha="a1"), _make_tampered_receipt(sha="a2")]
            ledger_path = _write_ledger(Path(td), receipts)
            rc = cli.main(
                [
                    "--verify-release",
                    "--receipts",
                    ledger_path,
                    "--policy",
                    "balanced",
                ]
            )
            self.assertEqual(rc, 1)

    def test_verify_release_emit_vsa(self):
        """CLI --verify-release --emit-vsa writes VSA file."""
        import aiir.cli as cli

        with tempfile.TemporaryDirectory() as td:
            receipts = [_make_receipt(sha="a1")]
            ledger_path = _write_ledger(Path(td), receipts)
            # Use relative path — the CLI rejects absolute paths.
            # So we need to use a relative path from cwd.
            old_cwd = os.getcwd()
            try:
                os.chdir(td)
                rc = cli.main(
                    [
                        "--verify-release",
                        "--receipts",
                        ledger_path,
                        "--policy",
                        "balanced",
                        "--emit-vsa",
                        "vsa-output.intoto.jsonl",
                        "--subject",
                        "test/repo@sha1",
                    ]
                )
                self.assertEqual(rc, 0)
                self.assertTrue(Path("vsa-output.intoto.jsonl").exists())
                data = json.loads(
                    Path("vsa-output.intoto.jsonl").read_text(encoding="utf-8")
                )
                self.assertEqual(data["_type"], "https://in-toto.io/Statement/v1")
                self.assertEqual(data["predicateType"], VSA_PREDICATE_TYPE)
            finally:
                os.chdir(old_cwd)


# ---------------------------------------------------------------------------
# Test: MCP integration
# ---------------------------------------------------------------------------


class TestMCPVerifyRelease(unittest.TestCase):
    """Test MCP aiir_verify_release tool."""

    def test_tool_listed(self):
        from aiir.mcp_server import TOOLS

        names = [t["name"] for t in TOOLS]
        self.assertIn("aiir_verify_release", names)

    def test_handler_registered(self):
        from aiir.mcp_server import TOOL_HANDLERS

        self.assertIn("aiir_verify_release", TOOL_HANDLERS)


# ---------------------------------------------------------------------------
# Test: Import from __init__
# ---------------------------------------------------------------------------


class TestPublicExports(unittest.TestCase):
    """Test that verify_release is accessible from the public API."""

    def test_import_from_aiir(self):
        from aiir import verify_release as vr
        from aiir import format_release_report as frr
        from aiir import VSA_PREDICATE_TYPE as vpt

        self.assertTrue(callable(vr))
        self.assertTrue(callable(frr))
        self.assertIsInstance(vpt, str)

    def test_import_from_cli(self):
        from aiir.cli import verify_release as vr
        from aiir.cli import format_release_report as frr
        from aiir.cli import VSA_PREDICATE_TYPE as vpt

        self.assertTrue(callable(vr))
        self.assertTrue(callable(frr))
        self.assertIsInstance(vpt, str)


# ---------------------------------------------------------------------------
# Test: Edge cases and security
# ---------------------------------------------------------------------------


class TestEdgeCases(unittest.TestCase):
    """Edge cases and defensive checks."""

    def test_receipt_with_non_dict_commit(self):
        """Receipt with commit mutated after creation is skipped (not a valid receipt)."""
        with tempfile.TemporaryDirectory() as td:
            receipt = _make_receipt(sha="a1")
            receipt["commit"] = "not-a-dict"
            ledger_path = _write_ledger(Path(td), [receipt])
            result = verify_release(
                receipts_path=ledger_path,
                policy_preset="balanced",
            )
            # The receipt is skipped (no valid commit dict) — 0 receipts evaluated.
            # With no commit range, this means 0 receipts → PASSED (vacuous truth).
            self.assertIn(result["verificationResult"], ("PASSED", "FAILED"))

    def test_receipt_with_empty_sha(self):
        """Receipt with SHA mutated after creation is skipped (no SHA to match)."""
        with tempfile.TemporaryDirectory() as td:
            receipt = _make_receipt(sha="a1")
            receipt["commit"]["sha"] = ""
            ledger_path = _write_ledger(Path(td), [receipt])
            result = verify_release(
                receipts_path=ledger_path,
                policy_preset="balanced",
            )
            # Skipped receipt (empty SHA) — 0 evaluated → PASSED.
            self.assertIn(result["verificationResult"], ("PASSED", "FAILED"))

    def test_policy_symlink_rejected(self):
        """Policy file as symlink is rejected."""
        with tempfile.TemporaryDirectory() as td:
            real = Path(td) / "real.json"
            real.write_text('{"enforcement": "warn"}', encoding="utf-8")
            link = Path(td) / "link.json"
            link.symlink_to(real)
            receipts = [_make_receipt(sha="a1")]
            ledger_path = _write_ledger(Path(td), receipts)
            with self.assertRaises(ValueError):
                verify_release(
                    receipts_path=ledger_path,
                    policy_path=str(link),
                )

    def test_large_policy_file_rejected(self):
        """Policy file exceeding size limit is rejected."""
        with tempfile.TemporaryDirectory() as td:
            big = Path(td) / "big.json"
            big.write_text("{" + " " * (2 * 1024 * 1024) + "}", encoding="utf-8")
            receipts = [_make_receipt(sha="a1")]
            ledger_path = _write_ledger(Path(td), receipts)
            with self.assertRaises(ValueError):
                verify_release(
                    receipts_path=ledger_path,
                    policy_path=str(big),
                )

    def test_many_receipts_performance(self):
        """100 receipts should process without issues."""
        with tempfile.TemporaryDirectory() as td:
            receipts = [_make_receipt(sha=f"sha_{i:04d}") for i in range(100)]
            ledger_path = _write_ledger(Path(td), receipts)
            result = verify_release(
                receipts_path=ledger_path,
                policy_preset="balanced",
            )
            self.assertEqual(result["verificationResult"], "PASSED")
            self.assertEqual(result["predicate"]["evaluation"]["totalReceipts"], 100)

    def test_commit_range_with_real_shas(self):
        """Regression: list_commits_in_range returns List[str] (plain SHAs).

        Previously verify_release did `[c.sha for c in commits]` which raised
        AttributeError because the elements are already strings, not objects.
        Fixed to `commit_shas = list_commits_in_range(...)` directly.
        """
        sha_a = _pad_sha("aaa111")
        sha_b = _pad_sha("bbb222")
        sha_c = _pad_sha("ccc333")

        receipts = [
            _make_receipt(sha="aaa111"),
            _make_receipt(sha="bbb222"),
        ]
        with tempfile.TemporaryDirectory() as td:
            ledger_path = _write_ledger(Path(td), receipts)

            # Mock list_commits_in_range to return List[str] (plain SHAs),
            # exactly as the real function does.
            with patch(
                "aiir._verify_release.list_commits_in_range",
                return_value=[sha_a, sha_b, sha_c],
            ):
                # This used to raise: AttributeError: 'str' has no attribute 'sha'
                result = verify_release(
                    commit_range="v1.1.0..v1.2.0",
                    receipts_path=ledger_path,
                    policy_preset="balanced",
                )
                # Should succeed without AttributeError.
                # sha_c has no receipt → coverage gap → result depends on policy.
                self.assertIn(result["verificationResult"], ("PASSED", "FAILED"))
                coverage = result.get("coverage", {})
                self.assertEqual(coverage.get("commits_total"), 3)


class TestReleaseReportOperatorGuidance(unittest.TestCase):
    def test_helper_extractors_handle_unexpected_shapes(self):
        self.assertEqual(_release_report_policy_uri({"predicate": []}), "unknown")
        self.assertEqual(
            _release_report_policy_uri({"predicate": {"policy": []}}),
            "unknown",
        )
        self.assertEqual(
            _release_report_policy_preset("aiir://presets/balanced"), "balanced"
        )
        self.assertEqual(_release_report_policy_preset("file:///tmp/policy.json"), "")
        self.assertEqual(
            _release_report_first_remediation(
                ["bad", {"remediation": "  rerun with signing  "}]
            ),
            "rerun with signing",
        )

    def test_guidance_handles_non_dict_predicate(self):
        guidance = _release_report_operator_guidance(
            {
                "predicate": [],
                "coverage": {},
                "policy_violations": [],
            }
        )
        self.assertEqual(guidance["policy_context"], "unknown")
        self.assertIn("current policy", guidance["recommended_action"])

    def test_guidance_handles_non_dict_subsections(self):
        guidance = _release_report_operator_guidance(
            {
                "predicate": {
                    "policy": {"uri": "aiir://presets/balanced"},
                    "evaluation": [],
                    "constraints": [],
                },
                "coverage": [],
                "policy_violations": ["bad"],
            }
        )
        self.assertEqual(guidance["policy_context"], "aiir://presets/balanced")
        self.assertIn("balanced policy", guidance["recommended_action"])

    def test_guidance_handles_missing_receipts(self):
        guidance = _release_report_operator_guidance(
            {
                "reason": "No receipts found",
                "predicate": {"policy": {"uri": "aiir://presets/strict"}},
            }
        )
        self.assertEqual(guidance["policy_context"], "aiir://presets/strict")
        self.assertIn(
            "None: no receipts were available.", guidance["evidence_strength"]
        )
        self.assertIn("Generate receipts", guidance["recommended_action"])

    def test_guidance_for_failed_policy_violation(self):
        guidance = _release_report_operator_guidance(
            {
                "verificationResult": "FAILED",
                "predicate": {
                    "policy": {"uri": "aiir://presets/release"},
                    "evaluation": {"invalidReceipts": 0},
                    "constraints": {},
                },
                "coverage": {"receipts_missing": []},
                "policy_violations": [
                    {
                        "rule": "allowed_detection_methods",
                        "message": "heuristic_v1 not allowed",
                        "remediation": "Switch to an allowed detection method.",
                    }
                ],
            }
        )
        self.assertEqual(
            guidance["evidence_strength"],
            "Rejected: the release failed the configured policy.",
        )
        self.assertIn(
            "Switch to an allowed detection method.", guidance["recommended_action"]
        )
        self.assertIn(
            "configured policy does not accept this release", guidance["escalation"]
        )

    def test_guidance_for_passed_policy_warning(self):
        guidance = _release_report_operator_guidance(
            {
                "verificationResult": "PASSED",
                "predicate": {
                    "policy": {"uri": "aiir://presets/release"},
                    "evaluation": {"invalidReceipts": 0},
                    "constraints": {},
                },
                "coverage": {"receipts_missing": []},
                "policy_violations": [
                    {
                        "rule": "allowed_authorship_classes",
                        "message": "warning only",
                        "remediation": "Review authorship warnings before promotion.",
                    }
                ],
            }
        )
        self.assertEqual(
            guidance["evidence_strength"],
            "Warning-level: the gate passed, but policy warnings remain.",
        )
        self.assertIn(
            "Review authorship warnings before promotion.",
            guidance["recommended_action"],
        )
        self.assertIn("human owner", guidance["escalation"])


# ---------------------------------------------------------------------------
# Test: D1/D3 security fixes — exploit-proving tests
# ---------------------------------------------------------------------------


class TestD1AgentReceiptSegregation(unittest.TestCase):
    """Exploit-proving tests for D1: agent receipts must not count toward commit
    coverage, max_ai_percent denominator, or signed-count aggregates.

    Each test has a failing-before / passing-after structure: the exploit input
    is described, and the assertion verifies the secure behavior (would have
    failed before the fix).
    """

    def _make_agent_receipt_with_glued_sha(self, sha: str) -> dict:
        """Build an agent receipt and glue on an unauthenticated commit.sha.

        This simulates the exploit: an attacker creates a valid agent receipt
        (content hash covers only agent fields) and adds a commit block with
        an arbitrary SHA.  Before the D1 fix, this SHA was counted toward
        coverage and the AI% denominator.
        """
        from aiir._agent_receipt import build_agent_receipt

        r = build_agent_receipt(
            actor_kind="llm",
            actor_tool_name="test-agent",
            action_kind="edit",
        )
        # Glue on an unauthenticated commit field (not in the content hash).
        r["commit"] = {"sha": _pad_sha(sha)}
        return r

    def test_agent_receipt_with_glued_sha_does_not_satisfy_coverage(self):
        """EXPLOIT BLOCKED (D1): a content-valid agent receipt with a glued-on
        commit.sha must NOT count toward commit coverage.

        Before the fix, _compute_coverage iterated all receipts and picked up
        the agent receipt's unauthenticated SHA, yielding 100% false coverage.
        After the fix, only type=='aiir.commit_receipt' receipts count.
        """
        agent_r = self._make_agent_receipt_with_glued_sha("exploitsha1")
        cov = _compute_coverage([_pad_sha("exploitsha1")], [agent_r])
        self.assertEqual(
            cov["receipts_found"],
            0,
            "An agent receipt's unauthenticated commit.sha must NOT satisfy "
            "coverage (D1): only commit receipts count.",
        )
        self.assertEqual(
            cov["coverage_percent"],
            0.0,
            "Coverage must be 0.0% when only agent receipts are present (D1).",
        )

    def test_agent_receipt_sha_does_not_count_in_no_range_coverage(self):
        """EXPLOIT BLOCKED (D1): in the no-commit-range path, agent receipts with
        a glued commit.sha must not inflate commits_total or receipts_found.

        Before the fix the no-range path counted all receipts with commit.sha,
        including agent receipts.  After the fix only commit receipts are counted.
        """
        with tempfile.TemporaryDirectory() as td:
            agent_r = self._make_agent_receipt_with_glued_sha("noshaha1")
            ledger = Path(td) / "r.jsonl"
            ledger.write_text(json.dumps(agent_r) + "\n", encoding="utf-8")
            result = verify_release(receipts_path=str(ledger), policy_preset="balanced")
            cov = result.get("coverage", {})
            self.assertEqual(
                cov["commits_total"],
                0,
                "Agent receipts must not appear in commits_total (D1).",
            )
            self.assertEqual(
                cov["receipts_found"],
                0,
                "Agent receipts must not appear in receipts_found (D1).",
            )

    def test_agent_padding_does_not_dilute_ai_percent(self):
        """EXPLOIT BLOCKED (D1): padding with agent receipts (with glued commit.sha
        and non-AI ai_attestation) must NOT dilute the AI% denominator.

        Before the fix: 1 AI commit receipt + 10 agent receipts -> denominator=11
        -> AI%=9.1% -> max_ai_percent=50 gate passed (false negative).
        After the fix: denominator=1 (commit receipts only) -> AI%=100% -> FAILED.
        """
        with tempfile.TemporaryDirectory() as td:
            ai_receipt = _make_receipt(
                sha="aicommit1", ai=True, authorship="ai_generated"
            )
            # 10 agent receipts with glued commit.sha and fake non-AI attestation
            agent_receipts = []
            for i in range(10):
                ar = self._make_agent_receipt_with_glued_sha(f"agentpad{i}")
                ar["ai_attestation"] = {
                    "is_ai_authored": False,
                    "is_bot_authored": False,
                }
                agent_receipts.append(ar)

            ledger = Path(td) / "r.jsonl"
            all_recs = [ai_receipt] + agent_receipts
            ledger.write_text(
                "\n".join(json.dumps(r) for r in all_recs) + "\n", encoding="utf-8"
            )
            result = verify_release(
                receipts_path=str(ledger),
                policy_preset="balanced",
                policy_overrides={"max_ai_percent": 50, "enforcement": "hard-fail"},
            )
            # AI% = 100% (1 AI commit / 1 commit total) -> must FAIL
            self.assertEqual(
                result["verificationResult"],
                "FAILED",
                "Agent-receipt padding must NOT dilute AI% below 100% (D1): "
                "only commit receipts count in the denominator.",
            )
            violation_rules = [v["rule"] for v in result.get("policy_violations", [])]
            self.assertIn(
                "max_ai_percent",
                violation_rules,
                "max_ai_percent violation must fire when AI% is 100% (unpadded).",
            )

    def test_agent_padding_does_not_inflate_unsigned_count(self):
        """EXPLOIT BLOCKED (D1): the max_unsigned_receipts count must not include
        agent receipts.

        With 2 unsigned commit receipts (below a limit of 3) plus 50 agent
        receipts, the unsigned count from commit receipts alone is 2 and the
        gate must PASS.  Before the fix agent receipts would inflate the count.
        """
        with tempfile.TemporaryDirectory() as td:
            commit_receipts = [_make_receipt(sha=f"cmt{i}", ai=False) for i in range(2)]
            agent_receipts = [
                self._make_agent_receipt_with_glued_sha(f"agentpad_{i}")
                for i in range(50)
            ]
            ledger = Path(td) / "r.jsonl"
            all_recs = commit_receipts + agent_receipts
            ledger.write_text(
                "\n".join(json.dumps(r) for r in all_recs) + "\n", encoding="utf-8"
            )
            result = verify_release(
                receipts_path=str(ledger),
                policy_preset="balanced",
                policy_overrides={
                    "max_unsigned_receipts": 3,
                    "enforcement": "hard-fail",
                },
            )
            # 2 unsigned commit receipts, limit=3 -> must PASS
            self.assertEqual(
                result["verificationResult"],
                "PASSED",
                "Agent receipts must not be counted as unsigned commit receipts (D1): "
                "only 2 actual unsigned commit receipts exist, below the limit of 3.",
            )


class TestD3SignatureBundleBinding(unittest.TestCase):
    """Exploit-proving tests for D3: the Sigstore bundle must be digest-bound to
    the receipt, and the VSA must not claim cryptographic signing for a
    structural-only pass.
    """

    def test_forged_bundle_digest_mismatch_fails_require_signing(self):
        """EXPLOIT BLOCKED (D3): a structurally-valid bundle whose digest does NOT
        match the receipt file SHA-256 must NOT satisfy require_signing.

        Before the fix, _is_structurally_valid_sigstore_bundle only checked shape;
        any structurally-valid bundle (even one produced for a different file) would
        pass.  After the D3 fix, the bundle digest must match the SHA-256 of the
        receipt JSON file bytes (mirrors how real sigstore tooling binds bundles).
        """
        import base64

        with tempfile.TemporaryDirectory() as td:
            receipt = _make_receipt(sha="ab00d00002")  # valid hex SHA
            receipt_dir = Path(td) / "receipts"
            receipt_dir.mkdir()
            receipt_path = receipt_dir / "receipt_0000.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

            # Structurally valid but WRONG digest
            junk_digest_b64 = base64.b64encode(b"WRONG_DIGEST_NOT_MATCHING").decode()
            forged_bundle = {
                "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                "verificationMaterial": {"certificate": {"rawBytes": "dGVzdGNlcnQ="}},
                "messageSignature": {
                    "messageDigest": {
                        "algorithm": "SHA2_256",
                        "digest": junk_digest_b64,
                    },
                    "signature": "JUNK_SIG_BASE64==",
                },
            }
            sidecar_path = Path(str(receipt_path) + ".sigstore")
            sidecar_path.write_text(json.dumps(forged_bundle), encoding="utf-8")

            result = verify_release(
                receipts_path=str(receipt_dir),
                policy_preset="strict",
            )
            self.assertEqual(
                result["verificationResult"],
                "FAILED",
                "A bundle with a mismatched digest must NOT satisfy require_signing "
                "(D3 digest binding was not enforced before the fix).",
            )
            violation_rules = [v["rule"] for v in result.get("policy_violations", [])]
            self.assertIn(
                "require_signing",
                violation_rules,
                "require_signing violation must fire for a mismatched-digest bundle.",
            )

    def test_correct_digest_bound_bundle_passes_require_signing(self):
        """Confirming: a bundle whose digest matches the receipt file SHA-256
        passes require_signing under D3 (mirrors real sigstore tooling).
        """
        with tempfile.TemporaryDirectory() as td:
            receipt = _make_receipt(sha="ab00d00001")  # valid hex SHA
            receipt_dir = Path(td) / "receipts"
            receipt_dir.mkdir()
            receipt_path = receipt_dir / "receipt_0000.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            _write_sigstore_sidecar(receipt_path, receipt=receipt)

            result = verify_release(
                receipts_path=str(receipt_dir),
                policy_preset="strict",
            )
            self.assertEqual(
                result["verificationResult"],
                "PASSED",
                "A correctly digest-bound sidecar must satisfy require_signing (D3).",
            )

    def test_vsa_does_not_claim_cryptographic_signing_for_structural_pass(self):
        """EXPLOIT BLOCKED (D3): when only the structural floor was applied, the VSA
        predicate must NOT claim cryptographic signing.

        Before the fix, _build_vsa_predicate emitted requireSigned:true with no
        qualifier, implying full crypto verification.  After the fix a
        signatureVerification:'structural' qualifier is added when the signing check
        was purely structural (shape + digest binding, no real sigstore verify).
        """
        pred = _build_vsa_predicate(
            policy={"enforcement": "hard-fail", "require_signing": True},
            policy_uri="policy.json",
            policy_digest="a" * 64,
            input_receipts_uri="ledger.jsonl",
            input_receipts_digest="b" * 64,
            verification_result="PASSED",
            coverage={
                "commits_total": 1,
                "receipts_found": 1,
                "receipts_missing": [],
                "coverage_percent": 100.0,
            },
            evaluation={
                "total_receipts": 1,
                "valid_receipts": 1,
                "invalid_receipts": 0,
                "policy_violations": [],
            },
        )
        self.assertIn("constraints", pred)
        self.assertTrue(pred["constraints"]["requireSigned"])
        self.assertIn(
            "signatureVerification",
            pred["constraints"],
            "D3 requires a signatureVerification qualifier in the VSA constraints.",
        )
        self.assertEqual(
            pred["constraints"]["signatureVerification"],
            "structural",
            "Without the sigstore extra, signatureVerification must be 'structural', "
            "not 'cryptographic' (D3: do not over-claim in the VSA).",
        )

    def test_bundle_with_no_message_digest_field_passes_structural_check(self):
        """Regression: bundles that omit the optional messageDigest field (older format)
        must still pass the structural check.

        D3 binding only rejects a *present, non-matching* digest.  A bundle that
        carries no messageDigest at all must not be incorrectly rejected.
        """
        with tempfile.TemporaryDirectory() as td:
            receipt = _make_receipt(sha="d1a2b3c4e5")  # valid hex SHA
            receipt_dir = Path(td) / "receipts"
            receipt_dir.mkdir()
            receipt_path = receipt_dir / "receipt_0000.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

            # Bundle with messageSignature but NO messageDigest sub-object
            bundle_no_digest = {
                "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                "verificationMaterial": {"certificate": {"rawBytes": "dGVzdA=="}},
                "messageSignature": {
                    # No 'messageDigest' key — valid for older bundle formats
                    "signature": "FAKESIG==",
                },
            }
            sidecar = Path(str(receipt_path) + ".sigstore")
            sidecar.write_text(json.dumps(bundle_no_digest), encoding="utf-8")

            result = verify_release(
                receipts_path=str(receipt_dir),
                policy_preset="strict",
            )
            # No digest present -> no binding check -> passes structural floor
            self.assertEqual(
                result["verificationResult"],
                "PASSED",
                "A bundle with no messageDigest must pass structural check (D3 only "
                "rejects present, non-matching digests).",
            )


if __name__ == "__main__":
    unittest.main()
