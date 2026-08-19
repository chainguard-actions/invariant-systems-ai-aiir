"""Tests for checked-in public example fixtures.

Copyright 2025-2026 Invariant Systems, Inc.
SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

from aiir._verify import verify_receipt_file
from aiir._verify_release import verify_release


ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_DIR = ROOT / "examples" / "sigstore-bundle"
CONTRADICTION_DIR = ROOT / "examples" / "verify-pass-strict-fail"
RELEASE_BUNDLE_DIR = ROOT / "examples" / "release-bundle-basic"
SCRIPTS_DIR = ROOT / "scripts"


def _load_module(name: str, path: Path):
    """Import a script module by path."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSignedBundleExample(unittest.TestCase):
    """Keep the public signed bundle example live and verifiable."""

    @classmethod
    def setUpClass(cls):
        cls.bundle_mod = _load_module(
            "check_rekor_bundle",
            SCRIPTS_DIR / "check_rekor_bundle.py",
        )

    def test_receipt_example_verifies(self):
        """The checked-in receipt fixture keeps its content-addressed integrity."""
        result = verify_receipt_file(str(EXAMPLE_DIR / "receipt.artifact"))
        self.assertTrue(result["valid"], result)

    def test_tampered_receipt_example_fails(self):
        """The negative example must fail integrity verification."""
        result = verify_receipt_file(str(EXAMPLE_DIR / "receipt.tampered.json"))
        self.assertFalse(result["valid"])
        self.assertIn("content hash mismatch", result.get("errors", []))
        self.assertIn("receipt_id mismatch", result.get("errors", []))

    def test_bundle_example_passes_rekor_linkage(self):
        """The checked-in Sigstore bundle must still match its receipt."""
        errors = self.bundle_mod.validate_bundle(
            EXAMPLE_DIR / "receipt.artifact",
            EXAMPLE_DIR / "receipt.artifact.sigstore",
        )
        self.assertEqual(errors, [])


class TestPublicExampleDocs(unittest.TestCase):
    """Public example docs should stay aligned with the current release surface."""

    def test_witness_quorum_verify_uses_current_release_artifact_name(self):
        from aiir import __version__

        content = (ROOT / "examples" / "witness-quorum" / "VERIFY.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(f"aiir-{__version__}-py3-none-any.whl", content)

    def test_guac_readme_receipt_snippet_uses_current_receipt_fields(self):
        content = (ROOT / "contrib" / "guac" / "README.md").read_text(encoding="utf-8")
        self.assertIn('"tree_sha": "..."', content)
        self.assertIn('"parent_shas": ["..."]', content)
        self.assertIn('"authorship_class": "ai_assisted"', content)
        self.assertIn(
            '"tool": "https://github.com/invariant-systems-ai/aiir@',
            content,
        )
        self.assertNotIn('"tree_hash": "..."', content)
        self.assertNotIn('"generator_version":', content)


class TestVerifyPassStrictFailExample(unittest.TestCase):
    """Keep the minimal policy contradiction example live and accurate."""

    @classmethod
    def setUpClass(cls):
        cls.bundle_mod = _load_module(
            "check_rekor_bundle_contradiction",
            SCRIPTS_DIR / "check_rekor_bundle.py",
        )

    def test_unsigned_fixture_verifies(self):
        result = verify_receipt_file(
            str(CONTRADICTION_DIR / "unsigned" / "receipt.json")
        )
        self.assertTrue(result["valid"], result)

    def test_unsigned_fixture_fails_strict_release_policy(self):
        """Unsigned receipt fails strict policy with BOTH per-receipt and aggregate violations.

        C5.2: verify_release now wires evaluate_ledger_policy, so an unsigned
        receipt under the strict preset triggers *both* require_signing (per-receipt
        gate) AND max_unsigned_receipts (ledger-aggregate gate).  The test asserts
        the full set of violations so that reverting C5.2 (which would drop the
        aggregate enforcement) causes this test to fail — preserving the security
        invariant.
        """
        result = verify_release(
            receipts_path=str(CONTRADICTION_DIR / "unsigned"),
            policy_preset="strict",
        )
        self.assertEqual(result["verificationResult"], "FAILED")
        violation_rules = {
            violation["rule"] for violation in result["policy_violations"]
        }
        self.assertIn("require_signing", violation_rules)
        self.assertIn("max_unsigned_receipts", violation_rules)

    def test_signed_fixture_passes_strict_release_policy(self):
        result = verify_release(
            receipts_path=str(CONTRADICTION_DIR / "signed"),
            policy_preset="strict",
        )
        self.assertEqual(result["verificationResult"], "PASSED")

    def test_signed_fixture_bundle_matches_receipt(self):
        errors = self.bundle_mod.validate_bundle(
            CONTRADICTION_DIR / "signed" / "receipt.json",
            CONTRADICTION_DIR / "signed" / "receipt.json.sigstore",
        )
        self.assertEqual(errors, [])

    def test_readme_uses_directory_local_paths(self):
        readme = (CONTRADICTION_DIR / "README.md").read_text(encoding="utf-8")

        self.assertIn(
            "PYTHONPATH=../.. python3 -m aiir --verify unsigned/receipt.json --explain",
            readme,
        )
        self.assertIn(
            "PYTHONPATH=../.. python3 -m aiir --verify-release --receipts unsigned/ --policy strict",
            readme,
        )
        self.assertIn(
            "PYTHONPATH=../.. python3 -m aiir --verify-release --receipts signed/ --policy strict",
            readme,
        )
        self.assertNotIn(
            "examples/verify-pass-strict-fail/unsigned/receipt.json", readme
        )
        self.assertNotIn("examples/verify-pass-strict-fail/signed/receipt.json", readme)

    def test_signed_and_unsigned_use_identical_receipt_bytes(self):
        unsigned_path = CONTRADICTION_DIR / "unsigned" / "receipt.json"
        signed_path = CONTRADICTION_DIR / "signed" / "receipt.json"

        self.assertEqual(
            unsigned_path.read_text(encoding="utf-8"),
            signed_path.read_text(encoding="utf-8"),
        )

        unsigned = json.loads(unsigned_path.read_text(encoding="utf-8"))
        signed = json.loads(signed_path.read_text(encoding="utf-8"))
        self.assertEqual(unsigned["content_hash"], signed["content_hash"])
        self.assertEqual(unsigned["receipt_id"], signed["receipt_id"])
        self.assertEqual(unsigned["extensions"], {})
        self.assertEqual(signed["extensions"], {})


class TestReleaseBundleExample(unittest.TestCase):
    """The committed release-bundle snapshot must stay internally consistent."""

    def test_manifest_matches_artifact_bytes(self):
        import hashlib

        bundle = RELEASE_BUNDLE_DIR / "bundle"
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], "aiir/release_bundle.v1")
        for entry in manifest["artifacts"]:
            data = (bundle / entry["path"]).read_bytes()
            self.assertEqual(
                hashlib.sha256(data).hexdigest(), entry["sha256"], entry["path"]
            )

    def test_manifest_sha256_matches_manifest(self):
        import hashlib

        bundle = RELEASE_BUNDLE_DIR / "bundle"
        sha_line = (bundle / "manifest.sha256").read_text(encoding="utf-8").split()[0]
        self.assertEqual(
            sha_line,
            hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest(),
        )

    def test_bundled_receipts_reverify_under_policy(self):
        bundle = RELEASE_BUNDLE_DIR / "bundle"
        result = verify_release(
            receipts_path=str(bundle / "receipts"),
            policy_path=str(bundle / "policy.json"),
        )
        self.assertEqual(result["verificationResult"], "PASSED")

    def test_input_ledger_present(self):
        self.assertTrue((RELEASE_BUNDLE_DIR / "receipts.jsonl").is_file())
