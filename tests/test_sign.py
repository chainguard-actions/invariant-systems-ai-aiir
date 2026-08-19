"""Tests for sigstore signing and verification."""
# Copyright 2025-2026 Invariant Systems, Inc.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Import the module under test
import aiir.cli as cli


class TestSigstoreAvailability(unittest.TestCase):
    """Tests for _sigstore_available() and graceful degradation."""

    def test_sigstore_available_when_installed(self):
        """_sigstore_available() returns True when sigstore is importable."""
        # Use a mock that makes the import succeed
        import types

        fake_sigstore = types.ModuleType("sigstore")
        with patch.dict("sys.modules", {"sigstore": fake_sigstore}):
            self.assertTrue(cli._sigstore_available())

    def test_sigstore_not_available_when_missing(self):
        """_sigstore_available() returns False when sigstore is not installed."""
        with patch.dict("sys.modules", {"sigstore": None}):
            self.assertFalse(cli._sigstore_available())

    def test_sign_receipt_raises_without_sigstore(self):
        """sign_receipt() raises RuntimeError with helpful message when sigstore missing."""
        with patch.dict(
            "sys.modules",
            {
                "sigstore": None,
                "sigstore.models": None,
                "sigstore.oidc": None,
                "sigstore.sign": None,
            },
        ):
            with self.assertRaises(RuntimeError) as ctx:
                cli.sign_receipt(b'{"test": true}')
            self.assertIn("pip install sigstore", str(ctx.exception))

    def test_verify_signature_raises_without_sigstore(self):
        """verify_receipt_signature() raises RuntimeError when sigstore missing."""
        with patch.dict(
            "sys.modules",
            {
                "sigstore": None,
                "sigstore.models": None,
                "sigstore.verify": None,
                "sigstore.verify.policy": None,
            },
        ):
            import tempfile

            # Use real files so we reach the sigstore import check
            with tempfile.NamedTemporaryFile(
                suffix=".json", delete=False, mode="w"
            ) as rf:
                rf.write("{}")
                rpath = rf.name
            bpath = rpath + ".sigstore"
            with open(bpath, "w") as bf:
                bf.write("{}")
            try:
                with self.assertRaises(RuntimeError) as ctx:
                    cli.verify_receipt_signature(rpath, bpath)
                self.assertIn("pip install sigstore", str(ctx.exception))
            finally:
                os.unlink(rpath)
                os.unlink(bpath)


class TestSigstoreSigning(unittest.TestCase):
    """Tests for sign_receipt() and sign_receipt_file() with mocked sigstore."""

    def test_sign_receipt_returns_bundle_json(self):
        """sign_receipt() calls sigstore API and returns bundle JSON."""
        fake_bundle_json = '{"mediaType": "application/vnd.dev.sigstore.bundle.v0.3"}'

        mock_bundle = unittest.mock.MagicMock()
        mock_bundle.to_json.return_value = fake_bundle_json

        mock_signer = unittest.mock.MagicMock()
        mock_signer.__enter__ = unittest.mock.MagicMock(return_value=mock_signer)
        mock_signer.__exit__ = unittest.mock.MagicMock(return_value=False)
        mock_signer.sign_artifact.return_value = mock_bundle

        mock_ctx = unittest.mock.MagicMock()
        mock_ctx.signer.return_value = mock_signer

        mock_identity_token = unittest.mock.MagicMock()

        with patch.dict("sys.modules", {}):  # Clear cache
            with patch("aiir.cli.sign_receipt.__module__", "cli"):
                # Patch at the function level using a wrapper
                from unittest.mock import MagicMock
                import types

                # Create mock modules
                mock_sigstore_sign = types.ModuleType("sigstore.sign")
                mock_sigstore_sign.SigningContext = MagicMock()
                mock_sigstore_sign.SigningContext.from_trust_config.return_value = (
                    mock_ctx
                )

                mock_sigstore_models = types.ModuleType("sigstore.models")
                mock_sigstore_models.ClientTrustConfig = MagicMock()
                mock_sigstore_models.ClientTrustConfig.production.return_value = (
                    MagicMock()
                )

                mock_sigstore_oidc = types.ModuleType("sigstore.oidc")
                mock_sigstore_oidc.detect_credential = MagicMock(
                    return_value="fake-token"
                )
                mock_sigstore_oidc.IdentityToken = MagicMock(
                    return_value=mock_identity_token
                )
                mock_sigstore_oidc.Issuer = MagicMock()

                with patch.dict(
                    "sys.modules",
                    {
                        "sigstore": types.ModuleType("sigstore"),
                        "sigstore.sign": mock_sigstore_sign,
                        "sigstore.models": mock_sigstore_models,
                        "sigstore.oidc": mock_sigstore_oidc,
                    },
                ):
                    result = cli.sign_receipt(b'{"test": true}')
                    self.assertEqual(result, fake_bundle_json)
                    mock_signer.sign_artifact.assert_called_once_with(b'{"test": true}')

    def test_sign_receipt_local_fallback_uses_configured_issuer(self):
        """sign_receipt() uses the interactive Issuer fallback outside CI."""
        fake_bundle_json = '{"mediaType": "application/vnd.dev.sigstore.bundle.v0.3"}'

        mock_bundle = unittest.mock.MagicMock()
        mock_bundle.to_json.return_value = fake_bundle_json

        mock_signer = unittest.mock.MagicMock()
        mock_signer.__enter__ = unittest.mock.MagicMock(return_value=mock_signer)
        mock_signer.__exit__ = unittest.mock.MagicMock(return_value=False)
        mock_signer.sign_artifact.return_value = mock_bundle

        mock_ctx = unittest.mock.MagicMock()
        mock_ctx.signer.return_value = mock_signer

        mock_identity_token = unittest.mock.MagicMock()
        mock_issuer_instance = unittest.mock.MagicMock()
        mock_issuer_instance.identity_token.return_value = mock_identity_token

        with patch.dict("sys.modules", {}):
            with patch("aiir.cli.sign_receipt.__module__", "cli"):
                from unittest.mock import MagicMock
                import types

                mock_sigstore_sign = types.ModuleType("sigstore.sign")
                mock_signing_context_cls = MagicMock()
                mock_signing_context_cls.from_trust_config.return_value = mock_ctx
                setattr(mock_sigstore_sign, "SigningContext", mock_signing_context_cls)

                mock_sigstore_models = types.ModuleType("sigstore.models")
                mock_client_trust_config_cls = MagicMock()
                mock_client_trust_config_cls.production.return_value = MagicMock()
                setattr(
                    mock_sigstore_models,
                    "ClientTrustConfig",
                    mock_client_trust_config_cls,
                )

                mock_sigstore_oidc = types.ModuleType("sigstore.oidc")
                setattr(
                    mock_sigstore_oidc,
                    "detect_credential",
                    MagicMock(return_value=None),
                )
                setattr(mock_sigstore_oidc, "IdentityToken", MagicMock())
                mock_issuer_cls = MagicMock(return_value=mock_issuer_instance)
                setattr(mock_sigstore_oidc, "Issuer", mock_issuer_cls)

                with patch.dict(
                    "sys.modules",
                    {
                        "sigstore": types.ModuleType("sigstore"),
                        "sigstore.sign": mock_sigstore_sign,
                        "sigstore.models": mock_sigstore_models,
                        "sigstore.oidc": mock_sigstore_oidc,
                    },
                ):
                    with patch.dict("os.environ", {}, clear=True):
                        result = cli.sign_receipt(b'{"test": true}')

                self.assertEqual(result, fake_bundle_json)
                mock_issuer_cls.assert_called_once_with(
                    "https://oauth2.sigstore.dev/auth"
                )
                mock_issuer_instance.identity_token.assert_called_once_with(
                    force_oob=False
                )
                mock_signer.sign_artifact.assert_called_once_with(b'{"test": true}')

    def test_sign_receipt_local_fallback_can_force_oob(self):
        """sign_receipt() honors SIGSTORE_OAUTH_FORCE_OOB for local fallback."""
        fake_bundle_json = '{"mediaType": "application/vnd.dev.sigstore.bundle.v0.3"}'

        mock_bundle = unittest.mock.MagicMock()
        mock_bundle.to_json.return_value = fake_bundle_json

        mock_signer = unittest.mock.MagicMock()
        mock_signer.__enter__ = unittest.mock.MagicMock(return_value=mock_signer)
        mock_signer.__exit__ = unittest.mock.MagicMock(return_value=False)
        mock_signer.sign_artifact.return_value = mock_bundle

        mock_ctx = unittest.mock.MagicMock()
        mock_ctx.signer.return_value = mock_signer

        mock_identity_token = unittest.mock.MagicMock()
        mock_issuer_instance = unittest.mock.MagicMock()
        mock_issuer_instance.identity_token.return_value = mock_identity_token

        with patch.dict("sys.modules", {}):
            with patch("aiir.cli.sign_receipt.__module__", "cli"):
                from unittest.mock import MagicMock
                import types

                mock_sigstore_sign = types.ModuleType("sigstore.sign")
                mock_signing_context_cls = MagicMock()
                mock_signing_context_cls.from_trust_config.return_value = mock_ctx
                setattr(mock_sigstore_sign, "SigningContext", mock_signing_context_cls)

                mock_sigstore_models = types.ModuleType("sigstore.models")
                mock_client_trust_config_cls = MagicMock()
                mock_client_trust_config_cls.production.return_value = MagicMock()
                setattr(
                    mock_sigstore_models,
                    "ClientTrustConfig",
                    mock_client_trust_config_cls,
                )

                mock_sigstore_oidc = types.ModuleType("sigstore.oidc")
                setattr(
                    mock_sigstore_oidc,
                    "detect_credential",
                    MagicMock(return_value=None),
                )
                setattr(mock_sigstore_oidc, "IdentityToken", MagicMock())
                mock_issuer_cls = MagicMock(return_value=mock_issuer_instance)
                setattr(mock_sigstore_oidc, "Issuer", mock_issuer_cls)

                with patch.dict(
                    "sys.modules",
                    {
                        "sigstore": types.ModuleType("sigstore"),
                        "sigstore.sign": mock_sigstore_sign,
                        "sigstore.models": mock_sigstore_models,
                        "sigstore.oidc": mock_sigstore_oidc,
                    },
                ):
                    with patch.dict(
                        "os.environ",
                        {"SIGSTORE_OAUTH_FORCE_OOB": "true"},
                        clear=True,
                    ):
                        result = cli.sign_receipt(b'{"test": true}')

                self.assertEqual(result, fake_bundle_json)
                mock_issuer_cls.assert_called_once_with(
                    "https://oauth2.sigstore.dev/auth"
                )
                mock_issuer_instance.identity_token.assert_called_once_with(
                    force_oob=True
                )
                mock_signer.sign_artifact.assert_called_once_with(b'{"test": true}')

    def test_sign_receipt_file_writes_bundle(self):
        """sign_receipt_file() writes .sigstore bundle next to receipt."""
        fake_bundle = '{"mediaType": "test-bundle"}'

        with tempfile.TemporaryDirectory() as tmpdir:
            receipt_path = os.path.join(tmpdir, "receipt_test.json")
            Path(receipt_path).write_text('{"type": "test"}', encoding="utf-8")

            with patch("aiir._sign.sign_receipt", return_value=fake_bundle):
                bundle_path = cli.sign_receipt_file(receipt_path)

            self.assertEqual(bundle_path, receipt_path + ".sigstore")
            self.assertTrue(Path(bundle_path).exists())
            self.assertEqual(
                Path(bundle_path).read_text(encoding="utf-8"),
                fake_bundle,
            )

    def test_sign_receipt_file_not_found(self):
        """sign_receipt_file() raises FileNotFoundError for missing files."""
        with self.assertRaises(FileNotFoundError):
            cli.sign_receipt_file("/tmp/nonexistent_receipt_xyz.json")

    def test_sign_receipt_file_stat_error_after_lstat(self):
        """sign_receipt_file() reports size stat failures after lstat succeeds."""
        fake_path = unittest.mock.MagicMock()
        fake_path.lstat.return_value = object()
        fake_path.is_symlink.return_value = False
        fake_path.stat.side_effect = OSError("perm denied")

        with patch("aiir._sign.Path", return_value=fake_path):
            with self.assertRaises(ValueError) as ctx:
                cli.sign_receipt_file("receipt.json")

        fake_path.lstat.assert_called_once_with()
        fake_path.stat.assert_called_once_with()
        self.assertIn("Cannot stat receipt file", str(ctx.exception))
        self.assertIn("perm denied", str(ctx.exception))

    def test_sign_receipt_file_rejects_existing_bundle(self):
        """sign_receipt_file() raises FileExistsError if .sigstore already exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            receipt_path = os.path.join(tmpdir, "receipt.json")
            Path(receipt_path).write_text('{"type": "test"}', encoding="utf-8")
            # Pre-create the bundle file
            bundle_path = receipt_path + ".sigstore"
            Path(bundle_path).write_text('{"old": true}', encoding="utf-8")

            with self.assertRaises(FileExistsError) as ctx:
                cli.sign_receipt_file(receipt_path)
            self.assertIn("already exists", str(ctx.exception))


class TestSigstoreBundleHelpers(unittest.TestCase):
    """Tests for bundle summary and structural validation helpers."""

    @staticmethod
    def _valid_bundle(artifact_bytes: bytes) -> dict:
        artifact_sha256 = hashlib.sha256(artifact_bytes).digest()
        artifact_sha256_hex = artifact_sha256.hex()
        artifact_sha256_b64 = base64.b64encode(artifact_sha256).decode("ascii")
        rekor_body = {
            "spec": {
                "data": {
                    "hash": {
                        "algorithm": "sha256",
                        "value": artifact_sha256_hex,
                    }
                },
                "signature": {
                    "content": "bundle-signature",
                    "publicKey": {"content": "public-key"},
                },
            }
        }
        return {
            "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
            "messageSignature": {
                "messageDigest": {
                    "algorithm": "SHA2_256",
                    "digest": artifact_sha256_b64,
                },
                "signature": "bundle-signature",
            },
            "verificationMaterial": {
                "certificate": {
                    "rawBytes": base64.b64encode(b"fake-certificate").decode("ascii")
                },
                "tlogEntries": [
                    {
                        "kindVersion": {"kind": "hashedrekord"},
                        "logIndex": "123",
                        "logId": {"keyId": "rekor-key"},
                        "integratedTime": "1711962200",
                        "inclusionPromise": {
                            "signedEntryTimestamp": "signed-entry-timestamp"
                        },
                        "inclusionProof": {
                            "checkpoint": {"envelope": "rekor.sigstore.dev - 1"}
                        },
                        "canonicalizedBody": base64.b64encode(
                            json.dumps(rekor_body).encode("utf-8")
                        ).decode("ascii"),
                    }
                ],
                "timestampVerificationData": {
                    "rfc3161Timestamps": [{"signedTimestamp": "ts"}]
                },
            },
        }

    def test_summarize_sigstore_bundle_includes_metadata(self):
        from aiir._sign import summarize_sigstore_bundle

        bundle = self._valid_bundle(b'{"type":"test"}')

        summary = summarize_sigstore_bundle(bundle)

        self.assertEqual(
            summary["media_type"], "application/vnd.dev.sigstore.bundle.v0.3+json"
        )
        self.assertTrue(summary["certificate_present"])
        self.assertEqual(summary["tlog_entry_count"], 1)
        self.assertEqual(summary["message_digest_algorithm"], "SHA2_256")
        self.assertEqual(summary["rfc3161_timestamp_count"], 1)
        self.assertEqual(summary["entries"][0]["kind"], "hashedrekord")
        self.assertEqual(summary["entries"][0]["log_index"], "123")
        self.assertEqual(
            summary["entries"][0]["integrated_time_rfc3339"],
            "2024-04-01T09:03:20Z",
        )
        self.assertTrue(summary["entries"][0]["has_signed_entry_timestamp"])
        self.assertTrue(summary["entries"][0]["has_checkpoint"])
        self.assertTrue(summary["certificate_sha256"].startswith("sha256:"))

    def test_summarize_sigstore_bundle_handles_invalid_optional_fields(self):
        from aiir._sign import summarize_sigstore_bundle

        bundle = {
            "messageSignature": {},
            "verificationMaterial": {
                "certificate": {"rawBytes": "%%%not-base64%%%"},
                "tlogEntries": [
                    "skip-me",
                    {"integratedTime": "not-a-number"},
                    {"integratedTime": str(10**100)},
                ],
                "timestampVerificationData": {"rfc3161Timestamps": "not-a-list"},
            },
        }

        summary = summarize_sigstore_bundle(bundle)

        self.assertNotIn("certificate_sha256", summary)
        self.assertEqual(summary["tlog_entry_count"], 2)
        self.assertIsNone(summary["entries"][0]["integrated_time_rfc3339"])
        self.assertIsNone(summary["entries"][1]["integrated_time_rfc3339"])
        self.assertEqual(summary["rfc3161_timestamp_count"], 0)

    def test_validate_sigstore_bundle_accepts_matching_hashedrekord(self):
        from aiir._sign import validate_sigstore_bundle

        artifact_bytes = b'{"type":"test"}'

        errors = validate_sigstore_bundle(
            artifact_bytes, self._valid_bundle(artifact_bytes)
        )

        self.assertEqual(errors, [])

    def test_validate_sigstore_bundle_reports_structural_errors(self):
        from aiir._sign import validate_sigstore_bundle

        artifact_bytes = b'{"type":"test"}'
        artifact_sha256_hex = hashlib.sha256(artifact_bytes).hexdigest()
        malformed_entry_body = {
            "spec": {
                "data": {
                    "hash": {
                        "algorithm": "sha1",
                        "value": "0" * 64,
                    }
                },
                "signature": {
                    "content": "different-signature",
                    "publicKey": {
                        "url": "https://example.com/key.pem",
                        "content": "",
                    },
                },
            }
        }
        missing_public_key_body = {
            "spec": {
                "data": {
                    "hash": {
                        "algorithm": "sha256",
                        "value": artifact_sha256_hex,
                    }
                },
                "signature": {"content": "bundle-signature"},
            }
        }
        bundle = {
            "mediaType": "bad-media-type",
            "messageSignature": {
                "messageDigest": {
                    "algorithm": "SHA1",
                    "digest": "bad-digest",
                },
                "signature": "",
            },
            "verificationMaterial": {
                "tlogEntries": [
                    "not-an-object",
                    {
                        "kindVersion": {"kind": "rekord"},
                        "integratedTime": "not-a-number",
                        "inclusionPromise": {},
                        "inclusionProof": {"checkpoint": {"envelope": "missing"}},
                    },
                    {
                        "kindVersion": {"kind": "hashedrekord"},
                        "integratedTime": "1711962200",
                        "inclusionPromise": {
                            "signedEntryTimestamp": "signed-entry-timestamp"
                        },
                        "inclusionProof": {
                            "checkpoint": {"envelope": "rekor.sigstore.dev - 1"}
                        },
                        "canonicalizedBody": "@@@not-base64@@@",
                    },
                    {
                        "kindVersion": {"kind": "hashedrekord"},
                        "integratedTime": "1711962200",
                        "inclusionPromise": {
                            "signedEntryTimestamp": "signed-entry-timestamp"
                        },
                        "inclusionProof": {
                            "checkpoint": {"envelope": "rekor.sigstore.dev - 1"}
                        },
                        "canonicalizedBody": base64.b64encode(
                            json.dumps(malformed_entry_body).encode("utf-8")
                        ).decode("ascii"),
                    },
                    {
                        "kindVersion": {"kind": "hashedrekord"},
                        "integratedTime": "1711962200",
                        "inclusionPromise": {
                            "signedEntryTimestamp": "signed-entry-timestamp"
                        },
                        "inclusionProof": {
                            "checkpoint": {"envelope": "rekor.sigstore.dev - 1"}
                        },
                        "canonicalizedBody": base64.b64encode(
                            json.dumps(missing_public_key_body).encode("utf-8")
                        ).decode("ascii"),
                    },
                ]
            },
        }

        errors = validate_sigstore_bundle(artifact_bytes, bundle)

        self.assertIn("unexpected mediaType: 'bad-media-type'", errors)
        self.assertIn("unexpected messageDigest.algorithm: 'SHA1'", errors)
        self.assertIn("messageDigest.digest does not match artifact sha256", errors)
        self.assertIn("missing messageSignature.signature", errors)
        self.assertIn("tlog entry 1 is not an object", errors)
        self.assertIn("tlog entry 2 has unexpected kind: 'rekord'", errors)
        self.assertIn("tlog entry 2 has invalid integratedTime", errors)
        self.assertIn("tlog entry 2 is missing signedEntryTimestamp", errors)
        self.assertIn(
            "tlog entry 2 checkpoint does not reference rekor.sigstore.dev", errors
        )
        self.assertIn("tlog entry 2 is missing canonicalizedBody", errors)
        self.assertTrue(
            any(
                error.startswith("tlog entry 3 canonicalizedBody is invalid:")
                for error in errors
            )
        )
        self.assertIn("tlog entry 4 hash algorithm is not sha256", errors)
        self.assertIn("tlog entry 4 hash does not match artifact sha256", errors)
        self.assertIn(
            "tlog entry 4 signature content does not match bundle signature", errors
        )
        self.assertIn("tlog entry 4 uses external public key URLs", errors)
        self.assertIn("tlog entry 4 publicKey.content is missing", errors)
        self.assertIn("tlog entry 5 is missing publicKey metadata", errors)

    def test_validate_sigstore_bundle_rejects_missing_required_blocks(self):
        from aiir._sign import validate_sigstore_bundle

        artifact_bytes = b'{"type":"test"}'
        cases = [
            (
                {"mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json"},
                "missing messageSignature block",
            ),
            (
                {
                    "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                    "messageSignature": {},
                },
                "missing messageDigest block",
            ),
            (
                {
                    "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                    "messageSignature": {
                        "messageDigest": {
                            "algorithm": "SHA2_256",
                            "digest": base64.b64encode(
                                hashlib.sha256(artifact_bytes).digest()
                            ).decode("ascii"),
                        },
                        "signature": "bundle-signature",
                    },
                },
                "missing verificationMaterial block",
            ),
            (
                {
                    "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                    "messageSignature": {
                        "messageDigest": {
                            "algorithm": "SHA2_256",
                            "digest": base64.b64encode(
                                hashlib.sha256(artifact_bytes).digest()
                            ).decode("ascii"),
                        },
                        "signature": "bundle-signature",
                    },
                    "verificationMaterial": {},
                },
                "bundle is missing Rekor tlog entries",
            ),
        ]

        for bundle, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(
                    validate_sigstore_bundle(artifact_bytes, bundle), [expected]
                )


class TestSigstoreVerification(unittest.TestCase):
    """Tests for verify_receipt_signature() with mocked sigstore."""

    def test_verify_missing_receipt(self):
        """verify_receipt_signature() returns error for missing receipt file."""
        # Need sigstore modules available for the function to proceed past import
        import types

        mock_sigstore = types.ModuleType("sigstore")
        mock_verify = types.ModuleType("sigstore.verify")
        mock_verify.Verifier = unittest.mock.MagicMock()
        mock_policy = types.ModuleType("sigstore.verify.policy")
        mock_policy.UnsafeNoOp = unittest.mock.MagicMock()
        mock_policy.Identity = unittest.mock.MagicMock()
        mock_models = types.ModuleType("sigstore.models")
        mock_models.Bundle = unittest.mock.MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "sigstore": mock_sigstore,
                "sigstore.verify": mock_verify,
                "sigstore.verify.policy": mock_policy,
                "sigstore.models": mock_models,
            },
        ):
            result = cli.verify_receipt_signature("/tmp/no_such_receipt_xyz.json")
        self.assertFalse(result["valid"])
        self.assertIn("not found", result["error"])

    def test_verify_missing_bundle(self):
        """verify_receipt_signature() returns error when .sigstore bundle missing."""
        import types

        mock_sigstore = types.ModuleType("sigstore")
        mock_verify = types.ModuleType("sigstore.verify")
        mock_verify.Verifier = unittest.mock.MagicMock()
        mock_policy = types.ModuleType("sigstore.verify.policy")
        mock_policy.UnsafeNoOp = unittest.mock.MagicMock()
        mock_policy.Identity = unittest.mock.MagicMock()
        mock_models = types.ModuleType("sigstore.models")
        mock_models.Bundle = unittest.mock.MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            receipt_path = os.path.join(tmpdir, "receipt.json")
            Path(receipt_path).write_text("{}", encoding="utf-8")

            with patch.dict(
                "sys.modules",
                {
                    "sigstore": mock_sigstore,
                    "sigstore.verify": mock_verify,
                    "sigstore.verify.policy": mock_policy,
                    "sigstore.models": mock_models,
                },
            ):
                result = cli.verify_receipt_signature(receipt_path)
            self.assertFalse(result["valid"])
            self.assertIn("bundle not found", result["error"].lower())

    def test_verify_successful_signature(self):
        """verify_receipt_signature() returns valid=True when verification passes."""
        import types

        mock_verifier = unittest.mock.MagicMock()
        mock_verifier.verify_artifact.return_value = None  # No exception = success

        mock_sigstore = types.ModuleType("sigstore")
        mock_verify_mod = types.ModuleType("sigstore.verify")
        mock_verify_mod.Verifier = unittest.mock.MagicMock()
        mock_verify_mod.Verifier.production.return_value = mock_verifier
        mock_policy = types.ModuleType("sigstore.verify.policy")
        mock_policy.UnsafeNoOp = unittest.mock.MagicMock()
        mock_policy.Identity = unittest.mock.MagicMock()
        mock_models = types.ModuleType("sigstore.models")
        mock_models.Bundle = unittest.mock.MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            receipt_path = os.path.join(tmpdir, "receipt.json")
            bundle_path = receipt_path + ".sigstore"
            Path(receipt_path).write_text('{"type":"test"}', encoding="utf-8")
            Path(bundle_path).write_text('{"mediaType":"bundle"}', encoding="utf-8")

            bundle_summary = {
                "media_type": "application/vnd.dev.sigstore.bundle.v0.3+json",
                "tlog_entry_count": 1,
                "entries": [
                    {
                        "kind": "hashedrekord",
                        "log_index": "123",
                        "integrated_time_rfc3339": "2026-04-01T09:03:20Z",
                    }
                ],
            }
            with (
                patch.dict(
                    "sys.modules",
                    {
                        "sigstore": mock_sigstore,
                        "sigstore.verify": mock_verify_mod,
                        "sigstore.verify.policy": mock_policy,
                        "sigstore.models": mock_models,
                    },
                ),
                patch("aiir._sign.validate_sigstore_bundle", return_value=[]),
                patch(
                    "aiir._sign.summarize_sigstore_bundle", return_value=bundle_summary
                ),
            ):
                result = cli.verify_receipt_signature(receipt_path)
            self.assertTrue(result["valid"])
            self.assertTrue(result["signature_valid"])
            self.assertEqual(result["policy"], "any")
            self.assertEqual(result["bundle"], bundle_summary)

    def test_verify_successful_signature_with_identity_pinning(self):
        """verify_receipt_signature() carries identity policy details on success."""
        import types

        mock_verifier = unittest.mock.MagicMock()
        mock_verifier.verify_artifact.return_value = None

        mock_sigstore = types.ModuleType("sigstore")
        mock_verify_mod = types.ModuleType("sigstore.verify")
        mock_verify_mod.Verifier = unittest.mock.MagicMock()
        mock_verify_mod.Verifier.production.return_value = mock_verifier
        mock_policy = types.ModuleType("sigstore.verify.policy")
        mock_policy.UnsafeNoOp = unittest.mock.MagicMock()
        mock_policy.Identity = unittest.mock.MagicMock(return_value="identity-policy")
        mock_models = types.ModuleType("sigstore.models")
        mock_models.Bundle = unittest.mock.MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            receipt_path = os.path.join(tmpdir, "receipt.json")
            bundle_path = receipt_path + ".sigstore"
            Path(receipt_path).write_text('{"type":"test"}', encoding="utf-8")
            Path(bundle_path).write_text('{"mediaType":"bundle"}', encoding="utf-8")

            bundle_summary = {
                "media_type": "application/vnd.dev.sigstore.bundle.v0.3+json",
                "tlog_entry_count": 1,
                "entries": [],
            }
            with (
                patch.dict(
                    "sys.modules",
                    {
                        "sigstore": mock_sigstore,
                        "sigstore.verify": mock_verify_mod,
                        "sigstore.verify.policy": mock_policy,
                        "sigstore.models": mock_models,
                    },
                ),
                patch("aiir._sign.validate_sigstore_bundle", return_value=[]),
                patch(
                    "aiir._sign.summarize_sigstore_bundle", return_value=bundle_summary
                ),
            ):
                result = cli.verify_receipt_signature(
                    receipt_path,
                    expected_identity="user@example.com",
                    expected_issuer="https://issuer.example",
                )

            self.assertTrue(result["valid"])
            self.assertEqual(result["policy"], "identity")
            self.assertEqual(result["expected_identity"], "user@example.com")
            self.assertEqual(result["expected_issuer"], "https://issuer.example")
            mock_policy.Identity.assert_called_once_with(
                identity="user@example.com",
                issuer="https://issuer.example",
            )

    def test_verify_signature_sanitizes_exception_message(self):
        """verify_receipt_signature() redacts filesystem paths from errors."""
        import types

        mock_sigstore = types.ModuleType("sigstore")
        mock_verify_mod = types.ModuleType("sigstore.verify")
        mock_verify_mod.Verifier = unittest.mock.MagicMock()
        mock_verify_mod.Verifier.production.return_value = unittest.mock.MagicMock()
        mock_policy = types.ModuleType("sigstore.verify.policy")
        mock_policy.UnsafeNoOp = unittest.mock.MagicMock()
        mock_policy.Identity = unittest.mock.MagicMock()
        mock_models = types.ModuleType("sigstore.models")
        mock_models.Bundle = unittest.mock.MagicMock()
        mock_models.Bundle.from_json.side_effect = RuntimeError(
            "/tmp/private/oidc/token-value\nsecond line should be dropped"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            receipt_path = os.path.join(tmpdir, "receipt.json")
            bundle_path = receipt_path + ".sigstore"
            Path(receipt_path).write_text('{"type":"test"}', encoding="utf-8")
            Path(bundle_path).write_text('{"mediaType":"bundle"}', encoding="utf-8")

            with (
                patch.dict(
                    "sys.modules",
                    {
                        "sigstore": mock_sigstore,
                        "sigstore.verify": mock_verify_mod,
                        "sigstore.verify.policy": mock_policy,
                        "sigstore.models": mock_models,
                    },
                ),
                patch("aiir._sign.validate_sigstore_bundle", return_value=[]),
                patch(
                    "aiir._sign.summarize_sigstore_bundle",
                    return_value={"tlog_entry_count": 0, "entries": []},
                ),
            ):
                result = cli.verify_receipt_signature(receipt_path)

            self.assertFalse(result["valid"])
            self.assertIn("<path>", result["error"])
            self.assertNotIn("/tmp/private", result["error"])
            self.assertNotIn("second line", result["error"])

    def test_verify_signature_rejects_non_object_bundle_json(self):
        """verify_receipt_signature() fails cleanly when the bundle JSON is not an object."""
        import types

        mock_sigstore = types.ModuleType("sigstore")
        mock_verify_mod = types.ModuleType("sigstore.verify")
        mock_verify_mod.Verifier = unittest.mock.MagicMock()
        mock_policy = types.ModuleType("sigstore.verify.policy")
        mock_policy.UnsafeNoOp = unittest.mock.MagicMock()
        mock_policy.Identity = unittest.mock.MagicMock()
        mock_models = types.ModuleType("sigstore.models")
        mock_models.Bundle = unittest.mock.MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            receipt_path = os.path.join(tmpdir, "receipt.json")
            bundle_path = receipt_path + ".sigstore"
            Path(receipt_path).write_text('{"type":"test"}', encoding="utf-8")
            Path(bundle_path).write_text("[]", encoding="utf-8")

            with patch.dict(
                "sys.modules",
                {
                    "sigstore": mock_sigstore,
                    "sigstore.verify": mock_verify_mod,
                    "sigstore.verify.policy": mock_policy,
                    "sigstore.models": mock_models,
                },
            ):
                result = cli.verify_receipt_signature(receipt_path)

            self.assertFalse(result["valid"])
            self.assertEqual(result["error"], "bundle JSON must be an object")

    def test_verify_rejects_bundle_sanity_failures_with_identity_expectations(self):
        """Bundle sanity failures preserve identity expectations for caller context."""
        import types

        mock_sigstore = types.ModuleType("sigstore")
        mock_verify_mod = types.ModuleType("sigstore.verify")
        mock_verify_mod.Verifier = unittest.mock.MagicMock()
        mock_policy = types.ModuleType("sigstore.verify.policy")
        mock_policy.UnsafeNoOp = unittest.mock.MagicMock()
        mock_policy.Identity = unittest.mock.MagicMock()
        mock_models = types.ModuleType("sigstore.models")
        mock_models.Bundle = unittest.mock.MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            receipt_path = os.path.join(tmpdir, "receipt.json")
            bundle_path = receipt_path + ".sigstore"
            Path(receipt_path).write_text('{"type":"test"}', encoding="utf-8")
            Path(bundle_path).write_text("{}", encoding="utf-8")

            with (
                patch.dict(
                    "sys.modules",
                    {
                        "sigstore": mock_sigstore,
                        "sigstore.verify": mock_verify_mod,
                        "sigstore.verify.policy": mock_policy,
                        "sigstore.models": mock_models,
                    },
                ),
                patch(
                    "aiir._sign.validate_sigstore_bundle",
                    return_value=["bundle mismatch"],
                ),
                patch(
                    "aiir._sign.summarize_sigstore_bundle",
                    return_value={"tlog_entry_count": 0, "entries": []},
                ),
            ):
                result = cli.verify_receipt_signature(
                    receipt_path,
                    expected_identity="user@example.com",
                    expected_issuer="https://issuer.example",
                )

            self.assertFalse(result["valid"])
            self.assertEqual(result["error"], "bundle mismatch")
            self.assertEqual(result["expected_identity"], "user@example.com")
            self.assertEqual(result["expected_issuer"], "https://issuer.example")

    def test_verify_rejects_bundle_sanity_failures(self):
        """verify_receipt_signature() fails closed on malformed Rekor linkage."""
        import types

        mock_verifier = unittest.mock.MagicMock()
        mock_sigstore = types.ModuleType("sigstore")
        mock_verify_mod = types.ModuleType("sigstore.verify")
        mock_verify_mod.Verifier = unittest.mock.MagicMock()
        mock_verify_mod.Verifier.production.return_value = mock_verifier
        mock_policy = types.ModuleType("sigstore.verify.policy")
        mock_policy.UnsafeNoOp = unittest.mock.MagicMock()
        mock_policy.Identity = unittest.mock.MagicMock()
        mock_bundle_cls = unittest.mock.MagicMock()
        mock_models = types.ModuleType("sigstore.models")
        mock_models.Bundle = mock_bundle_cls

        with tempfile.TemporaryDirectory() as tmpdir:
            receipt_path = os.path.join(tmpdir, "receipt.json")
            bundle_path = receipt_path + ".sigstore"
            Path(receipt_path).write_text('{"type":"test"}', encoding="utf-8")
            Path(bundle_path).write_text("{}", encoding="utf-8")

            with patch.dict(
                "sys.modules",
                {
                    "sigstore": mock_sigstore,
                    "sigstore.verify": mock_verify_mod,
                    "sigstore.verify.policy": mock_policy,
                    "sigstore.models": mock_models,
                },
            ):
                result = cli.verify_receipt_signature(receipt_path)

            self.assertFalse(result["valid"])
            self.assertIn("unexpected mediaType", result["error"])
            self.assertIn("missing messageSignature block", result["errors"])
            mock_bundle_cls.from_json.assert_not_called()


class TestSignCLIFlags(unittest.TestCase):
    """Tests for --sign and --verify-signature CLI flag parsing."""

    def test_sign_without_output_fails(self):
        """--sign without --output should exit with error."""
        with patch("aiir.cli.get_repo_root", return_value="/tmp"):
            with patch("aiir.cli.generate_receipt", return_value={"type": "test"}):
                with patch("aiir.cli._sigstore_available", return_value=True):
                    ret = cli.main(["--commit", "HEAD", "--sign"])
        self.assertEqual(ret, 1)

    def test_sign_without_sigstore_fails(self):
        """--sign when sigstore not installed should exit with error."""
        with patch("aiir.cli.get_repo_root", return_value="/tmp"):
            with patch("aiir.cli.generate_receipt", return_value={"type": "test"}):
                with patch("aiir.cli._sigstore_available", return_value=False):
                    ret = cli.main(
                        ["--commit", "HEAD", "--sign", "--output", "/tmp/out"]
                    )
        self.assertEqual(ret, 1)

    def test_verify_signature_flag_parsed(self):
        """--verify-signature flag is correctly parsed by argparse."""
        with patch("aiir.cli.verify_receipt_file") as mock_verify:
            mock_verify.return_value = {
                "valid": True,
                "receipt_id": "g1-abc",
                "commit_sha": "abc123",
            }
            with patch("aiir.cli.verify_receipt_signature") as mock_sig:
                mock_sig.return_value = {
                    "valid": True,
                    "signature_valid": True,
                    "policy": "any",
                }
                ret = cli.main(["--verify", "/dev/null", "--verify-signature"])
        # verify_receipt_file was called
        mock_verify.assert_called_once()
        # verify_receipt_signature was also called
        mock_sig.assert_called_once()

    def test_verify_with_identity_pinning(self):
        """--signer-identity and --signer-issuer are passed through to verification."""
        with patch("aiir.cli.verify_receipt_file") as mock_verify:
            mock_verify.return_value = {
                "valid": True,
                "receipt_id": "g1-abc",
                "commit_sha": "abc123",
            }
            with patch("aiir.cli.verify_receipt_signature") as mock_sig:
                mock_sig.return_value = {
                    "valid": True,
                    "signature_valid": True,
                    "policy": "identity",
                }
                ret = cli.main(
                    [
                        "--verify",
                        "/dev/null",
                        "--verify-signature",
                        "--signer-identity",
                        "user@example.com",
                        "--signer-issuer",
                        "https://accounts.google.com",
                    ]
                )
        mock_sig.assert_called_once_with(
            "/dev/null",
            expected_identity="user@example.com",
            expected_issuer="https://accounts.google.com",
        )

    def test_verify_signature_success_prints_bundle_details(self):
        """Successful signature verification prints Rekor and signer details."""
        with patch("aiir.cli.verify_receipt_file") as mock_verify:
            mock_verify.return_value = {
                "valid": True,
                "receipt_id": "g1-abc",
                "commit_sha": "abc123",
            }
            with patch("aiir.cli.verify_receipt_signature") as mock_sig:
                mock_sig.return_value = {
                    "valid": True,
                    "signature_valid": True,
                    "policy": "identity",
                    "bundle": {
                        "entries": [
                            {
                                "kind": "hashedrekord",
                                "log_index": "123",
                                "integrated_time_rfc3339": "2026-04-01T09:03:20Z",
                            }
                        ],
                        "certificate_sha256": "sha256:abcdefghijklmnopqrstuvwxyz0123456789",
                    },
                }
                with (
                    patch("sys.stderr", new_callable=io.StringIO) as stderr,
                    patch("sys.stdout", new_callable=io.StringIO),
                ):
                    ret = cli.main(
                        [
                            "--verify",
                            "/dev/null",
                            "--verify-signature",
                            "--signer-identity",
                            "user@example.com",
                            "--signer-issuer",
                            "https://accounts.google.com",
                        ]
                    )
        self.assertEqual(ret, 0)
        stderr_text = stderr.getvalue()
        self.assertIn("Signature verified (policy=identity)", stderr_text)
        self.assertIn(
            "Rekor: hashedrekord, logIndex=123, integrated=2026-04-01T09:03:20Z",
            stderr_text,
        )
        self.assertIn("Certificate: sha256:", stderr_text)
        self.assertIn("Expected signer: user@example.com", stderr_text)
        self.assertIn(
            "Expected issuer: https://accounts.google.com",
            stderr_text,
        )

    def test_verify_signature_success_without_bundle_details(self):
        """Successful signature verification omits Rekor detail lines when bundle data is sparse."""
        with patch("aiir.cli.verify_receipt_file") as mock_verify:
            mock_verify.return_value = {
                "valid": True,
                "receipt_id": "g1-abc",
                "commit_sha": "abc123",
            }
            with patch("aiir.cli.verify_receipt_signature") as mock_sig:
                mock_sig.return_value = {
                    "valid": True,
                    "signature_valid": True,
                    "policy": "any",
                    "bundle": {"entries": [{}]},
                }
                with (
                    patch("sys.stderr", new_callable=io.StringIO) as stderr,
                    patch("sys.stdout", new_callable=io.StringIO),
                ):
                    ret = cli.main(["--verify", "/dev/null", "--verify-signature"])
        self.assertEqual(ret, 0)
        stderr_text = stderr.getvalue()
        self.assertIn("Signature verified (policy=any)", stderr_text)
        self.assertNotIn("Rekor:", stderr_text)
        self.assertNotIn("Certificate:", stderr_text)

    def test_verify_signature_success_with_non_dict_bundle(self):
        """Successful signature verification tolerates a non-dict bundle summary."""
        with patch("aiir.cli.verify_receipt_file") as mock_verify:
            mock_verify.return_value = {
                "valid": True,
                "receipt_id": "g1-abc",
                "commit_sha": "abc123",
            }
            with patch("aiir.cli.verify_receipt_signature") as mock_sig:
                mock_sig.return_value = {
                    "valid": True,
                    "signature_valid": True,
                    "policy": "any",
                    "bundle": [],
                }
                with (
                    patch("sys.stderr", new_callable=io.StringIO) as stderr,
                    patch("sys.stdout", new_callable=io.StringIO),
                ):
                    ret = cli.main(["--verify", "/dev/null", "--verify-signature"])
        self.assertEqual(ret, 0)
        self.assertIn("Signature verified (policy=any)", stderr.getvalue())

    def test_verify_signature_failure_returns_nonzero(self):
        """Failed signature verification returns exit code 1."""
        with patch("aiir.cli.verify_receipt_file") as mock_verify:
            mock_verify.return_value = {
                "valid": True,
                "receipt_id": "g1-abc",
                "commit_sha": "abc123",
            }
            with patch("aiir.cli.verify_receipt_signature") as mock_sig:
                mock_sig.return_value = {
                    "valid": False,
                    "signature_valid": False,
                    "error": "bad sig",
                }
                ret = cli.main(["--verify", "/dev/null", "--verify-signature"])
        self.assertEqual(ret, 1)

    def test_verify_signature_failure_prints_additional_bundle_errors(self):
        """Failed signature verification prints extra bundle errors after the primary one."""
        with patch("aiir.cli.verify_receipt_file") as mock_verify:
            mock_verify.return_value = {
                "valid": True,
                "receipt_id": "g1-abc",
                "commit_sha": "abc123",
            }
            with patch("aiir.cli.verify_receipt_signature") as mock_sig:
                mock_sig.return_value = {
                    "valid": False,
                    "signature_valid": False,
                    "error": "bad sig",
                    "errors": ["bad sig", "bundle mismatch", "missing tlog"],
                }
                with (
                    patch("sys.stderr", new_callable=io.StringIO) as stderr,
                    patch("sys.stdout", new_callable=io.StringIO),
                ):
                    ret = cli.main(["--verify", "/dev/null", "--verify-signature"])
        self.assertEqual(ret, 1)
        stderr_text = stderr.getvalue()
        self.assertIn("Signature FAILED: bad sig", stderr_text)
        self.assertIn("* bundle mismatch", stderr_text)
        self.assertIn("* missing tlog", stderr_text)


class TestSignCIDetection(unittest.TestCase):
    """Tests for CI environment detection when ambient OIDC credential is missing."""

    def test_sign_in_github_actions_no_oidc_raises_clear_error(self):
        """sign_receipt() in GitHub Actions without OIDC gives a targeted error."""
        import types

        mock_sigstore_sign = types.ModuleType("sigstore.sign")
        mock_sigstore_sign.SigningContext = unittest.mock.MagicMock()

        mock_sigstore_models = types.ModuleType("sigstore.models")
        mock_sigstore_models.ClientTrustConfig = unittest.mock.MagicMock()

        mock_sigstore_oidc = types.ModuleType("sigstore.oidc")
        mock_sigstore_oidc.detect_credential = unittest.mock.MagicMock(
            return_value=None
        )
        mock_sigstore_oidc.IdentityToken = unittest.mock.MagicMock()
        mock_sigstore_oidc.Issuer = unittest.mock.MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "sigstore": types.ModuleType("sigstore"),
                "sigstore.sign": mock_sigstore_sign,
                "sigstore.models": mock_sigstore_models,
                "sigstore.oidc": mock_sigstore_oidc,
            },
        ):
            with patch.dict(
                "os.environ", {"GITHUB_ACTIONS": "true", "CI": "true"}, clear=False
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    cli.sign_receipt(b'{"test": true}')
                self.assertIn("id-token: write", str(ctx.exception))
                self.assertIn("no ambient OIDC credential", str(ctx.exception))

    def test_sign_in_github_actions_fork_pr_mentions_fork(self):
        """sign_receipt() on a fork PR mentions fork limitation in error."""
        import types

        mock_sigstore_sign = types.ModuleType("sigstore.sign")
        mock_sigstore_sign.SigningContext = unittest.mock.MagicMock()

        mock_sigstore_models = types.ModuleType("sigstore.models")
        mock_sigstore_models.ClientTrustConfig = unittest.mock.MagicMock()

        mock_sigstore_oidc = types.ModuleType("sigstore.oidc")
        mock_sigstore_oidc.detect_credential = unittest.mock.MagicMock(
            return_value=None
        )
        mock_sigstore_oidc.IdentityToken = unittest.mock.MagicMock()
        mock_sigstore_oidc.Issuer = unittest.mock.MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "sigstore": types.ModuleType("sigstore"),
                "sigstore.sign": mock_sigstore_sign,
                "sigstore.models": mock_sigstore_models,
                "sigstore.oidc": mock_sigstore_oidc,
            },
        ):
            with patch.dict(
                "os.environ",
                {
                    "GITHUB_ACTIONS": "true",
                    "CI": "true",
                    "GITHUB_EVENT_NAME": "pull_request",
                },
                clear=False,
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    cli.sign_receipt(b'{"test": true}')
                self.assertIn("Fork PRs", str(ctx.exception))

    def test_sign_in_generic_ci_no_oidc_raises_clear_error(self):
        """sign_receipt() in generic CI without OIDC gives a clear error."""
        import types

        mock_sigstore_sign = types.ModuleType("sigstore.sign")
        mock_sigstore_sign.SigningContext = unittest.mock.MagicMock()

        mock_sigstore_models = types.ModuleType("sigstore.models")
        mock_sigstore_models.ClientTrustConfig = unittest.mock.MagicMock()

        mock_sigstore_oidc = types.ModuleType("sigstore.oidc")
        mock_sigstore_oidc.detect_credential = unittest.mock.MagicMock(
            return_value=None
        )
        mock_sigstore_oidc.IdentityToken = unittest.mock.MagicMock()
        mock_sigstore_oidc.Issuer = unittest.mock.MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "sigstore": types.ModuleType("sigstore"),
                "sigstore.sign": mock_sigstore_sign,
                "sigstore.models": mock_sigstore_models,
                "sigstore.oidc": mock_sigstore_oidc,
            },
        ):
            with patch.dict("os.environ", {"CI": "true"}, clear=False):
                # Remove GitHub-specific env vars
                with patch.dict(
                    "os.environ",
                    {
                        "GITHUB_ACTIONS": "",
                        "GITLAB_CI": "",
                    },
                    clear=False,
                ):
                    env_backup = os.environ.copy()
                    os.environ.pop("GITHUB_ACTIONS", None)
                    os.environ.pop("GITLAB_CI", None)
                    try:
                        with self.assertRaises(RuntimeError) as ctx:
                            cli.sign_receipt(b'{"test": true}')
                        self.assertIn("no ambient OIDC credential", str(ctx.exception))
                        self.assertIn("sign: false", str(ctx.exception))
                        self.assertIn("SIGSTORE_ID_TOKEN", str(ctx.exception))
                    finally:
                        os.environ.update(env_backup)


# ---------------------------------------------------------------------------
# Round 4 red-team hardening tests (R4-XX)
# ---------------------------------------------------------------------------
