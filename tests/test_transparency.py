# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""Tests for offline transparency and witness verification."""

from __future__ import annotations

import base64
import hashlib
import importlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aiir.cli as cli
from aiir._ed25519 import public_key_from_seed, sign, verify
from aiir._transparency import (
    parse_witness_quorum,
    validate_rekor_bundle_schema,
    validate_trust_root_schema,
    verify_consistency_proof,
    verify_transparency_material,
)

ed25519 = importlib.import_module("aiir._ed25519")
transparency = importlib.import_module("aiir._transparency")

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _load_script_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _leaf_hash(data: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + data).digest()


def _node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _largest_power_of_two_less_than(value: int) -> int:
    return 1 << ((value - 1).bit_length() - 1)


def _tree_hash(leaves: list[bytes]) -> bytes:
    if not leaves:
        return hashlib.sha256(b"").digest()
    if len(leaves) == 1:
        return _leaf_hash(leaves[0])
    split = _largest_power_of_two_less_than(len(leaves))
    return _node_hash(_tree_hash(leaves[:split]), _tree_hash(leaves[split:]))


def _consistency_proof(leaves: list[bytes], old_size: int) -> list[bytes]:
    if old_size == len(leaves):
        return []
    split = _largest_power_of_two_less_than(len(leaves))
    if old_size <= split:
        return _consistency_proof(leaves[:split], old_size) + [
            _tree_hash(leaves[split:])
        ]
    return _consistency_proof(leaves[split:], old_size - split) + [
        _tree_hash(leaves[:split])
    ]


def _key_id(name: str, signature_type: int, public_key: bytes) -> str:
    digest = hashlib.sha256(
        name.encode("utf-8") + b"\n" + bytes([signature_type]) + public_key
    ).digest()
    return digest[:4].hex()


def _signed_note(body: str, signatures: list[tuple[str, bytes]]) -> str:
    signature_lines = []
    for name, payload in signatures:
        encoded = base64.b64encode(payload).decode("ascii")
        signature_lines.append(f"\u2014 {name} {encoded}")
    return body + "\n" + "\n".join(signature_lines) + "\n"


class TestEd25519Verification(unittest.TestCase):
    def test_rfc8032_vector_verifies(self):
        seed = bytes.fromhex(
            "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
        )
        public_key = bytes.fromhex(
            "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
        )
        signature = bytes.fromhex(
            "e5564300c360ac729086e2cc806e828a"
            "84877f1eb8e5d974d873e06522490155"
            "5fb8821590a33bacc61e39701cf9b46b"
            "d25bf5f0595bbe24655141438e7a100b"
        )
        self.assertEqual(public_key_from_seed(seed), public_key)
        self.assertTrue(verify(public_key, b"", signature))

    def test_rfc8032_vector_rejects_tampering(self):
        seed = bytes.fromhex(
            "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
        )
        public_key = public_key_from_seed(seed)
        signature = sign(seed, b"hello world")
        self.assertTrue(verify(public_key, b"hello world", signature))
        self.assertFalse(verify(public_key, b"HELLO world", signature))


class TestTransparencySchemas(unittest.TestCase):
    def test_validate_trust_root_schema_accepts_valid_document(self):
        public_key = base64.b64encode(public_key_from_seed(bytes([1]) * 32)).decode(
            "ascii"
        )
        document = {
            "schema": "aiir.trust.v1",
            "logs": [
                {
                    "name": "rekor.example/log",
                    "checkpoint_key_id": "deadbeef",
                    "public_key_type": "ed25519",
                    "public_key_b64": public_key,
                }
            ],
            "witnesses": [],
            "policy": {"require_witnesses": {"default": "0-of-0"}},
        }
        self.assertEqual(validate_trust_root_schema(document), [])

    def test_validate_trust_root_schema_rejects_bad_key_id(self):
        public_key = base64.b64encode(public_key_from_seed(bytes([1]) * 32)).decode(
            "ascii"
        )
        document = {
            "schema": "aiir.trust.v1",
            "logs": [
                {
                    "name": "rekor.example/log",
                    "checkpoint_key_id": "not-hex",
                    "public_key_type": "ed25519",
                    "public_key_b64": public_key,
                }
            ],
        }
        errors = validate_trust_root_schema(document)
        self.assertTrue(any("checkpoint_key_id" in error for error in errors))

    def test_validate_rekor_bundle_schema_rejects_invalid_root_hash(self):
        document = {
            "schema": "aiir.rekor.bundle.v1",
            "log_id": "rekor-log-1",
            "artifact_sha256": "sha256:" + "a" * 64,
            "body_b64": base64.b64encode(b"{}").decode("ascii"),
            "body_hash": "sha256:" + hashlib.sha256(b"{}").hexdigest(),
            "log_index": 0,
            "integrated_time": 1710000000,
            "inclusion_proof": {
                "tree_size": 1,
                "root_hash": "not-base64",
                "hashes": [],
                "checkpoint": "rekor.example/log\n1\nAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE=\n\n\u2014 rekor.example/log AAAA\n",
            },
        }
        errors = validate_rekor_bundle_schema(document)
        self.assertTrue(any("root_hash" in error for error in errors))

    def test_parse_witness_quorum(self):
        self.assertEqual(parse_witness_quorum("2-of-3"), (2, 3))
        with self.assertRaises(ValueError):
            parse_witness_quorum("3-of-2")

    def test_witness_quorum_example_trust_root_is_valid(self):
        example_path = (
            Path(__file__).resolve().parent.parent
            / "examples"
            / "witness-quorum"
            / "trust-root.example.json"
        )
        document = json.loads(example_path.read_text(encoding="utf-8"))
        self.assertEqual(validate_trust_root_schema(document), [])
        self.assertEqual(document["policy"]["require_witnesses"]["release"], "2-of-3")
        self.assertEqual(len(document["witnesses"]), 3)


class TestTransparencyVerification(unittest.TestCase):
    LOG_NAME = "rekor.example/log"
    WITNESS_NAME = "witness.example/w1"
    LOG_ID = "rekor-log-1"
    LOG_SEED = bytes(range(1, 33))
    WITNESS_SEED = bytes(range(101, 133))
    WITNESS_TIMESTAMP = 1700000000

    def _build_fixture(self, root: Path) -> dict[str, Path]:
        artifact_path = root / "artifact.bin"
        artifact_bytes = b"artifact-bytes"
        artifact_path.write_bytes(artifact_bytes)
        artifact_sha256 = "sha256:" + hashlib.sha256(artifact_bytes).hexdigest()

        body_bytes = json.dumps(
            {"kind": "hashedrekord", "artifact_sha256": artifact_sha256},
            separators=(",", ":"),
        ).encode("utf-8")
        future_body_bytes = b"later-entry"

        old_root = _tree_hash([body_bytes])
        new_root = _tree_hash([body_bytes, future_body_bytes])
        old_body = f"{self.LOG_NAME}\n1\n{base64.b64encode(old_root).decode('ascii')}\n"
        new_body = f"{self.LOG_NAME}\n2\n{base64.b64encode(new_root).decode('ascii')}\n"

        log_public_key = public_key_from_seed(self.LOG_SEED)
        witness_public_key = public_key_from_seed(self.WITNESS_SEED)

        old_checkpoint = _signed_note(
            old_body,
            [
                (
                    self.LOG_NAME,
                    bytes.fromhex(_key_id(self.LOG_NAME, 0x01, log_public_key))
                    + sign(self.LOG_SEED, old_body.encode("utf-8")),
                )
            ],
        )
        witness_message = (
            b"cosignature/v1\n"
            + f"time {self.WITNESS_TIMESTAMP}\n".encode("ascii")
            + new_body.encode("utf-8")
        )
        witnessed_checkpoint = _signed_note(
            new_body,
            [
                (
                    self.LOG_NAME,
                    bytes.fromhex(_key_id(self.LOG_NAME, 0x01, log_public_key))
                    + sign(self.LOG_SEED, new_body.encode("utf-8")),
                ),
                (
                    self.WITNESS_NAME,
                    bytes.fromhex(_key_id(self.WITNESS_NAME, 0x04, witness_public_key))
                    + self.WITNESS_TIMESTAMP.to_bytes(8, "big")
                    + sign(self.WITNESS_SEED, witness_message),
                ),
            ],
        )

        bundle = {
            "schema": "aiir.rekor.bundle.v1",
            "log_id": self.LOG_ID,
            "artifact_sha256": artifact_sha256,
            "body_b64": base64.b64encode(body_bytes).decode("ascii"),
            "body_hash": "sha256:" + hashlib.sha256(body_bytes).hexdigest(),
            "log_index": 0,
            "integrated_time": 1710000000,
            "inclusion_proof": {
                "tree_size": 1,
                "root_hash": base64.b64encode(old_root).decode("ascii"),
                "hashes": [],
                "checkpoint": old_checkpoint,
            },
            "consistency_proof": {
                "old_tree_size": 1,
                "new_tree_size": 2,
                "hashes": [
                    base64.b64encode(item).decode("ascii")
                    for item in _consistency_proof([body_bytes, future_body_bytes], 1)
                ],
            },
        }
        trust_root = {
            "schema": "aiir.trust.v1",
            "logs": [
                {
                    "name": self.LOG_NAME,
                    "log_id": self.LOG_ID,
                    "checkpoint_key_id": _key_id(self.LOG_NAME, 0x01, log_public_key),
                    "public_key_type": "ed25519",
                    "public_key_b64": base64.b64encode(log_public_key).decode("ascii"),
                }
            ],
            "witnesses": [
                {
                    "name": self.WITNESS_NAME,
                    "key_id": _key_id(self.WITNESS_NAME, 0x04, witness_public_key),
                    "public_key_type": "ed25519",
                    "public_key_b64": base64.b64encode(witness_public_key).decode(
                        "ascii"
                    ),
                    "min_version": 1,
                }
            ],
            "policy": {
                "require_witnesses": {
                    "default": "0-of-0",
                    "release": "1-of-1",
                },
                "max_future_skew_seconds": 300,
            },
        }

        bundle_path = root / "rekor-bundle.json"
        trust_root_path = root / "trust-root.json"
        witnessed_checkpoint_path = root / "witnessed-checkpoint.txt"
        bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
        trust_root_path.write_text(json.dumps(trust_root), encoding="utf-8")
        witnessed_checkpoint_path.write_text(witnessed_checkpoint, encoding="utf-8")
        return {
            "artifact": artifact_path,
            "bundle": bundle_path,
            "trust_root": trust_root_path,
            "witnessed_checkpoint": witnessed_checkpoint_path,
        }

    def test_verify_consistency_proof_small_tree(self):
        leaves = [b"a", b"b", b"c"]
        old_root = _tree_hash(leaves[:2])
        new_root = _tree_hash(leaves)
        proof = _consistency_proof(leaves, 2)
        self.assertTrue(verify_consistency_proof(2, 3, old_root, new_root, proof))

    def test_verify_transparency_material_allows_checkpoint_only_when_policy_is_zero(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self._build_fixture(Path(tmp))
            result = verify_transparency_material(
                str(fixture["artifact"]),
                str(fixture["bundle"]),
                str(fixture["trust_root"]),
            )
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["witnessed_checkpoint"]["required"], "0-of-0")

    def test_verify_transparency_material_happy_path_with_witness(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self._build_fixture(Path(tmp))
            result = verify_transparency_material(
                str(fixture["artifact"]),
                str(fixture["bundle"]),
                str(fixture["trust_root"]),
                witnessed_checkpoint_path=str(fixture["witnessed_checkpoint"]),
                require_witnesses="release",
            )
        self.assertTrue(result["valid"], result)
        self.assertTrue(result["rekor_bundle"]["inclusion_proof_verified"])
        self.assertTrue(result["witnessed_checkpoint"]["consistency_proof_verified"])
        self.assertEqual(len(result["witnessed_checkpoint"]["verified_witnesses"]), 1)

    def test_verify_transparency_material_requires_witness_when_policy_demands_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self._build_fixture(Path(tmp))
            result = verify_transparency_material(
                str(fixture["artifact"]),
                str(fixture["bundle"]),
                str(fixture["trust_root"]),
                require_witnesses="1-of-1",
            )
        self.assertFalse(result["valid"])
        self.assertIn("witnessed checkpoint is required", result["error"])

    def test_artifact_mode_requires_bundle_and_trust_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "artifact.bin"
            artifact.write_bytes(b"demo")
            stderr = io.StringIO()
            with (
                patch("sys.stderr", stderr),
                patch("sys.stdout", io.StringIO()),
            ):
                code = cli.main(["--artifact", str(artifact)])
        self.assertEqual(code, 1)
        self.assertIn("--rekor-bundle", stderr.getvalue())

    def test_artifact_mode_verifies_offline_transparency(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self._build_fixture(Path(tmp))
            stderr = io.StringIO()
            stdout = io.StringIO()
            with (
                patch("sys.stderr", stderr),
                patch("sys.stdout", stdout),
            ):
                code = cli.main(
                    [
                        "--artifact",
                        str(fixture["artifact"]),
                        "--rekor-bundle",
                        str(fixture["bundle"]),
                        "--trust-root",
                        str(fixture["trust_root"]),
                        "--witnessed-checkpoint",
                        str(fixture["witnessed_checkpoint"]),
                        "--require-witnesses",
                        "release",
                    ]
                )
        self.assertEqual(code, 0)
        self.assertIn("Artifact transparency verified", stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["valid"])
        self.assertTrue(payload["inclusion_proof_verified"])
        self.assertTrue(payload["witnessed_checkpoint_verified"])
        self.assertEqual(payload["verified_witness_count"], 1)


class TestEmitOfflineRekorBundle(unittest.TestCase):
    """Tests for scripts/emit_offline_rekor_bundle.py logic."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_script_module(
            "emit_offline_rekor_bundle", SCRIPTS_DIR / "emit_offline_rekor_bundle.py"
        )

    def _valid_bundle(self, artifact_bytes: bytes) -> dict[str, object]:
        artifact_sha256 = hashlib.sha256(artifact_bytes).digest()
        artifact_sha256_hex = artifact_sha256.hex()
        artifact_sha256_b64 = base64.b64encode(artifact_sha256).decode("ascii")
        root_hash_b64 = base64.b64encode(b"r" * 32).decode("ascii")
        rekor_body = {
            "apiVersion": "0.0.1",
            "kind": "hashedrekord",
            "spec": {
                "data": {"hash": {"algorithm": "sha256", "value": artifact_sha256_hex}},
                "signature": {
                    "content": "bundle-signature",
                    "publicKey": {"content": "public-key"},
                },
            },
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
                "certificate": {"rawBytes": "fake-cert"},
                "tlogEntries": [
                    {
                        "kindVersion": {"kind": "hashedrekord", "version": "0.0.1"},
                        "integratedTime": "1772986853",
                        "logIndex": "123",
                        "logId": {"keyId": "rekor-key"},
                        "inclusionPromise": {"signedEntryTimestamp": "fake-set"},
                        "inclusionProof": {
                            "logIndex": "123",
                            "treeSize": "456",
                            "rootHash": root_hash_b64,
                            "hashes": [],
                            "checkpoint": {
                                "envelope": "rekor.sigstore.dev - 1\n456\n"
                                + root_hash_b64
                                + "\n\n\u2014 rekor.sigstore.dev AAAA\n"
                            },
                        },
                        "canonicalizedBody": base64.b64encode(
                            json.dumps(rekor_body, separators=(",", ":")).encode(
                                "utf-8"
                            )
                        ).decode("ascii"),
                    }
                ],
                "timestampVerificationData": {},
            },
        }

    def test_build_rekor_bundle_happy_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "artifact.whl"
            artifact.write_bytes(b"wheel-bytes")
            result = self.mod.build_rekor_bundle(
                artifact, self._valid_bundle(b"wheel-bytes")
            )

        self.assertEqual(result["schema"], "aiir.rekor.bundle.v1")
        self.assertEqual(
            result["artifact_sha256"],
            "sha256:" + hashlib.sha256(b"wheel-bytes").hexdigest(),
        )
        self.assertEqual(result["log_id"], "rekor-key")
        self.assertEqual(result["log_index"], "123")
        self.assertEqual(result["inclusion_proof"]["tree_size"], "456")

    def test_build_rekor_bundle_requires_full_inclusion_proof(self):
        bundle = self._valid_bundle(b"wheel-bytes")
        bundle["verificationMaterial"]["tlogEntries"][0]["inclusionProof"].pop(
            "rootHash"
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "artifact.whl"
            artifact.write_bytes(b"wheel-bytes")
            with self.assertRaises(ValueError):
                self.mod.build_rekor_bundle(artifact, bundle)

    def test_main_writes_rekor_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "artifact.whl"
            artifact.write_bytes(b"wheel-bytes")
            bundle_path = root / "bundle.json"
            bundle_path.write_text(
                json.dumps(self._valid_bundle(b"wheel-bytes")), encoding="utf-8"
            )
            output_path = root / "rekor-bundle.json"

            code = self.mod.main(
                [
                    "--artifact",
                    str(artifact),
                    "--bundle",
                    str(bundle_path),
                    "--output",
                    str(output_path),
                ]
            )

            self.assertEqual(code, 0)
            written = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(written["schema"], "aiir.rekor.bundle.v1")


class TestOfflineRekorWorkflowSurfaces(unittest.TestCase):
    def test_repo_workflow_emits_offline_rekor_assets(self):
        content = (WORKFLOWS_DIR / "offline-rekor-release.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("scripts/emit_offline_rekor_bundle.py", content)
        self.assertIn("VERIFY-OFFLINE.md", content)
        self.assertIn(".rekor-bundle.json", content)
        self.assertIn("attestations/sha256:", content)
        self.assertIn("e.g. vX.Y.Z", content)
        self.assertNotIn("v1.3.0", content)

        publish_content = (WORKFLOWS_DIR / "publish.yml").read_text(encoding="utf-8")
        self.assertNotIn("scripts/emit_offline_rekor_bundle.py", publish_content)
        self.assertNotIn("VERIFY-OFFLINE.md", publish_content)

        recovery_content = (WORKFLOWS_DIR / "release-recovery.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("scripts/emit_offline_rekor_bundle.py", recovery_content)
        self.assertNotIn("VERIFY-OFFLINE.md", recovery_content)


class TestEd25519DefensiveBranches(unittest.TestCase):
    def setUp(self):
        self.seed = bytes([7]) * 32
        self.public_key = public_key_from_seed(self.seed)
        self.signature = sign(self.seed, b"message")

    def test_decode_point_rejects_invalid_inputs(self):
        with self.assertRaisesRegex(ValueError, "32 bytes"):
            ed25519.decode_point(b"short")

        with self.assertRaisesRegex(ValueError, "out-of-range y coordinate"):
            ed25519.decode_point(ed25519._Q.to_bytes(32, "little"))

        with patch.object(ed25519, "_is_on_curve", return_value=False):
            with self.assertRaisesRegex(ValueError, "not on the curve"):
                ed25519.decode_point(b"\x01" + b"\x00" * 31)

    def test_public_key_from_seed_requires_32_byte_seed(self):
        with self.assertRaisesRegex(ValueError, "32 bytes"):
            public_key_from_seed(b"tiny")

    def test_verify_rejects_invalid_inputs_and_subgroup_failures(self):
        self.assertFalse(verify(b"short", b"message", self.signature))

        with patch.object(ed25519, "decode_point", side_effect=ValueError("bad point")):
            self.assertFalse(verify(self.public_key, b"message", self.signature))

        with patch.object(ed25519, "_scalar_mult", return_value=(1, 2)):
            self.assertFalse(verify(self.public_key, b"message", self.signature))

        with patch.object(
            ed25519,
            "_scalar_mult",
            side_effect=[ed25519._IDENTITY, (1, 2)],
        ):
            self.assertFalse(verify(self.public_key, b"message", self.signature))

        bad_scalar_signature = self.signature[:32] + ed25519._L.to_bytes(32, "little")
        self.assertFalse(verify(self.public_key, b"message", bad_scalar_signature))


class TestTransparencySchemaFailures(unittest.TestCase):
    def setUp(self):
        self.public_key_b64 = base64.b64encode(
            public_key_from_seed(bytes([1]) * 32)
        ).decode("ascii")
        self.hash_b64 = base64.b64encode(b"h" * 32).decode("ascii")

    def test_validate_trust_root_schema_rejects_non_objects_and_non_lists(self):
        self.assertEqual(
            validate_trust_root_schema([]),
            ["Trust root must be a JSON object"],
        )

        errors = validate_trust_root_schema(
            {
                "schema": "aiir.trust.v1",
                "logs": "bad",
                "witnesses": "bad",
                "policy": [],
            }
        )
        self.assertIn("logs must be an array", errors)
        self.assertIn("witnesses must be an array when present", errors)
        self.assertIn("policy must be an object when present", errors)

    def test_validate_trust_root_schema_reports_nested_errors(self):
        errors = validate_trust_root_schema(
            {
                "schema": "wrong",
                "logs": [
                    "bad-log-entry",
                    {
                        "name": "bad name",
                        "checkpoint_key_id": "oops",
                        "log_id": 7,
                        "public_key_type": "rsa",
                        "public_key_b64": "@@@",
                    },
                ],
                "witnesses": [
                    "bad-witness-entry",
                    {
                        "name": "bad name",
                        "key_id": "oops",
                        "public_key_type": "rsa",
                        "public_key_b64": "@@@",
                        "min_version": 0,
                    },
                ],
                "policy": {
                    "max_future_skew_seconds": -1,
                    "require_witnesses": {
                        1: "0-of-0",
                        "release": 3,
                        "broken": "2-of-1",
                    },
                },
            }
        )
        for fragment in [
            "schema must be 'aiir.trust.v1'",
            "logs[0] must be an object",
            "logs[1].name must be a non-empty key name",
            "logs[1].checkpoint_key_id must be 8 lowercase hex chars",
            "logs[1].log_id must be a string when present",
            "logs[1].public_key_type must be 'ed25519'",
            "logs[1].public_key_b64 must be valid base64",
            "witnesses[0] must be an object",
            "witnesses[1].name must be a non-empty key name",
            "witnesses[1].key_id must be 8 lowercase hex chars",
            "witnesses[1].public_key_type must be 'ed25519'",
            "witnesses[1].public_key_b64 must be valid base64",
            "witnesses[1].min_version must be a positive integer",
            "policy.max_future_skew_seconds must be a non-negative integer",
            "policy.require_witnesses keys must be strings",
            "policy.require_witnesses.release must be a string",
            "policy.require_witnesses.broken: witness policy cannot require more witnesses than it allows",
        ]:
            self.assertTrue(any(fragment in error for error in errors), fragment)

    def test_validate_trust_root_schema_rejects_non_dict_require_witnesses(self):
        errors = validate_trust_root_schema(
            {
                "schema": "aiir.trust.v1",
                "logs": [],
                "policy": {"require_witnesses": []},
            }
        )
        self.assertIn(
            "policy.require_witnesses must be an object when present",
            errors,
        )

    def test_validate_trust_root_schema_allows_empty_require_witnesses_map(self):
        self.assertEqual(
            validate_trust_root_schema(
                {
                    "schema": "aiir.trust.v1",
                    "logs": [],
                    "policy": {"require_witnesses": {}},
                }
            ),
            [],
        )

    def test_validate_trust_root_schema_allows_policy_without_require_witnesses(self):
        self.assertEqual(
            validate_trust_root_schema(
                {
                    "schema": "aiir.trust.v1",
                    "logs": [],
                    "policy": {},
                }
            ),
            [],
        )

    def test_validate_rekor_bundle_schema_rejects_non_objects(self):
        self.assertEqual(
            validate_rekor_bundle_schema([]),
            ["Rekor bundle must be a JSON object"],
        )

    def test_validate_rekor_bundle_schema_reports_nested_errors(self):
        errors = validate_rekor_bundle_schema(
            {
                "schema": "wrong",
                "log_id": "",
                "artifact_sha256": "bad",
                "body_b64": "@@@",
                "body_hash": "bad",
                "log_index": True,
                "integrated_time": -1,
                "inclusion_proof": {
                    "tree_size": "01",
                    "root_hash": "@@@",
                    "hashes": ["@@@"],
                    "checkpoint": "",
                },
                "consistency_proof": {
                    "old_tree_size": -1,
                    "new_tree_size": "01",
                    "hashes": ["@@@"],
                },
            }
        )
        for fragment in [
            "schema must be 'aiir.rekor.bundle.v1'",
            "log_id is required",
            "artifact_sha256 must match",
            "body_b64 must be valid base64",
            "body_hash must match",
            "log_index must be a non-negative integer or decimal string",
            "integrated_time must be a non-negative integer or decimal string",
            "inclusion_proof.tree_size must be a non-negative integer or decimal string",
            "inclusion_proof.root_hash must be valid base64",
            "inclusion_proof.hashes[0] must be valid base64",
            "inclusion_proof.checkpoint must be a non-empty signed note",
            "consistency_proof.old_tree_size must be a non-negative integer or decimal string",
            "consistency_proof.new_tree_size must be a non-negative integer or decimal string",
            "consistency_proof.hashes[0] must be valid base64",
        ]:
            self.assertTrue(any(fragment in error for error in errors), fragment)

    def test_validate_rekor_bundle_schema_rejects_non_object_proofs(self):
        errors = validate_rekor_bundle_schema(
            {
                "schema": "aiir.rekor.bundle.v1",
                "log_id": "rekor-log-1",
                "artifact_sha256": "sha256:" + "a" * 64,
                "body_b64": base64.b64encode(b"{}").decode("ascii"),
                "log_index": 0,
                "integrated_time": 0,
                "inclusion_proof": "bad",
                "consistency_proof": "bad",
            }
        )
        self.assertIn("inclusion_proof must be an object", errors)
        self.assertIn("consistency_proof must be an object when present", errors)

    def test_validate_rekor_bundle_schema_rejects_non_list_hash_arrays(self):
        errors = validate_rekor_bundle_schema(
            {
                "schema": "aiir.rekor.bundle.v1",
                "log_id": "rekor-log-1",
                "artifact_sha256": "sha256:" + "a" * 64,
                "body_b64": base64.b64encode(b"{}").decode("ascii"),
                "log_index": 0,
                "integrated_time": 0,
                "inclusion_proof": {
                    "tree_size": 1,
                    "root_hash": self.hash_b64,
                    "hashes": "bad",
                    "checkpoint": "signed-note",
                },
                "consistency_proof": {
                    "old_tree_size": 1,
                    "new_tree_size": 2,
                    "hashes": "bad",
                },
            }
        )
        self.assertIn("inclusion_proof.hashes must be an array", errors)
        self.assertIn("consistency_proof.hashes must be an array", errors)


class TestTransparencyInternalHelpers(unittest.TestCase):
    LOG_NAME = "rekor.example/log"
    LOG_ID = "rekor-log-1"
    LOG_SEED = bytes(range(1, 33))
    WITNESS_NAME = "witness.example/w1"
    WITNESS_SEED = bytes(range(101, 133))

    def setUp(self):
        self.log_public_key = public_key_from_seed(self.LOG_SEED)
        self.witness_public_key = public_key_from_seed(self.WITNESS_SEED)
        self.checkpoint_key_id = _key_id(
            self.LOG_NAME,
            transparency._NOTE_TYPE_ED25519,
            self.log_public_key,
        )
        self.witness_key_id = _key_id(
            self.WITNESS_NAME,
            transparency._NOTE_TYPE_COSIGNATURE,
            self.witness_public_key,
        )
        self.root_hash_b64 = base64.b64encode(b"r" * 32).decode("ascii")
        self.body = f"{self.LOG_NAME}\n1\n{self.root_hash_b64}\n"
        self.good_checkpoint_note = _signed_note(
            self.body,
            [
                (
                    self.LOG_NAME,
                    bytes.fromhex(self.checkpoint_key_id)
                    + sign(self.LOG_SEED, self.body.encode("utf-8")),
                )
            ],
        )

    def _sigstore_bundle(self, artifact_bytes: bytes) -> dict[str, object]:
        return TestEmitOfflineRekorBundle()._valid_bundle(artifact_bytes)

    def _fixture_parts(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = TestTransparencyVerification()._build_fixture(Path(tmp))
            artifact_bytes = fixture["artifact"].read_bytes()
            trust_root = json.loads(fixture["trust_root"].read_text(encoding="utf-8"))
            bundle_doc = json.loads(fixture["bundle"].read_text(encoding="utf-8"))
            witness_note = fixture["witnessed_checkpoint"].read_text(encoding="utf-8")
        trust = transparency._parse_trust_root(trust_root)
        canonical = transparency._canonicalize_bundle(bundle_doc, artifact_bytes)
        checkpoint_result = transparency._verify_checkpoint_note(
            canonical["checkpoint_note"],
            trust["logs"],
            expected_log_id=canonical["log_id"],
        )
        return witness_note, trust, canonical, checkpoint_result["checkpoint"]

    def test_verify_inclusion_proof_branches(self):
        leaves = [b"a", b"b"]
        root_two = _tree_hash(leaves)
        self.assertTrue(
            transparency.verify_inclusion_proof(
                _leaf_hash(leaves[0]),
                0,
                2,
                [_leaf_hash(leaves[1])],
                root_two,
            )
        )

        three_leaf_root = _tree_hash([b"a", b"b", b"c"])
        left_subtree = _tree_hash([b"a", b"b"])
        self.assertTrue(
            transparency.verify_inclusion_proof(
                _leaf_hash(b"c"),
                2,
                3,
                [left_subtree],
                three_leaf_root,
            )
        )

        self.assertFalse(
            transparency.verify_inclusion_proof(
                _leaf_hash(b"a"), -1, 1, [], _leaf_hash(b"a")
            )
        )
        self.assertFalse(
            transparency.verify_inclusion_proof(
                _leaf_hash(leaves[0]), 0, 2, [], root_two
            )
        )
        self.assertFalse(
            transparency.verify_inclusion_proof(
                _leaf_hash(leaves[0]),
                0,
                2,
                [_leaf_hash(leaves[1]), b"x" * 32],
                root_two,
            )
        )

    def test_verify_consistency_proof_branches(self):
        leaves = [b"a", b"b", b"c", b"d"]
        old_root = _tree_hash(leaves[:2])
        new_root = _tree_hash(leaves)
        proof = _consistency_proof(leaves, 2)
        self.assertTrue(verify_consistency_proof(2, 4, old_root, new_root, proof))
        self.assertFalse(verify_consistency_proof(0, 4, old_root, new_root, proof))
        self.assertFalse(verify_consistency_proof(4, 3, old_root, new_root, proof))
        self.assertTrue(verify_consistency_proof(4, 4, new_root, new_root, []))
        self.assertFalse(verify_consistency_proof(4, 4, new_root, old_root, []))
        self.assertFalse(
            verify_consistency_proof(
                2, 3, _tree_hash(leaves[:2]), _tree_hash(leaves[:3]), []
            )
        )
        fn_not_zero_leaves = [b"a", b"b", b"c", b"d", b"e"]
        fn_not_zero_old_root = _tree_hash(fn_not_zero_leaves[:3])
        fn_not_zero_new_root = _tree_hash(fn_not_zero_leaves)
        fn_not_zero_proof = _consistency_proof(fn_not_zero_leaves, 3)
        self.assertFalse(
            verify_consistency_proof(
                3,
                5,
                fn_not_zero_old_root,
                fn_not_zero_new_root,
                fn_not_zero_proof,
            )
        )
        inner_loop_leaves = [b"a", b"b", b"c", b"d", b"e", b"f"]
        inner_loop_proof = _consistency_proof(inner_loop_leaves, 5)
        self.assertFalse(
            verify_consistency_proof(
                5,
                6,
                _tree_hash(inner_loop_leaves[:5]),
                _tree_hash(inner_loop_leaves),
                inner_loop_proof + [b"x" * 32],
            )
        )
        self.assertFalse(
            verify_consistency_proof(2, 4, old_root, new_root, proof + [b"x" * 32])
        )

    def test_parse_trust_root_and_policy_helpers(self):
        document = {
            "logs": [
                {
                    "name": self.LOG_NAME,
                    "public_key_b64": base64.b64encode(self.log_public_key).decode(
                        "ascii"
                    ),
                }
            ],
            "witnesses": [
                {
                    "name": self.WITNESS_NAME,
                    "public_key_b64": base64.b64encode(self.witness_public_key).decode(
                        "ascii"
                    ),
                }
            ],
            "policy": {"require_witnesses": {"release": "1-of-1"}},
        }

        parsed = transparency._parse_trust_root(document)
        self.assertEqual(
            parsed["logs"][0]["checkpoint_key_id"],
            transparency._note_key_id(
                self.LOG_NAME,
                transparency._NOTE_TYPE_ED25519,
                self.log_public_key,
            ),
        )
        self.assertEqual(
            parsed["witnesses"][0]["key_id"],
            transparency._note_key_id(
                self.WITNESS_NAME,
                transparency._NOTE_TYPE_COSIGNATURE,
                self.witness_public_key,
            ),
        )
        self.assertEqual(
            transparency._resolve_witness_policy(document, "release"),
            "1-of-1",
        )
        self.assertEqual(transparency._resolve_witness_policy({}, None), "0-of-0")
        self.assertEqual(len(transparency._note_key_id("name", 1, b"k" * 32)), 8)

        with self.assertRaisesRegex(ValueError, "unknown witness policy"):
            transparency._resolve_witness_policy(
                {"policy": {"require_witnesses": {}}},
                "release",
            )

        with self.assertRaisesRegex(ValueError, "witness policy"):
            transparency._resolve_witness_policy(
                {"policy": {"require_witnesses": {"default": "bad"}}},
                None,
            )

        with self.assertRaisesRegex(
            ValueError, "default witness policy must be a string"
        ):
            transparency._resolve_witness_policy(
                {"policy": {"require_witnesses": {"default": 1}}},
                None,
            )

    def test_parse_signed_note_rejects_malformed_inputs(self):
        too_many_lines = _signed_note(
            "body\n",
            [("name", b"abcd") for _ in range(transparency._MAX_SIGNATURES + 1)],
        )
        cases = [
            (None, "signed note must be text"),
            ("bad\x00\n", "signed note contains control characters"),
            ("body", "signed note must end with a newline"),
            (
                "body\n— name AAAA\n",
                "signed note is missing the separator before signatures",
            ),
            ("body\n\n", "signed note must contain at least one signature line"),
            (too_many_lines, "signed note has too many signatures"),
            (
                "body\n\nnot-a-signature\n",
                "signed note contains a malformed signature line",
            ),
            ("body\n\n— onlyname\n", "signed note contains a malformed signature line"),
            ("body\n\n— bad+name AAAA\n", "signed note contains an invalid key name"),
            ("body\n\n— name !!!\n", "signed note contains invalid base64"),
            (
                "body\n\n— name YWJj\n",
                "signed note signature payload is too short",
            ),
        ]
        for note_text, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    transparency._parse_signed_note(note_text)

        parsed = transparency._parse_signed_note(
            _signed_note("body\n", [("name", bytes.fromhex("deadbeef") + b"x")])
        )
        self.assertEqual(parsed["signatures"][0]["signature_type"], -1)

    def test_parse_signed_note_normalizes_windows_newlines(self):
        note_text = _signed_note(
            "body\n",
            [("name", bytes.fromhex("deadbeef") + b"x")],
        ).replace("\n", "\r\n")
        parsed = transparency._parse_signed_note(note_text)
        self.assertEqual(parsed["body"], "body\n")
        self.assertEqual(parsed["body_bytes"], b"body\n")

    def test_parse_checkpoint_body_rejects_malformed_inputs(self):
        root_hash = base64.b64encode(b"r" * 32).decode("ascii")
        cases = [
            ("body", "checkpoint body must end with a newline"),
            (
                "origin\n1\n",
                "checkpoint body must contain origin, tree size, and root hash",
            ),
            (f"\n1\n{root_hash}\n", "checkpoint origin must be non-empty"),
            (
                f"origin\n01\n{root_hash}\n",
                "checkpoint tree size must be decimal with no leading zeroes",
            ),
            (
                f"origin\n1\n{root_hash}\next\n\n",
                "checkpoint extension lines must be non-empty",
            ),
        ]
        for body, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    transparency._parse_checkpoint_body(body)

    def test_read_and_json_helpers_cover_error_paths(self):
        with self.assertRaisesRegex(FileNotFoundError, "Artifact not found"):
            transparency._read_bytes("/definitely/missing", "Artifact")

        with (
            patch.object(transparency.Path, "exists", return_value=True),
            patch.object(transparency.Path, "is_symlink", return_value=True),
        ):
            with self.assertRaisesRegex(ValueError, "is a symlink"):
                transparency._read_bytes("ignored", "Artifact")

        with (
            patch.object(transparency.Path, "exists", return_value=True),
            patch.object(transparency.Path, "is_symlink", return_value=False),
            patch.object(transparency.Path, "stat", side_effect=OSError("boom")),
        ):
            with self.assertRaisesRegex(ValueError, "Cannot stat artifact"):
                transparency._read_bytes("ignored", "Artifact")

        stat_small = type("Stat", (), {"st_size": 1})()
        with (
            patch.object(transparency.Path, "exists", return_value=True),
            patch.object(transparency.Path, "is_symlink", return_value=False),
            patch.object(
                transparency.Path,
                "stat",
                return_value=type(
                    "Stat", (), {"st_size": transparency.MAX_RECEIPT_FILE_SIZE + 1}
                )(),
            ),
        ):
            with self.assertRaisesRegex(ValueError, "is too large"):
                transparency._read_bytes("ignored", "Artifact")

        with (
            patch.object(transparency.Path, "exists", return_value=True),
            patch.object(transparency.Path, "is_symlink", return_value=False),
            patch.object(transparency.Path, "stat", return_value=stat_small),
            patch.object(transparency.Path, "read_bytes", side_effect=OSError("boom")),
        ):
            with self.assertRaisesRegex(ValueError, "Cannot read artifact"):
                transparency._read_bytes("ignored", "Artifact")

        with patch.object(transparency, "_read_bytes", return_value=b"\xff"):
            with self.assertRaisesRegex(ValueError, "not valid UTF-8"):
                transparency._read_text("ignored", "Artifact")

        with patch.object(transparency, "_read_text", return_value="{"):
            with self.assertRaisesRegex(ValueError, "not valid JSON"):
                transparency._load_json("ignored", "Trust root")

        with patch.object(transparency, "_read_text", return_value="[]"):
            with self.assertRaisesRegex(ValueError, "must be a JSON object"):
                transparency._load_json("ignored", "Trust root")

        self.assertIsNone(transparency._parse_consistency_proof(None))
        with self.assertRaisesRegex(ValueError, "must be an object"):
            transparency._parse_consistency_proof([])

    def test_numeric_and_decode_helpers_cover_error_paths(self):
        with self.assertRaisesRegex(ValueError, "boolean values"):
            transparency._parse_uint(True)
        with self.assertRaisesRegex(ValueError, "must be non-negative"):
            transparency._parse_uint(-1)
        with self.assertRaisesRegex(
            ValueError, "non-negative integer or decimal string"
        ):
            transparency._parse_uint("bad")

        self.assertFalse(transparency._is_uint_value("bad"))

        for value, label, message in [
            (None, "hash", "must be a non-empty base64 string"),
            ("@@@", "hash", "must be valid base64"),
            (
                base64.b64encode(b"short").decode("ascii"),
                "hash",
                "must decode to 32 bytes",
            ),
        ]:
            with self.subTest(label=label, value=value):
                with self.assertRaisesRegex(ValueError, message):
                    transparency._decode_hash_b64(value, label)

        for value, label, message in [
            (None, "logs", "must be a non-empty base64 string"),
            ("@@@", "logs", "must be valid base64"),
            (
                base64.b64encode(b"short").decode("ascii"),
                "logs",
                "must decode to 32 bytes",
            ),
        ]:
            with self.subTest(label=label, value=value):
                with self.assertRaisesRegex(ValueError, message):
                    transparency._decode_public_key(value, label)

        logs = [
            {"name": "other", "log_id": "wrong"},
            {"name": self.LOG_NAME, "log_id": "other"},
            {"name": self.LOG_NAME, "log_id": self.LOG_ID},
        ]
        self.assertIsNone(transparency._select_log("missing", logs, None))
        self.assertEqual(
            transparency._select_log(self.LOG_NAME, logs, self.LOG_ID),
            logs[2],
        )
        self.assertIsNone(
            transparency._select_log(self.LOG_NAME, logs[:2], self.LOG_ID)
        )

        self.assertIsNone(transparency._format_timestamp(object()))
        self.assertIsNone(transparency._format_timestamp(10**40))

    def test_parse_sigstore_bundle_success_and_errors(self):
        artifact_bytes = b"artifact-bytes"
        bundle = self._sigstore_bundle(artifact_bytes)
        parsed = transparency._parse_sigstore_bundle(bundle, artifact_bytes)
        self.assertEqual(parsed["schema"], "sigstore.bundle.v0.3")
        self.assertEqual(parsed["log_id"], "rekor-key")
        self.assertEqual(parsed["tree_size"], 456)

        def deep_clone(value):
            return json.loads(json.dumps(value))

        def mutate_missing_message_signature(doc):
            doc.pop("messageSignature")

        def mutate_missing_message_digest(doc):
            doc["messageSignature"]["messageDigest"] = []

        def mutate_bad_algorithm(doc):
            doc["messageSignature"]["messageDigest"]["algorithm"] = "SHA1"

        def mutate_non_string_digest(doc):
            doc["messageSignature"]["messageDigest"]["digest"] = 1

        def mutate_bad_digest(doc):
            doc["messageSignature"]["messageDigest"]["digest"] = base64.b64encode(
                b"x" * 32
            ).decode("ascii")

        def mutate_missing_verification_material(doc):
            doc["verificationMaterial"] = []

        def mutate_missing_tlog_entries(doc):
            doc["verificationMaterial"]["tlogEntries"] = []

        def mutate_non_object_entry(doc):
            doc["verificationMaterial"]["tlogEntries"][0] = "bad"

        def mutate_missing_body(doc):
            doc["verificationMaterial"]["tlogEntries"][0]["canonicalizedBody"] = ""

        def mutate_bad_body_base64(doc):
            doc["verificationMaterial"]["tlogEntries"][0]["canonicalizedBody"] = "@@@"

        def mutate_bad_body_json(doc):
            doc["verificationMaterial"]["tlogEntries"][0]["canonicalizedBody"] = (
                base64.b64encode(b"not-json").decode("ascii")
            )

        def mutate_bad_rekor_hash_algorithm(doc):
            body = json.loads(
                base64.b64decode(
                    doc["verificationMaterial"]["tlogEntries"][0]["canonicalizedBody"],
                    validate=True,
                ).decode("utf-8")
            )
            body["spec"]["data"]["hash"]["algorithm"] = "sha512"
            doc["verificationMaterial"]["tlogEntries"][0]["canonicalizedBody"] = (
                base64.b64encode(
                    json.dumps(body, separators=(",", ":")).encode("utf-8")
                ).decode("ascii")
            )

        def mutate_bad_rekor_hash_value(doc):
            body = json.loads(
                base64.b64decode(
                    doc["verificationMaterial"]["tlogEntries"][0]["canonicalizedBody"],
                    validate=True,
                ).decode("utf-8")
            )
            body["spec"]["data"]["hash"]["value"] = "0" * 64
            doc["verificationMaterial"]["tlogEntries"][0]["canonicalizedBody"] = (
                base64.b64encode(
                    json.dumps(body, separators=(",", ":")).encode("utf-8")
                ).decode("ascii")
            )

        def mutate_missing_inclusion(doc):
            doc["verificationMaterial"]["tlogEntries"][0]["inclusionProof"] = []

        def mutate_missing_checkpoint_envelope(doc):
            doc["verificationMaterial"]["tlogEntries"][0]["inclusionProof"][
                "checkpoint"
            ] = {}

        cases = [
            (mutate_missing_message_signature, "missing messageSignature"),
            (mutate_missing_message_digest, "missing messageDigest"),
            (mutate_bad_algorithm, "must use SHA2_256"),
            (mutate_non_string_digest, "digest must be a string"),
            (mutate_bad_digest, "digest does not match the artifact"),
            (mutate_missing_verification_material, "missing verificationMaterial"),
            (mutate_missing_tlog_entries, "missing Rekor tlog entries"),
            (mutate_non_object_entry, "tlog entry is not an object"),
            (mutate_missing_body, "missing canonicalizedBody"),
            (mutate_bad_body_base64, "canonicalizedBody is invalid"),
            (mutate_bad_body_json, "canonicalizedBody is invalid JSON"),
            (mutate_bad_rekor_hash_algorithm, "must use sha256"),
            (
                mutate_bad_rekor_hash_value,
                "Rekor body hash does not match the artifact",
            ),
            (mutate_missing_inclusion, "missing inclusionProof"),
            (mutate_missing_checkpoint_envelope, "missing checkpoint.envelope"),
        ]
        for mutator, message in cases:
            with self.subTest(message=message):
                broken = deep_clone(bundle)
                mutator(broken)
                with self.assertRaisesRegex(ValueError, message):
                    transparency._parse_sigstore_bundle(broken, artifact_bytes)

    def test_verify_checkpoint_note_branch_coverage(self):
        trusted_log = {
            "name": self.LOG_NAME,
            "checkpoint_key_id": self.checkpoint_key_id,
            "public_key": self.log_public_key,
            "log_id": self.LOG_ID,
        }

        no_trusted_log = transparency._verify_checkpoint_note(
            self.good_checkpoint_note,
            [],
            expected_log_id=self.LOG_ID,
        )
        self.assertFalse(no_trusted_log["valid"])
        self.assertIn(
            "no trusted log matches checkpoint origin", no_trusted_log["errors"][0]
        )

        wrong_note = _signed_note(
            self.body,
            [
                (
                    "other.log",
                    bytes.fromhex(self.checkpoint_key_id)
                    + sign(self.LOG_SEED, self.body.encode("utf-8")),
                ),
                (
                    self.LOG_NAME,
                    bytes.fromhex("00000000")
                    + sign(self.LOG_SEED, self.body.encode("utf-8")),
                ),
                (
                    self.LOG_NAME,
                    bytes.fromhex(self.checkpoint_key_id) + b"x" * 72,
                ),
            ],
        )
        wrong_result = transparency._verify_checkpoint_note(
            wrong_note,
            [trusted_log],
            expected_log_id=self.LOG_ID,
        )
        self.assertFalse(wrong_result["valid"])
        self.assertIn(
            "checkpoint used an unexpected signature type", wrong_result["errors"]
        )
        self.assertIn(
            "no trusted checkpoint signature verified", wrong_result["errors"]
        )

        with patch.object(transparency, "_ed25519_verify", return_value=False):
            verify_fail = transparency._verify_checkpoint_note(
                self.good_checkpoint_note,
                [trusted_log],
                expected_log_id=self.LOG_ID,
            )
        self.assertFalse(verify_fail["valid"])
        self.assertIn("checkpoint signature did not verify", verify_fail["errors"])

        checkpoint = transparency._parse_checkpoint_body(self.body)
        checkpoint["log_id"] = "bundle-log"
        with (
            patch.object(
                transparency, "_parse_checkpoint_body", return_value=checkpoint
            ),
            patch.object(
                transparency,
                "_select_log",
                return_value={**trusted_log, "log_id": "trusted-log"},
            ),
        ):
            mismatch = transparency._verify_checkpoint_note(
                self.good_checkpoint_note,
                [trusted_log],
                expected_log_id=self.LOG_ID,
            )
        self.assertFalse(mismatch["valid"])
        self.assertIn(
            "checkpoint log_id did not match the trusted log", mismatch["errors"]
        )

        with (
            patch.object(
                transparency, "_parse_checkpoint_body", return_value=checkpoint
            ),
            patch.object(transparency, "_select_log", return_value=trusted_log),
        ):
            matching = transparency._verify_checkpoint_note(
                self.good_checkpoint_note,
                [trusted_log],
                expected_log_id=self.LOG_ID,
            )
        self.assertTrue(matching["valid"])

    def test_verify_witnessed_checkpoint_branch_coverage(self):
        witness_note_text, trust, canonical, inclusion_checkpoint = (
            self._fixture_parts()
        )

        no_inclusion_checkpoint = transparency._verify_witnessed_checkpoint(
            witness_note_text,
            trust,
            None,
            canonical["consistency_proof"],
            required_witnesses=1,
            total_witnesses=1,
        )
        self.assertTrue(no_inclusion_checkpoint["valid"], no_inclusion_checkpoint)
        self.assertIsNone(no_inclusion_checkpoint["body_match"])

        missing_consistency = transparency._verify_witnessed_checkpoint(
            witness_note_text,
            trust,
            inclusion_checkpoint,
            None,
            required_witnesses=1,
            total_witnesses=1,
        )
        self.assertFalse(missing_consistency["valid"])
        self.assertIn(
            "consistency proof is required when the witnessed checkpoint differs",
            missing_consistency["errors"],
        )

        with patch.object(transparency, "verify_consistency_proof", return_value=False):
            inconsistent = transparency._verify_witnessed_checkpoint(
                witness_note_text,
                trust,
                inclusion_checkpoint,
                canonical["consistency_proof"],
                required_witnesses=1,
                total_witnesses=1,
            )
        self.assertFalse(inconsistent["valid"])
        self.assertIn(
            "consistency proof did not connect the bundled checkpoint to the witnessed checkpoint",
            inconsistent["errors"],
        )

        checkpoint_note = transparency._parse_signed_note(canonical["checkpoint_note"])
        log_signature = checkpoint_note["signatures"][0]
        current_time = 1_700_000_000
        future_time = current_time + 10_000
        wrong_type_signature = sign(self.WITNESS_SEED, checkpoint_note["body_bytes"])
        future_message = (
            b"cosignature/v1\n"
            + f"time {future_time}\n".encode("ascii")
            + checkpoint_note["body_bytes"]
        )
        future_signature = future_time.to_bytes(8, "big") + sign(
            self.WITNESS_SEED,
            future_message,
        )
        bad_message = (
            b"cosignature/v1\n"
            + f"time {current_time}\n".encode("ascii")
            + checkpoint_note["body_bytes"]
        )
        bad_signature = current_time.to_bytes(8, "big") + sign(
            bytes([9]) * 32,
            bad_message,
        )
        synthetic_note = _signed_note(
            checkpoint_note["body"],
            [
                (
                    self.LOG_NAME,
                    bytes.fromhex(log_signature["key_id_hex"])
                    + log_signature["signature_bytes"],
                ),
                (
                    self.WITNESS_NAME,
                    bytes.fromhex(self.witness_key_id) + wrong_type_signature,
                ),
                (
                    self.WITNESS_NAME,
                    bytes.fromhex(self.witness_key_id) + future_signature,
                ),
                (
                    self.WITNESS_NAME,
                    bytes.fromhex(self.witness_key_id) + bad_signature,
                ),
            ],
        )
        matching_inclusion_checkpoint = transparency._parse_checkpoint_body(
            checkpoint_note["body"]
        )
        with patch("time.time", return_value=current_time):
            witness_errors = transparency._verify_witnessed_checkpoint(
                synthetic_note,
                trust,
                matching_inclusion_checkpoint,
                canonical["consistency_proof"],
                required_witnesses=1,
                total_witnesses=2,
            )
        self.assertFalse(witness_errors["valid"])
        self.assertTrue(witness_errors["body_match"])
        self.assertTrue(witness_errors["consistency_proof_verified"])
        self.assertIn(
            f"witness {self.WITNESS_NAME} used the wrong signature type",
            witness_errors["errors"],
        )
        self.assertIn(
            f"witness {self.WITNESS_NAME} timestamp is too far in the future",
            witness_errors["errors"],
        )
        self.assertIn(
            f"witness {self.WITNESS_NAME} signature did not verify",
            witness_errors["errors"],
        )
        self.assertIn(
            "trust root does not define enough witnesses for the requested policy",
            witness_errors["errors"],
        )
        self.assertIn("witness policy was not satisfied", witness_errors["errors"])


class TestTransparencyMaterialFailurePaths(unittest.TestCase):
    def _build_fixture(self, root: Path) -> dict[str, Path]:
        return TestTransparencyVerification()._build_fixture(root)

    def test_verify_transparency_material_rejects_missing_inputs(self):
        result = verify_transparency_material("/missing", "/bundle", "/trust")
        self.assertFalse(result["valid"])
        self.assertIn("Artifact not found", result["error"])

    def test_verify_transparency_material_rejects_invalid_trust_root_and_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self._build_fixture(Path(tmp))
            fixture["trust_root"].write_text("[]", encoding="utf-8")
            result = verify_transparency_material(
                str(fixture["artifact"]),
                str(fixture["bundle"]),
                str(fixture["trust_root"]),
            )
            self.assertFalse(result["valid"])
            self.assertIn("Trust root must be a JSON object", result["error"])

            fixture["trust_root"].write_text(
                json.dumps(
                    {
                        "schema": "aiir.trust.v1",
                        "logs": [],
                        "witnesses": [],
                        "policy": {"require_witnesses": {"default": "0-of-0"}},
                    }
                ),
                encoding="utf-8",
            )
            fixture["bundle"].write_text(
                json.dumps({"schema": "bad"}), encoding="utf-8"
            )
            result = verify_transparency_material(
                str(fixture["artifact"]),
                str(fixture["bundle"]),
                str(fixture["trust_root"]),
            )
        self.assertFalse(result["valid"])
        self.assertIn("schema must be 'aiir.rekor.bundle.v1'", result["error"])

    def test_verify_transparency_material_returns_trust_root_validation_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self._build_fixture(Path(tmp))
            fixture["trust_root"].write_text(
                json.dumps({"schema": "bad", "logs": []}), encoding="utf-8"
            )
            result = verify_transparency_material(
                str(fixture["artifact"]),
                str(fixture["bundle"]),
                str(fixture["trust_root"]),
            )
        self.assertFalse(result["valid"])
        self.assertIn("schema must be 'aiir.trust.v1'", result["error"])

    def test_verify_transparency_material_handles_missing_witnessed_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self._build_fixture(Path(tmp))
            missing = Path(tmp) / "missing-witness.txt"
            result = verify_transparency_material(
                str(fixture["artifact"]),
                str(fixture["bundle"]),
                str(fixture["trust_root"]),
                witnessed_checkpoint_path=str(missing),
                require_witnesses="release",
            )
        self.assertFalse(result["valid"])
        self.assertIn("Witnessed checkpoint not found", result["error"])

    def test_verify_transparency_material_reports_hash_and_proof_mismatches(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self._build_fixture(Path(tmp))
            bundle = json.loads(fixture["bundle"].read_text(encoding="utf-8"))
            bundle["artifact_sha256"] = "sha256:" + "0" * 64
            bundle["body_hash"] = "sha256:" + "1" * 64
            bundle["inclusion_proof"]["root_hash"] = base64.b64encode(b"z" * 32).decode(
                "ascii"
            )
            bundle["inclusion_proof"]["tree_size"] = 2
            fixture["bundle"].write_text(json.dumps(bundle), encoding="utf-8")
            result = verify_transparency_material(
                str(fixture["artifact"]),
                str(fixture["bundle"]),
                str(fixture["trust_root"]),
            )
        self.assertFalse(result["valid"])
        self.assertIn("artifact hash does not match Rekor bundle", result["errors"])
        self.assertIn("body_hash does not match body_b64", result["errors"])
        self.assertIn(
            "inclusion proof root hash does not match the signed checkpoint",
            result["errors"],
        )
        self.assertIn(
            "inclusion proof tree size does not match the signed checkpoint",
            result["errors"],
        )
        self.assertIn(
            "inclusion proof did not reconstruct the checkpoint root hash",
            result["errors"],
        )

    def test_verify_transparency_material_allows_missing_body_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self._build_fixture(Path(tmp))
            bundle = json.loads(fixture["bundle"].read_text(encoding="utf-8"))
            bundle.pop("body_hash")
            fixture["bundle"].write_text(json.dumps(bundle), encoding="utf-8")
            result = verify_transparency_material(
                str(fixture["artifact"]),
                str(fixture["bundle"]),
                str(fixture["trust_root"]),
            )
        self.assertTrue(result["valid"], result)
        self.assertTrue(result["body_hash_match"])

    def test_verify_transparency_material_handles_invalid_checkpoint_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self._build_fixture(Path(tmp))
            fixture["trust_root"].write_text(
                json.dumps(
                    {
                        "schema": "aiir.trust.v1",
                        "logs": [],
                        "witnesses": [],
                        "policy": {"require_witnesses": {"default": "0-of-0"}},
                    }
                ),
                encoding="utf-8",
            )
            result = verify_transparency_material(
                str(fixture["artifact"]),
                str(fixture["bundle"]),
                str(fixture["trust_root"]),
            )
        self.assertFalse(result["valid"])
        self.assertIn("no trusted log matches checkpoint origin", result["error"])


class TestArtifactCliCoverage(unittest.TestCase):
    def test_artifact_mode_rejects_verify_with_artifact(self):
        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            code = cli.main(
                [
                    "--artifact",
                    "artifact.bin",
                    "--verify",
                    "receipt.json",
                ]
            )
        self.assertEqual(code, 1)
        self.assertIn("Choose only one of --verify or --artifact", stderr.getvalue())

    def test_artifact_mode_requires_trust_root(self):
        stderr = io.StringIO()
        with (
            patch("sys.stderr", stderr),
            patch("sys.stdout", io.StringIO()),
        ):
            code = cli.main(
                [
                    "--artifact",
                    "artifact.bin",
                    "--rekor-bundle",
                    "bundle.json",
                ]
            )
        self.assertEqual(code, 1)
        self.assertIn("Artifact verification requires --trust-root", stderr.getvalue())

    def test_artifact_mode_success_without_optional_detail_lines(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(
                cli,
                "verify_transparency_material",
                return_value={
                    "valid": True,
                    "artifact_sha256": "sha256:" + "a" * 64,
                    "artifact_hash_match": True,
                    "rekor_bundle": {
                        "log_index": None,
                        "integrated_time_rfc3339": None,
                    },
                    "witnessed_checkpoint": {
                        "verified_witnesses": [],
                        "required": "0-of-0",
                    },
                },
            ),
            patch("sys.stdout", stdout),
            patch("sys.stderr", stderr),
        ):
            code = cli.main(
                [
                    "--artifact",
                    "artifact.bin",
                    "--rekor-bundle",
                    "bundle.json",
                    "--trust-root",
                    "trust-root.json",
                ]
            )
        self.assertEqual(code, 0)
        self.assertNotIn("Rekor:", stderr.getvalue())
        self.assertNotIn("Witnesses:", stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["valid"])
        self.assertTrue(payload["artifact_hash_match"])
        self.assertEqual(payload["verified_witness_count"], 0)

    def test_artifact_mode_success_skips_non_dict_optional_sections(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(
                cli,
                "verify_transparency_material",
                return_value={
                    "valid": True,
                    "artifact_sha256": "sha256:" + "a" * 64,
                    "rekor_bundle": [],
                    "witnessed_checkpoint": [],
                },
            ),
            patch("sys.stdout", stdout),
            patch("sys.stderr", stderr),
        ):
            code = cli.main(
                [
                    "--artifact",
                    "artifact.bin",
                    "--rekor-bundle",
                    "bundle.json",
                    "--trust-root",
                    "trust-root.json",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["verified_witness_count"], 0)

    def test_artifact_mode_failure_prints_extra_errors(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(
                cli,
                "verify_transparency_material",
                return_value={
                    "valid": False,
                    "error": "primary failure",
                    "errors": ["primary failure", "secondary detail"],
                },
            ),
            patch("sys.stdout", stdout),
            patch("sys.stderr", stderr),
        ):
            code = cli.main(
                [
                    "--artifact",
                    "artifact.bin",
                    "--rekor-bundle",
                    "bundle.json",
                    "--trust-root",
                    "trust-root.json",
                ]
            )
        self.assertEqual(code, 1)
        self.assertIn("Artifact transparency verification failed.", stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["valid"])
        self.assertEqual(payload["error_count"], 2)

    def test_artifact_mode_failure_without_error_list_counts_single_error(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(
                cli,
                "verify_transparency_material",
                return_value={
                    "valid": False,
                    "error": "primary failure",
                },
            ),
            patch("sys.stdout", stdout),
            patch("sys.stderr", stderr),
        ):
            code = cli.main(
                [
                    "--artifact",
                    "artifact.bin",
                    "--rekor-bundle",
                    "bundle.json",
                    "--trust-root",
                    "trust-root.json",
                ]
            )
        self.assertEqual(code, 1)
        self.assertIn("Artifact transparency verification failed.", stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["valid"])
        self.assertEqual(payload["error_count"], 1)


class TestCanonicalizeBundleDispatch(unittest.TestCase):
    def test_canonicalize_bundle_dispatches_sigstore_media_type(self):
        artifact_bytes = b"artifact-bytes"
        bundle = TestEmitOfflineRekorBundle()._valid_bundle(artifact_bytes)
        sentinel = {"schema": "sigstore.bundle.v0.3"}
        with patch.object(
            transparency, "_parse_sigstore_bundle", return_value=sentinel
        ) as parse_bundle:
            result = transparency._canonicalize_bundle(bundle, artifact_bytes)
        self.assertEqual(result, sentinel)
        parse_bundle.assert_called_once_with(bundle, artifact_bytes)


if __name__ == "__main__":
    unittest.main()
