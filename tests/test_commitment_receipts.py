"""Tests for generic AIIR commitment receipts."""
# Copyright 2025-2026 Invariant Systems, Inc.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aiir.cli as cli
from aiir import _commitment as commitment


class TestCommitmentReceipts(unittest.TestCase):
    """Direct tests for the commitment receipt profile."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="aiir-commitment-")
        self.root = Path(self.tmpdir)
        self.plan = self.root / "plan.json"
        self.plan.write_text('{"status":"ready"}\n', encoding="utf-8")
        self.bundle = self.root / "bundle"
        (self.bundle / "nested").mkdir(parents=True)
        (self.bundle / "manifest.txt").write_text("alpha\n", encoding="utf-8")
        (self.bundle / "nested" / "data.txt").write_text("beta\n", encoding="utf-8")
        (self.bundle / "empty").mkdir()
        self.digest = (
            "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _build_receipt(self):
        file_artifact = commitment.build_commitment_path_artifact(
            str(self.plan), cwd=self.tmpdir
        )
        dir_artifact = commitment.build_commitment_path_artifact(
            str(self.bundle), cwd=self.tmpdir
        )
        digest_artifact = commitment.parse_commitment_digest_spec(
            f"packet={self.digest.upper()}"
        )
        with patch(
            "aiir._commitment._run_git",
            return_value="https://token@example.com/invariant-systems-ai/aiir.git\n",
        ):
            return commitment.build_commitment_receipt(
                subject_name="nisq-eval-plan",
                summary="Declared evaluation plan before rerun",
                artifacts=[file_artifact, dir_artifact, digest_artifact],
                cwd=self.tmpdir,
                namespace="public-proof",
            )

    def test_parse_digest_and_basic_detectors(self):
        artifact = commitment.parse_commitment_digest_spec(
            f"packet={self.digest.upper()}"
        )
        self.assertEqual(artifact["type"], "digest")
        self.assertEqual(artifact["digest"], self.digest)
        self.assertFalse(commitment.is_commitment_receipt({"type": "other"}))
        with self.assertRaises(ValueError):
            commitment.parse_commitment_digest_spec("broken")

    def test_path_artifacts_cover_relative_and_absolute_refs(self):
        relative = commitment.build_commitment_path_artifact(
            "plan.json", cwd=self.tmpdir
        )
        self.assertEqual(relative["ref"], "plan.json")
        external_dir = tempfile.mkdtemp(prefix="aiir-commitment-external-")
        try:
            external = Path(external_dir) / "outside.txt"
            external.write_text("outside\n", encoding="utf-8")
            absolute = commitment.build_commitment_path_artifact(
                str(external), cwd=self.tmpdir
            )
            self.assertEqual(absolute["ref"], external.resolve().as_posix())
        finally:
            shutil.rmtree(external_dir, ignore_errors=True)

    def test_path_artifact_rejects_empty_missing_symlink_and_fifo(self):
        with self.assertRaises(ValueError):
            commitment.build_commitment_path_artifact("   ", cwd=self.tmpdir)
        with self.assertRaises(ValueError):
            commitment.build_commitment_path_artifact("missing.json", cwd=self.tmpdir)

        symlink = self.root / "plan-link.json"
        symlink.symlink_to(self.plan)
        with self.assertRaises(ValueError):
            commitment.build_commitment_path_artifact(str(symlink), cwd=self.tmpdir)

        if hasattr(os, "mkfifo"):
            top_fifo = self.root / "top-pipe"
            os.mkfifo(top_fifo)
            with self.assertRaises(ValueError):
                commitment.build_commitment_path_artifact(
                    str(top_fifo), cwd=self.tmpdir
                )
            top_fifo.unlink()

        if hasattr(os, "mkfifo"):
            fifo_path = self.bundle / "pipe"
            os.mkfifo(fifo_path)
            with self.assertRaises(ValueError):
                commitment.build_commitment_path_artifact(
                    str(self.bundle), cwd=self.tmpdir
                )
            fifo_path.unlink()

        bundle_link = self.bundle / "nested-link"
        bundle_link.symlink_to(self.plan)
        with self.assertRaises(ValueError):
            commitment.build_commitment_path_artifact(str(self.bundle), cwd=self.tmpdir)

    def test_build_verify_format_and_intoto_round_trip(self):
        receipt = self._build_receipt()
        self.assertTrue(commitment.is_commitment_receipt(receipt))
        self.assertEqual(receipt["extensions"]["namespace"], "public-proof")
        self.assertEqual(
            receipt["provenance"]["repository"],
            "https://example.com/invariant-systems-ai/aiir.git",
        )
        self.assertEqual(receipt["artifacts"][2]["digest"], self.digest)
        self.assertEqual(receipt["artifacts"][1]["file_count"], 2)

        result = commitment.verify_commitment_receipt(receipt)
        self.assertTrue(result["valid"])
        self.assertEqual(result["artifact_count"], 3)
        self.assertEqual(result["subject_name"], "nisq-eval-plan")
        self.assertIn("expected_content_hash", result)

        pretty = cli.format_receipt_pretty(receipt)
        detail = cli.format_receipt_detail(receipt)
        self.assertIn("Commitment:", pretty)
        self.assertIn("nisq-eval-plan", pretty)
        self.assertIn("artifact(s)", detail)

        statement = cli.wrap_in_toto_statement(receipt)
        self.assertEqual(
            statement["predicateType"],
            "https://invariantsystems.io/predicates/aiir/commitment_receipt/v1",
        )
        self.assertEqual(statement["subject"][0]["name"], "plan.json")
        self.assertEqual(
            statement["subject"][0]["digest"]["sha256"],
            receipt["artifacts"][0]["digest"].split(":", 1)[1],
        )

        explanation = cli.explain_verification(result)
        self.assertIn("subject, statement, artifacts, provenance", explanation)

    def test_wrap_in_toto_falls_back_when_artifacts_missing(self):
        statement = cli.wrap_in_toto_statement(
            {
                "type": commitment.COMMITMENT_RECEIPT_TYPE,
                "schema": commitment.COMMITMENT_RECEIPT_SCHEMA_VERSION,
                "subject": {"name": "fallback-subject"},
                "content_hash": self.digest,
                "artifacts": [],
            }
        )
        self.assertEqual(statement["subject"][0]["name"], "fallback-subject")
        self.assertEqual(
            statement["subject"][0]["digest"]["sha256"], self.digest.split(":", 1)[1]
        )

    def test_write_verify_file_and_array_with_cbor_sidecar(self):
        receipt = self._build_receipt()
        old_cwd = os.getcwd()
        try:
            os.chdir(self.tmpdir)
            out_dir = self.root / ".receipts"
            path = Path(cli.write_receipt(receipt, output_dir=str(out_dir)))
            self.assertTrue(path.name.startswith("receipt_nisq-eval-plan_"))
            self.assertTrue(path.with_suffix(".cbor").is_file())

            single = cli.verify_receipt_file(str(path))
            self.assertTrue(single["valid"])
            self.assertTrue(single["cbor_sidecar"]["valid"])
            self.assertEqual(single["receipt_type"], "commitment_receipt")

            second = dict(receipt)
            second["timestamp"] = "2026-01-02T00:00:00Z"
            array_path = self.root / "receipt-array.json"
            array_path.write_text(
                json.dumps([receipt, second], indent=2), encoding="utf-8"
            )
            many = cli.verify_receipt_file(str(array_path))
            self.assertTrue(many["valid"])
            self.assertEqual(many["count"], 2)
            self.assertEqual(many["receipts"][0]["subject_name"], "nisq-eval-plan")
        finally:
            os.chdir(old_cwd)

    def test_verify_reports_tamper_and_schema_errors(self):
        receipt = self._build_receipt()
        tampered = json.loads(json.dumps(receipt))
        tampered["statement"]["summary"] = "Changed later"
        tamper_result = commitment.verify_commitment_receipt(tampered)
        self.assertFalse(tamper_result["valid"])
        self.assertIn("content hash mismatch", tamper_result["errors"])
        self.assertIn("receipt_id mismatch", tamper_result["errors"])
        self.assertIn(
            "original files, directories, or", cli.explain_verification(tamper_result)
        )

        invalid = json.loads(json.dumps(receipt))
        invalid["type"] = "aiir.other_receipt"
        invalid["schema"] = "aiir/other_receipt.v1"
        invalid["version"] = "<bad>"
        invalid["artifacts"] = []
        invalid_result = commitment.verify_commitment_receipt(invalid)
        self.assertFalse(invalid_result["valid"])
        self.assertIn("unknown receipt type", invalid_result["errors"][0])
        self.assertTrue(
            any("unknown schema" in err for err in invalid_result["errors"])
        )
        self.assertTrue(
            any("invalid version format" in err for err in invalid_result["errors"])
        )
        self.assertTrue(
            any("non-empty array" in err for err in invalid_result["errors"])
        )

    def test_verify_rejects_bad_directory_member_and_empty_build(self):
        receipt = self._build_receipt()
        invalid_member = json.loads(json.dumps(receipt))
        invalid_member["artifacts"][1]["members"][1]["digest"] = "sha256:bad"
        invalid_result = commitment.verify_commitment_receipt(invalid_member)
        self.assertFalse(invalid_result["valid"])
        self.assertTrue(
            any(
                "invalid directory member digest" in err
                for err in invalid_result["errors"]
            )
        )

        with self.assertRaises(ValueError):
            commitment.build_commitment_receipt(
                subject_name="plan",
                summary="x",
                artifacts=[],
            )
        with self.assertRaises(ValueError):
            commitment.build_commitment_receipt(
                subject_name="   ",
                summary="x",
                artifacts=[
                    commitment.parse_commitment_digest_spec(f"packet={self.digest}")
                ],
            )

    def test_verify_rejects_individual_normalization_failures(self):
        receipt = self._build_receipt()
        cases = [
            ("subject", "bad", "commitment subject must be an object"),
            ("statement", "bad", "commitment statement must be an object"),
            ("provenance", "bad", "commitment provenance must be an object"),
            ("artifacts", ["bad"], "commitment artifact entries must be objects"),
        ]
        for field, value, expected in cases:
            with self.subTest(field=field):
                mutated = json.loads(json.dumps(receipt))
                mutated[field] = value
                result = commitment.verify_commitment_receipt(mutated)
                self.assertFalse(result["valid"])
                self.assertTrue(any(expected in err for err in result["errors"]))

        mutated = json.loads(json.dumps(receipt))
        mutated["artifacts"][0]["type"] = "weird"
        result = commitment.verify_commitment_receipt(mutated)
        self.assertFalse(result["valid"])
        self.assertTrue(
            any(
                "unsupported commitment artifact type" in err
                for err in result["errors"]
            )
        )

        mutated = json.loads(json.dumps(receipt))
        mutated["artifacts"][0]["digest"] = "sha256:bad"
        result = commitment.verify_commitment_receipt(mutated)
        self.assertFalse(result["valid"])
        self.assertTrue(
            any("invalid artifact digest" in err for err in result["errors"])
        )

        mutated = json.loads(json.dumps(receipt))
        mutated["artifacts"][0]["size"] = -1
        result = commitment.verify_commitment_receipt(mutated)
        self.assertFalse(result["valid"])
        self.assertTrue(
            any("file commitment artifacts require" in err for err in result["errors"])
        )

        mutated = json.loads(json.dumps(receipt))
        mutated["artifacts"][1]["entry_count"] = -1
        result = commitment.verify_commitment_receipt(mutated)
        self.assertFalse(result["valid"])
        self.assertTrue(any("entry_count" in err for err in result["errors"]))

        mutated = json.loads(json.dumps(receipt))
        mutated["artifacts"][1]["entry_count"] = 3
        mutated["artifacts"][1]["file_count"] = -1
        result = commitment.verify_commitment_receipt(mutated)
        self.assertFalse(result["valid"])
        self.assertTrue(any("file_count" in err for err in result["errors"]))

        mutated = json.loads(json.dumps(receipt))
        mutated["artifacts"][1]["members"] = "bad"
        result = commitment.verify_commitment_receipt(mutated)
        self.assertFalse(result["valid"])
        self.assertTrue(any("members array" in err for err in result["errors"]))

        mutated = json.loads(json.dumps(receipt))
        mutated["artifacts"][1]["members"] = ["bad"]
        result = commitment.verify_commitment_receipt(mutated)
        self.assertFalse(result["valid"])
        self.assertTrue(
            any("directory members must be objects" in err for err in result["errors"])
        )

        mutated = json.loads(json.dumps(receipt))
        mutated["artifacts"][1]["members"][0]["type"] = "odd"
        result = commitment.verify_commitment_receipt(mutated)
        self.assertFalse(result["valid"])
        self.assertTrue(
            any("unsupported directory member type" in err for err in result["errors"])
        )

        mutated = json.loads(json.dumps(receipt))
        mutated["artifacts"][1]["members"][1]["size"] = -1
        result = commitment.verify_commitment_receipt(mutated)
        self.assertFalse(result["valid"])
        self.assertTrue(
            any("directory file members require" in err for err in result["errors"])
        )

    def test_receipt_helpers_cover_fallback_branches(self):
        malformed_for_toto = {
            "type": commitment.COMMITMENT_RECEIPT_TYPE,
            "schema": commitment.COMMITMENT_RECEIPT_SCHEMA_VERSION,
            "subject": "bad-subject",
            "content_hash": self.digest,
            "artifacts": {"oops": True},
        }
        statement = cli.wrap_in_toto_statement(malformed_for_toto)
        self.assertEqual(statement["subject"][0]["name"], "commitment")

        malformed_for_toto = {
            "type": commitment.COMMITMENT_RECEIPT_TYPE,
            "schema": commitment.COMMITMENT_RECEIPT_SCHEMA_VERSION,
            "subject": {"name": "fallback-subject"},
            "content_hash": self.digest,
            "artifacts": ["bad", {"ref": "bad-digest", "digest": "oops"}],
        }
        statement = cli.wrap_in_toto_statement(malformed_for_toto)
        self.assertEqual(statement["subject"][0]["name"], "fallback-subject")

        pretty = cli.format_receipt_pretty(
            {
                "type": commitment.COMMITMENT_RECEIPT_TYPE,
                "subject": "bad",
                "statement": 3,
                "artifacts": {},
                "receipt_id": "c1-test",
                "content_hash": self.digest,
                "timestamp": "2026-01-01T00:00:00Z",
            }
        )
        self.assertIn("unknown", pretty)

        detail = cli.format_receipt_detail(
            {
                "type": commitment.COMMITMENT_RECEIPT_TYPE,
                "subject": "bad",
                "statement": 7,
                "provenance": "bad",
                "extensions": "bad",
                "artifacts": {"oops": True},
                "receipt_id": "c1-test",
                "content_hash": self.digest,
                "timestamp": "2026-01-01T00:00:00Z",
            }
        )
        self.assertIn("Items:    0 artifact(s)", detail)

        detail_receipt = self._build_receipt()
        detail_receipt["subject"] = "bad"
        detail_receipt["statement"] = 7
        detail_receipt["provenance"] = "bad"
        detail_receipt["artifacts"] = ["bad"] + detail_receipt["artifacts"] * 4
        detail_receipt["extensions"] = {f"k{i}": i for i in range(11)}
        detail = cli.format_receipt_detail(detail_receipt)
        self.assertIn("... and", detail)

    def test_write_receipt_recovers_sidecar_and_non_dict_filename_hints(self):
        old_cwd = os.getcwd()
        try:
            os.chdir(self.tmpdir)
            out_dir = self.root / ".receipts"
            receipt = self._build_receipt()
            path = Path(cli.write_receipt(receipt, output_dir=str(out_dir)))
            cbor_path = path.with_suffix(".cbor")
            cbor_path.unlink()
            second = Path(cli.write_receipt(receipt, output_dir=str(out_dir)))
            self.assertEqual(path, second)
            self.assertTrue(cbor_path.exists())

            odd = {
                "commit": "bad",
                "reviewed_commit": "bad",
                "subject": "bad",
                "content_hash": self.digest,
            }
            odd_path = Path(cli.write_receipt(odd, output_dir=str(out_dir)))
            self.assertTrue(odd_path.name.startswith("receipt_unknown_"))
        finally:
            os.chdir(old_cwd)


class TestCommitmentCli(unittest.TestCase):
    """CLI coverage for commitment mode."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="aiir-commitment-cli-")
        self.root = Path(self.tmpdir)
        self.plan = self.root / "plan.json"
        self.plan.write_text('{"status":"ready"}\n', encoding="utf-8")
        self.old_cwd = os.getcwd()
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_commitment_cli_output_and_verify(self):
        stderr = io.StringIO()
        stdout = io.StringIO()
        with patch("sys.stderr", stderr), patch("sys.stdout", stdout):
            code = cli.main(
                [
                    "--commitment-artifact",
                    "plan.json",
                    "--commitment-name",
                    "nisq-plan",
                    "--commitment-summary",
                    "Declared evaluation plan",
                    "--output",
                    ".receipts",
                    "--pretty",
                ]
            )
        self.assertEqual(code, 0)
        self.assertIn("1 commitment receipt generated", stderr.getvalue())
        self.assertIn("Commitment:", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")
        written = next((self.root / ".receipts").glob("receipt_*.json"))
        self.assertEqual(cli.main(["--verify", str(written)]), 0)

    def test_commitment_cli_stdout_default_and_jsonl(self):
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            code = cli.main(
                [
                    "--commitment-digest",
                    "packet=sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                    "--commitment-name",
                    "nisq-packet",
                    "--commitment-summary",
                    "Published packet digest",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["type"], "aiir.commitment_receipt")

        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            code = cli.main(
                [
                    "--commitment-artifact",
                    "plan.json",
                    "--commitment-name",
                    "nisq-plan",
                    "--commitment-summary",
                    "Declared evaluation plan",
                    "--jsonl",
                    "--in-toto",
                ]
            )
        self.assertEqual(code, 0)
        line = stdout.getvalue().strip()
        payload = json.loads(line)
        self.assertEqual(payload["_type"], "https://in-toto.io/Statement/v1")

    def test_commitment_cli_error_paths(self):
        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            code = cli.main(["--commitment-name", "x"])
        self.assertEqual(code, 1)
        self.assertIn("Commitment mode is incomplete", stderr.getvalue())

        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            code = cli.main(
                [
                    "--commitment-artifact",
                    "plan.json",
                    "--commitment-summary",
                    "Declared evaluation plan",
                ]
            )
        self.assertEqual(code, 1)
        self.assertIn("--commitment-name", stderr.getvalue())

        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            code = cli.main(
                [
                    "--commitment-artifact",
                    "plan.json",
                    "--commitment-name",
                    "nisq-plan",
                    "--commitment-summary",
                    "Declared evaluation plan",
                    "--review",
                ]
            )
        self.assertEqual(code, 1)
        self.assertIn("cannot be combined", stderr.getvalue())

        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            code = cli.main(
                [
                    "--commitment-artifact",
                    "missing.json",
                    "--commitment-name",
                    "nisq-plan",
                    "--commitment-summary",
                    "Declared evaluation plan",
                ]
            )
        self.assertEqual(code, 1)
        self.assertIn("Commitment artifact not found", stderr.getvalue())

        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            code = cli.main(
                [
                    "--commitment-artifact",
                    "plan.json",
                    "--commitment-name",
                    "nisq-plan",
                    "--commitment-summary",
                    "Declared evaluation plan",
                    "--sign",
                ]
            )
        self.assertEqual(code, 1)
        self.assertIn("--sign needs --output", stderr.getvalue())

        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            code = cli.main(
                [
                    "--commitment-artifact",
                    "plan.json",
                    "--commitment-name",
                    "nisq-plan",
                    "--commitment-summary",
                    "Declared evaluation plan",
                    "--github-action",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(stdout.getvalue())["provenance"]["generator"], "aiir.github"
        )

        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            code = cli.main(
                [
                    "--commitment-artifact",
                    "plan.json",
                    "--commitment-name",
                    "nisq-plan",
                    "--commitment-summary",
                    "Declared evaluation plan",
                    "--gitlab-ci",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(stdout.getvalue())["provenance"]["generator"], "aiir.gitlab"
        )

    def test_commitment_cli_signing_and_writer_failures(self):
        stderr = io.StringIO()
        with (
            patch("sys.stderr", stderr),
            patch("aiir.cli._sigstore_available", return_value=False),
        ):
            code = cli.main(
                [
                    "--commitment-artifact",
                    "plan.json",
                    "--commitment-name",
                    "nisq-plan",
                    "--commitment-summary",
                    "Declared evaluation plan",
                    "--output",
                    ".receipts",
                    "--sign",
                ]
            )
        self.assertEqual(code, 1)
        self.assertIn("Signing needs the 'sigstore' package", stderr.getvalue())

        stderr = io.StringIO()
        with (
            patch("sys.stderr", stderr),
            patch("aiir.cli.write_receipt", side_effect=ValueError("bad output")),
        ):
            code = cli.main(
                [
                    "--commitment-artifact",
                    "plan.json",
                    "--commitment-name",
                    "nisq-plan",
                    "--commitment-summary",
                    "Declared evaluation plan",
                    "--output",
                    ".receipts",
                ]
            )
        self.assertEqual(code, 1)
        self.assertIn("bad output", stderr.getvalue())

        receipt_path = self.root / ".receipts" / "receipt.json"
        receipt_path.parent.mkdir(exist_ok=True)
        receipt_path.write_text("{}", encoding="utf-8")
        stderr = io.StringIO()
        with (
            patch("sys.stderr", stderr),
            patch("aiir.cli._sigstore_available", return_value=True),
            patch("aiir.cli.write_receipt", return_value=str(receipt_path)),
            patch("aiir.cli.sign_receipt_file", side_effect=RuntimeError("boom")),
        ):
            code = cli.main(
                [
                    "--commitment-artifact",
                    "plan.json",
                    "--commitment-name",
                    "nisq-plan",
                    "--commitment-summary",
                    "Declared evaluation plan",
                    "--output",
                    ".receipts",
                    "--sign",
                ]
            )
        self.assertEqual(code, 1)
        self.assertIn("Signing failed: boom", stderr.getvalue())
        self.assertFalse(receipt_path.exists())

    def test_commitment_cli_signed_summary_and_verify_signature_paths(self):
        stderr = io.StringIO()
        with (
            patch("sys.stderr", stderr),
            patch("aiir.cli._sigstore_available", return_value=True),
            patch(
                "aiir.cli.sign_receipt_file", return_value=".receipts/receipt.sigstore"
            ),
        ):
            code = cli.main(
                [
                    "--commitment-artifact",
                    "plan.json",
                    "--commitment-name",
                    "nisq-plan",
                    "--commitment-summary",
                    "Declared evaluation plan",
                    "--output",
                    ".receipts",
                    "--sign",
                ]
            )
        self.assertEqual(code, 0)
        self.assertIn("1 signed", stderr.getvalue())

        written = next((self.root / ".receipts").glob("receipt_*.json"))
        stderr = io.StringIO()
        stdout = io.StringIO()
        with (
            patch("sys.stderr", stderr),
            patch("sys.stdout", stdout),
            patch(
                "aiir.cli.verify_receipt_signature",
                return_value={"valid": True, "policy": "any"},
            ),
        ):
            code = cli.main(
                ["--verify", str(written), "--verify-signature", "--explain"]
            )
        self.assertEqual(code, 0)
        self.assertIn("Signature verified", stderr.getvalue())
        self.assertIn("What was checked", stderr.getvalue())

        stderr = io.StringIO()
        stdout = io.StringIO()
        with (
            patch("sys.stderr", stderr),
            patch("sys.stdout", stdout),
            patch(
                "aiir.cli.verify_receipt_signature",
                return_value={"valid": False, "error": "bad signature"},
            ),
        ):
            code = cli.main(["--verify", str(written), "--verify-signature"])
        self.assertEqual(code, 1)
        self.assertIn("Signature FAILED: bad signature", stderr.getvalue())
