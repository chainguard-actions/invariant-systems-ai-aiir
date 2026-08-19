# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
ACTION_HEALTH_YML = REPO_ROOT / ".github" / "workflows" / "action-health.yml"
DOGFOOD_YML = REPO_ROOT / ".github" / "workflows" / "dogfood.yml"
PUBLISH_YML = REPO_ROOT / ".github" / "workflows" / "publish.yml"
INSTALL_COSIGN_SH = REPO_ROOT / "scripts" / "install-cosign.sh"
CHECK_REKOR_PY = REPO_ROOT / "scripts" / "check_rekor_bundle.py"


def _load_rekor_module():
    spec = importlib.util.spec_from_file_location("check_rekor_bundle", CHECK_REKOR_PY)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestCosignWorkflowPins(unittest.TestCase):
    def test_install_script_pins_cosign_305(self):
        content = INSTALL_COSIGN_SH.read_text(encoding="utf-8")
        self.assertIn('COSIGN_VERSION="${COSIGN_VERSION:-v3.0.5}"', content)
        self.assertIn("Expected cosign", content)
        self.assertIn(
            "SHA256 mismatch", content, "install script must verify SHA256 checksum"
        )

    def test_publish_workflow_installs_cosign(self):
        content = PUBLISH_YML.read_text(encoding="utf-8")
        self.assertIn("Install cosign verifier", content)
        self.assertIn("bash scripts/install-cosign.sh", content)

    def test_action_health_checks_out_v1_and_uses_checked_out_helpers(self):
        content = ACTION_HEALTH_YML.read_text(encoding="utf-8")
        self.assertIn("path: _action", content)
        self.assertIn("ref: v1", content)
        self.assertIn("bash _action/scripts/install-cosign.sh", content)
        self.assertIn(
            'python3 "$GITHUB_WORKSPACE/_action/scripts/check_rekor_bundle.py"',
            content,
        )

    def test_signed_receipt_workflows_run_rekor_sanity(self):
        for workflow in (ACTION_HEALTH_YML, DOGFOOD_YML):
            content = workflow.read_text(encoding="utf-8")
            self.assertIn("Check Rekor bundle linkage", content)
            self.assertIn("scripts/check_rekor_bundle.py", content)


class TestRekorBundleSanityChecker(unittest.TestCase):
    def setUp(self):
        self.module = _load_rekor_module()

    def _write_bundle(self, *, with_url: bool = False, wrong_digest: bool = False):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        artifact = root / "receipt.json"
        artifact.write_bytes(b'{"ok":true}\n')

        digest = hashlib.sha256(artifact.read_bytes()).digest()
        digest_hex = digest.hex()
        digest_b64 = base64.b64encode(digest).decode("ascii")
        if wrong_digest:
            digest_hex = "0" * 64

        body = {
            "apiVersion": "0.0.1",
            "kind": "hashedrekord",
            "spec": {
                "data": {"hash": {"algorithm": "sha256", "value": digest_hex}},
                "signature": {
                    "content": "fake-signature",
                    "publicKey": {
                        "content": "-----BEGIN PUBLIC KEY-----\nfake\n-----END PUBLIC KEY-----"
                    },
                },
            },
        }
        if with_url:
            body["spec"]["signature"]["publicKey"]["url"] = (
                "https://example.com/key.pem"
            )

        bundle = {
            "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
            "verificationMaterial": {
                "certificate": {"rawBytes": "fake-cert"},
                "tlogEntries": [
                    {
                        "kindVersion": {"kind": "hashedrekord", "version": "0.0.1"},
                        "integratedTime": "1772986853",
                        "inclusionPromise": {"signedEntryTimestamp": "fake-set"},
                        "inclusionProof": {
                            "checkpoint": {"envelope": "rekor.sigstore.dev - fake"}
                        },
                        "canonicalizedBody": base64.b64encode(
                            json.dumps(body, separators=(",", ":")).encode("utf-8")
                        ).decode("ascii"),
                    }
                ],
                "timestampVerificationData": {},
            },
            "messageSignature": {
                "messageDigest": {
                    "algorithm": "SHA2_256",
                    "digest": digest_b64,
                },
                "signature": "fake-signature",
            },
        }

        bundle_path = root / "receipt.json.sigstore"
        bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
        return artifact, bundle_path

    def test_accepts_self_consistent_bundle(self):
        artifact, bundle = self._write_bundle()
        errors = self.module.validate_bundle(artifact, bundle)
        self.assertEqual(errors, [])

    def test_rejects_digest_mismatch(self):
        artifact, bundle = self._write_bundle(wrong_digest=True)
        errors = self.module.validate_bundle(artifact, bundle)
        self.assertTrue(
            any("hash does not match artifact sha256" in err for err in errors)
        )

    def test_rejects_external_public_key_urls(self):
        artifact, bundle = self._write_bundle(with_url=True)
        errors = self.module.validate_bundle(artifact, bundle)
        self.assertTrue(any("external public key URLs" in err for err in errors))


if __name__ == "__main__":
    unittest.main()
