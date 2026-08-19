"""Tests for CLI parsing, integration, and UX."""
# Copyright 2025-2026 Invariant Systems, Inc.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

# Import the module under test
import aiir.cli as cli


class TestCLIParsing(unittest.TestCase):
    """Test CLI argument handling."""

    def test_verify_mode_valid_receipt(self):
        """--verify with a valid receipt file should return 0."""
        # Create a valid receipt
        commit = cli.CommitInfo(
            sha="deadbeef" * 5,
            author_name="Test",
            author_email="t@t.com",
            author_date="2026-01-01T00:00:00Z",
            committer_name="Test",
            committer_email="t@t.com",
            committer_date="2026-01-01T00:00:00Z",
            subject="test",
            body="test",
            diff_stat="",
            diff_hash="sha256:0000",
            files_changed=[],
            ai_signals_detected=[],
            is_ai_authored=False,
        )
        receipt = cli.build_commit_receipt(commit)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(receipt, f)
            tmppath = f.name

        try:
            ret = cli.main(["--verify", tmppath])
            self.assertEqual(ret, 0)
        finally:
            os.unlink(tmppath)

    def test_verify_mode_jsonl_ledger_routes_to_ledger_verifier(self):
        """--verify should accept the default .aiir/receipts.jsonl format."""
        commit = cli.CommitInfo(
            sha="deadbeef" * 5,
            author_name="Test",
            author_email="t@t.com",
            author_date="2026-01-01T00:00:00Z",
            committer_name="Test",
            committer_email="t@t.com",
            committer_date="2026-01-01T00:00:00Z",
            subject="test",
            body="test",
            diff_stat="",
            diff_hash="sha256:0000",
            files_changed=[],
            ai_signals_detected=[],
            is_ai_authored=False,
        )
        receipt = cli.build_commit_receipt(commit)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps(receipt) + "\n")
            f.write(json.dumps(receipt) + "\n")
            tmppath = f.name

        try:
            captured_out = StringIO()
            captured_err = StringIO()
            with patch("sys.stdout", captured_out), patch("sys.stderr", captured_err):
                ret = cli.main(["--verify", tmppath])

            self.assertEqual(ret, 0)
            self.assertIn("ledger receipts verified", captured_err.getvalue())
            result = json.loads(captured_out.getvalue())
            self.assertTrue(result["valid"])
            self.assertEqual(result["count"], 2)
            self.assertEqual(result["valid_receipts"], 2)
        finally:
            os.unlink(tmppath)

    def test_verify_mode_jsonl_ledger_reports_line_errors(self):
        """Invalid JSONL ledgers should use ledger-specific failure output."""
        commit = cli.CommitInfo(
            sha="deadbeef" * 5,
            author_name="Test",
            author_email="t@t.com",
            author_date="2026-01-01T00:00:00Z",
            committer_name="Test",
            committer_email="t@t.com",
            committer_date="2026-01-01T00:00:00Z",
            subject="test",
            body="test",
            diff_stat="",
            diff_hash="sha256:0000",
            files_changed=[],
            ai_signals_detected=[],
            is_ai_authored=False,
        )
        receipt = cli.build_commit_receipt(commit)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps(receipt) + "\n")
            f.write("not-json\n")
            tmppath = f.name

        try:
            captured_out = StringIO()
            captured_err = StringIO()
            with patch("sys.stdout", captured_out), patch("sys.stderr", captured_err):
                ret = cli.main(["--verify", tmppath])

            self.assertEqual(ret, 1)
            stderr = captured_err.getvalue()
            self.assertIn("Ledger verification failed", stderr)
            self.assertIn("Invalid JSON", stderr)
            result = json.loads(captured_out.getvalue())
            self.assertFalse(result["valid"])
            self.assertEqual(result["count"], 2)
            self.assertEqual(result["valid_receipts"], 1)
        finally:
            os.unlink(tmppath)

    def test_verify_mode_tampered_receipt(self):
        """--verify with a tampered receipt should return 1."""
        commit = cli.CommitInfo(
            sha="deadbeef" * 5,
            author_name="Test",
            author_email="t@t.com",
            author_date="2026-01-01T00:00:00Z",
            committer_name="Test",
            committer_email="t@t.com",
            committer_date="2026-01-01T00:00:00Z",
            subject="test",
            body="test",
            diff_stat="",
            diff_hash="sha256:0000",
            files_changed=[],
            ai_signals_detected=[],
            is_ai_authored=False,
        )
        receipt = cli.build_commit_receipt(commit)
        receipt["commit"]["subject"] = "TAMPERED"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(receipt, f)
            tmppath = f.name

        try:
            ret = cli.main(["--verify", tmppath])
            self.assertEqual(ret, 1)
        finally:
            os.unlink(tmppath)

    def test_doctor_jsonl_rejected(self):
        """--doctor only supports the object JSON output mode."""
        import io

        captured_err = io.StringIO()
        with patch("sys.stderr", captured_err):
            ret = cli.main(["--doctor", "--jsonl"])

        self.assertEqual(ret, 1)
        self.assertIn("--doctor supports --json, not --jsonl", captured_err.getvalue())

    def test_install_and_remove_hook_are_mutually_exclusive(self):
        """Hook lifecycle mode should reject conflicting top-level actions."""
        import io

        captured_err = io.StringIO()
        with patch("sys.stderr", captured_err):
            ret = cli.main(["--install-hook", "--remove-hook"])

        self.assertEqual(ret, 1)
        self.assertIn(
            "Choose only one of --install-hook or --remove-hook",
            captured_err.getvalue(),
        )

    def test_remove_hook_rejects_install_only_flags(self):
        """Remove mode should reject install-only hook conflict flags."""
        import io

        captured_err = io.StringIO()
        with patch("sys.stderr", captured_err):
            ret = cli.main(["--remove-hook", "--hook-append"])

        self.assertEqual(ret, 1)
        self.assertIn("only apply to --install-hook", captured_err.getvalue())

    def test_skip_receipt_only_commits_returns_success_without_writing(self):
        """Receipt-only ledger commits should be treated as a clean no-op."""
        receipt = {
            "commit": {
                "files": [
                    ".aiir/index.json",
                    ".aiir/receipts.jsonl",
                    ".aiir/receipts/receipt_deadbeef.json",
                ]
            }
        }

        with (
            patch("aiir.cli.generate_receipt", return_value=receipt),
            patch("aiir.cli.append_to_ledger") as append_to_ledger,
            patch("aiir.cli.write_receipt") as write_receipt,
        ):
            ret = cli.main(["--skip-receipt-only-commits", "--quiet"])

        self.assertEqual(ret, 0)
        append_to_ledger.assert_not_called()
        write_receipt.assert_not_called()

    def test_skip_receipt_only_commits_reports_non_quiet_skip(self):
        """Receipt-only ledger commits should explain the skip when not quiet."""
        import io

        receipt = {
            "commit": {
                "files": [
                    ".aiir/index.json",
                    ".aiir/receipts.jsonl",
                    ".aiir/receipts/receipt_deadbeef.json",
                ]
            }
        }

        captured_err = io.StringIO()
        with (
            patch("aiir.cli.generate_receipt", return_value=receipt),
            patch("aiir.cli.append_to_ledger") as append_to_ledger,
            patch("aiir.cli.write_receipt") as write_receipt,
            patch("sys.stderr", captured_err),
        ):
            ret = cli.main(["--skip-receipt-only-commits"])

        self.assertEqual(ret, 0)
        self.assertIn(
            "Skipping receipt-only AIIR ledger commit.", captured_err.getvalue()
        )
        append_to_ledger.assert_not_called()
        write_receipt.assert_not_called()

    def test_quickstart_happy_path_prints_immediate_success(self):
        """quickstart should install, seed, verify, and print two success lines."""
        import io

        commit = cli.CommitInfo(
            sha="deadbeef" * 5,
            author_name="Test",
            author_email="t@t.com",
            author_date="2026-01-01T00:00:00Z",
            committer_name="Test",
            committer_email="t@t.com",
            committer_date="2026-01-01T00:00:00Z",
            subject="test",
            body="test",
            diff_stat="",
            diff_hash="sha256:0000",
            files_changed=[],
            ai_signals_detected=[],
            is_ai_authored=False,
        )
        receipt = cli.build_commit_receipt(commit)

        captured_err = io.StringIO()
        with (
            patch("aiir.cli.get_repo_root", return_value="/tmp/repo"),
            patch("aiir.cli._install_managed_post_commit_hook"),
            patch("aiir.cli._ensure_ledger_initialized"),
            patch("aiir.cli.generate_receipt", return_value=receipt),
            patch("aiir.cli.append_to_ledger"),
            patch(
                "aiir.cli.verify_receipt_ledger_file",
                return_value={"valid": True, "valid_receipts": 1},
            ),
            patch("sys.stderr", captured_err),
        ):
            code = cli.main(["quickstart"])

        self.assertEqual(code, 0)
        report = captured_err.getvalue()
        self.assertIn("AIIR active", report)
        self.assertIn("Managed post-commit hook installed", report)
        self.assertIn("Verified (1 receipt)", report)

    def test_setup_alias_maps_to_quickstart(self):
        """setup shorthand should invoke the same quickstart behavior."""
        commit = cli.CommitInfo(
            sha="deadbeef" * 5,
            author_name="Test",
            author_email="t@t.com",
            author_date="2026-01-01T00:00:00Z",
            committer_name="Test",
            committer_email="t@t.com",
            committer_date="2026-01-01T00:00:00Z",
            subject="test",
            body="test",
            diff_stat="",
            diff_hash="sha256:0000",
            files_changed=[],
            ai_signals_detected=[],
            is_ai_authored=False,
        )
        receipt = cli.build_commit_receipt(commit)
        with (
            patch("aiir.cli.get_repo_root", return_value="/tmp/repo"),
            patch("aiir.cli._install_managed_post_commit_hook"),
            patch("aiir.cli._ensure_ledger_initialized"),
            patch("aiir.cli.generate_receipt", return_value=receipt),
            patch("aiir.cli.append_to_ledger"),
            patch(
                "aiir.cli.verify_receipt_ledger_file",
                return_value={"valid": True, "valid_receipts": 1},
            ),
        ):
            code = cli.main(["setup"])
        self.assertEqual(code, 0)

    def test_quickstart_json_output(self):
        """quickstart should support structured --json output."""
        import io

        commit = cli.CommitInfo(
            sha="deadbeef" * 5,
            author_name="Test",
            author_email="t@t.com",
            author_date="2026-01-01T00:00:00Z",
            committer_name="Test",
            committer_email="t@t.com",
            committer_date="2026-01-01T00:00:00Z",
            subject="test",
            body="test",
            diff_stat="",
            diff_hash="sha256:0000",
            files_changed=[],
            ai_signals_detected=[],
            is_ai_authored=False,
        )
        receipt = cli.build_commit_receipt(commit)
        captured_out = io.StringIO()
        with (
            patch("aiir.cli.get_repo_root", return_value="/tmp/repo"),
            patch("aiir.cli._install_managed_post_commit_hook"),
            patch("aiir.cli._ensure_ledger_initialized"),
            patch("aiir.cli.generate_receipt", return_value=receipt),
            patch("aiir.cli.append_to_ledger"),
            patch(
                "aiir.cli.verify_receipt_ledger_file",
                return_value={"valid": True, "valid_receipts": 1},
            ),
            patch("sys.stdout", captured_out),
        ):
            code = cli.main(["quickstart", "--json"])

        self.assertEqual(code, 0)
        payload = json.loads(captured_out.getvalue())
        self.assertEqual(payload["mode"], "quickstart")
        self.assertTrue(payload["active"])

    def test_quickstart_uses_total_when_valid_hashes_missing(self):
        """quickstart should fall back to total when verifier omits valid_hashes."""
        import io

        commit = cli.CommitInfo(
            sha="deadbeef" * 5,
            author_name="Test",
            author_email="t@t.com",
            author_date="2026-01-01T00:00:00Z",
            committer_name="Test",
            committer_email="t@t.com",
            committer_date="2026-01-01T00:00:00Z",
            subject="test",
            body="test",
            diff_stat="",
            diff_hash="sha256:0000",
            files_changed=[],
            ai_signals_detected=[],
            is_ai_authored=False,
        )
        receipt = cli.build_commit_receipt(commit)
        captured_err = io.StringIO()
        with (
            patch("aiir.cli.get_repo_root", return_value="/tmp/repo"),
            patch("aiir.cli._install_managed_post_commit_hook"),
            patch("aiir.cli._ensure_ledger_initialized"),
            patch("aiir.cli.generate_receipt", return_value=receipt),
            patch("aiir.cli.append_to_ledger"),
            patch(
                "aiir.cli.verify_receipt_ledger_file",
                return_value={"valid": True, "count": 2},
            ),
            patch("sys.stderr", captured_err),
        ):
            code = cli.main(["quickstart"])

        self.assertEqual(code, 0)
        self.assertIn("Verified (2 receipts)", captured_err.getvalue())

    def test_quickstart_keeps_existing_custom_hook_without_failing(self):
        """quickstart should continue when a custom hook exists."""
        import io

        commit = cli.CommitInfo(
            sha="deadbeef" * 5,
            author_name="Test",
            author_email="t@t.com",
            author_date="2026-01-01T00:00:00Z",
            committer_name="Test",
            committer_email="t@t.com",
            committer_date="2026-01-01T00:00:00Z",
            subject="test",
            body="test",
            diff_stat="",
            diff_hash="sha256:0000",
            files_changed=[],
            ai_signals_detected=[],
            is_ai_authored=False,
        )
        receipt = cli.build_commit_receipt(commit)
        captured_err = io.StringIO()
        with (
            patch("aiir.cli.get_repo_root", return_value="/tmp/repo"),
            patch(
                "aiir.cli._install_managed_post_commit_hook",
                side_effect=ValueError("custom hook present"),
            ),
            patch("aiir.cli._ensure_ledger_initialized"),
            patch("aiir.cli.generate_receipt", return_value=receipt),
            patch("aiir.cli.append_to_ledger"),
            patch(
                "aiir.cli.verify_receipt_ledger_file",
                return_value={"valid": True, "valid_receipts": 1},
            ),
            patch("sys.stderr", captured_err),
        ):
            code = cli.main(["quickstart"])

        self.assertEqual(code, 0)
        self.assertIn(
            "Existing custom post-commit hook detected", captured_err.getvalue()
        )

    def test_status_json_output(self):
        """status should support structured --json output."""
        import io

        with tempfile.TemporaryDirectory() as td:
            ledger_dir = Path(td) / ".aiir"
            ledger_dir.mkdir(parents=True, exist_ok=True)
            (ledger_dir / "receipts.jsonl").write_text(
                json.dumps(
                    {
                        "ai_attestation": {"is_ai_authored": True},
                        "extensions": {
                            "sigstore_bundle": {
                                "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                                "verificationMaterial": {
                                    "certificate": {"rawBytes": "QQ=="}
                                },
                                "messageSignature": {"signature": "Zm9v"},
                            }
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            captured_out = io.StringIO()
            with (
                patch(
                    "aiir.cli._collect_doctor_state",
                    return_value={
                        "git_available": True,
                        "head_receipt_status": "present",
                        "managed_hook_state": "managed",
                    },
                ),
                patch("sys.stdout", captured_out),
            ):
                code = cli.main(["status", "--ledger", str(ledger_dir), "--json"])

        self.assertEqual(code, 0)
        payload = json.loads(captured_out.getvalue())
        self.assertEqual(payload["mode"], "status")
        self.assertEqual(payload["ai_usage_commits"], 1)
        self.assertEqual(payload["signed_receipts"], 1)
        self.assertEqual(payload["unsigned_receipts"], 0)

    def test_ci_mode_requires_receipt_ledger(self):
        """ci should fail fast when the default receipts ledger is missing."""
        with tempfile.TemporaryDirectory() as td:
            cwd_before = os.getcwd()
            os.chdir(td)
            try:
                code = cli.main(["ci"])
            finally:
                os.chdir(cwd_before)
        self.assertEqual(code, 1)

    def test_ci_json_output(self):
        """ci should support structured --json output."""
        import io

        with tempfile.TemporaryDirectory() as td:
            ledger_dir = Path(td) / ".aiir"
            ledger_dir.mkdir(parents=True, exist_ok=True)
            (ledger_dir / "receipts.jsonl").write_text(
                json.dumps(
                    {
                        "ai_attestation": {"is_ai_authored": False},
                        "extensions": {
                            "sigstore_bundle": {
                                "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                                "verificationMaterial": {
                                    "certificate": {"rawBytes": "QQ=="}
                                },
                                "messageSignature": {"signature": "Zm9v"},
                            }
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            captured_out = io.StringIO()
            with (
                patch(
                    "aiir.cli.verify_receipt_ledger_file", return_value={"valid": True}
                ),
                patch("sys.stdout", captured_out),
            ):
                code = cli.main(["ci", "--ledger", str(ledger_dir), "--json"])

        self.assertEqual(code, 0)
        payload = json.loads(captured_out.getvalue())
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["mode"], "ci")
        self.assertEqual(payload["signed_receipts"], 1)
        self.assertEqual(payload["unsigned_receipts"], 0)

    def test_ci_json_missing_ledger_returns_structured_error(self):
        """ci --json should return machine-readable errors on missing ledger."""
        import io

        with tempfile.TemporaryDirectory() as td:
            captured_out = io.StringIO()
            cwd_before = os.getcwd()
            os.chdir(td)
            try:
                with patch("sys.stdout", captured_out):
                    code = cli.main(["ci", "--json"])
            finally:
                os.chdir(cwd_before)

        self.assertEqual(code, 1)
        payload = json.loads(captured_out.getvalue())
        self.assertEqual(payload["mode"], "ci")
        self.assertFalse(payload["valid"])
        self.assertIn("Missing receipt ledger", payload["error"])

    def test_ci_mode_sets_github_outputs_when_running_in_actions(self):
        """ci should export aggregate metrics to GitHub Actions outputs."""
        with tempfile.TemporaryDirectory() as td:
            ledger_dir = Path(td) / ".aiir"
            ledger_dir.mkdir(parents=True, exist_ok=True)
            (ledger_dir / "receipts.jsonl").write_text(
                json.dumps(
                    {
                        "ai_attestation": {"is_ai_authored": True},
                        "extensions": {
                            "sigstore_bundle": {
                                "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                                "verificationMaterial": {
                                    "certificate": {"rawBytes": "QQ=="}
                                },
                                "messageSignature": {"signature": "Zm9v"},
                            }
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with (
                patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}, clear=False),
                patch(
                    "aiir.cli.verify_receipt_ledger_file", return_value={"valid": True}
                ),
                patch("aiir.cli.set_github_output") as set_output,
                patch("aiir.cli.set_github_summary") as set_summary,
            ):
                code = cli.main(["ci", "--ledger", str(ledger_dir)])

        self.assertEqual(code, 0)
        self.assertEqual(set_output.call_count, 5)
        set_output.assert_any_call("AIIR_AI_COMMIT_COUNT", "1")
        set_output.assert_any_call("AIIR_SIGNED_RECEIPT_COUNT", "1")
        set_output.assert_any_call("AIIR_UNSIGNED_RECEIPT_COUNT", "0")
        set_summary.assert_called_once()

    def test_ci_mode_sets_gitlab_outputs_when_running_in_gitlab_ci(self):
        """ci should export aggregate metrics to GitLab dotenv outputs."""
        with tempfile.TemporaryDirectory() as td:
            ledger_dir = Path(td) / ".aiir"
            ledger_dir.mkdir(parents=True, exist_ok=True)
            (ledger_dir / "receipts.jsonl").write_text(
                json.dumps(
                    {
                        "ai_attestation": {"is_ai_authored": False},
                        "extensions": {
                            "sigstore_bundle": {
                                "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                                "verificationMaterial": {
                                    "certificate": {"rawBytes": "QQ=="}
                                },
                                "messageSignature": {"signature": "Zm9v"},
                            }
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with (
                patch.dict(
                    os.environ,
                    {"GITLAB_CI": "true", "GITHUB_ACTIONS": "false"},
                    clear=False,
                ),
                patch(
                    "aiir.cli.verify_receipt_ledger_file", return_value={"valid": True}
                ),
                patch("aiir.cli.set_gitlab_ci_output") as set_gitlab_output,
            ):
                code = cli.main(["ci", "--ledger", str(ledger_dir)])

        self.assertEqual(code, 0)
        self.assertEqual(set_gitlab_output.call_count, 5)
        set_gitlab_output.assert_any_call("AIIR_SIGNED_RECEIPT_COUNT", "1")
        set_gitlab_output.assert_any_call("AIIR_UNSIGNED_RECEIPT_COUNT", "0")

    def test_status_shorthand_reports_receipt_count(self):
        """status shorthand should print a concise repo summary."""
        import io

        with tempfile.TemporaryDirectory() as td:
            ledger_dir = Path(td) / ".aiir"
            ledger_dir.mkdir(parents=True, exist_ok=True)
            (ledger_dir / "receipts.jsonl").write_text(
                '{"a":1}\n{"a":2}\n', encoding="utf-8"
            )

            captured_err = io.StringIO()
            with (
                patch(
                    "aiir.cli._collect_doctor_state",
                    return_value={
                        "git_available": True,
                        "head_sha": "deadbeef" * 5,
                        "head_receipt_status": "present",
                    },
                ),
                patch("sys.stderr", captured_err),
            ):
                code = cli.main(["status", "--ledger", str(ledger_dir)])

        self.assertEqual(code, 0)
        report = captured_err.getvalue()
        self.assertIn("Repo: clean", report)
        self.assertIn("Receipts: 2", report)
        self.assertIn("Last commit: verified", report)
        # WS-D fix: non-contradictory output — 'none' when ai_receipts_count == 0
        self.assertIn("AI usage: none (0 commits)", report)
        self.assertNotIn("AI usage: detected (0 commits)", report)
        self.assertIn("Signing: 0 signed, 2 unsigned", report)

    def test_ci_mode_validates_multiline_ledger(self):
        """ci should verify JSONL ledgers with more than one receipt."""
        import io

        commit_one = cli.CommitInfo(
            sha="1" * 40,
            author_name="Test",
            author_email="t@t.com",
            author_date="2026-01-01T00:00:00Z",
            committer_name="Test",
            committer_email="t@t.com",
            committer_date="2026-01-01T00:00:00Z",
            subject="first",
            body="",
            diff_stat="",
            diff_hash="sha256:" + "0" * 64,
            files_changed=[],
            ai_signals_detected=["co-author: GitHub Copilot"],
            is_ai_authored=True,
        )
        commit_two = cli.CommitInfo(
            sha="2" * 40,
            author_name="Test",
            author_email="t@t.com",
            author_date="2026-01-01T00:00:00Z",
            committer_name="Test",
            committer_email="t@t.com",
            committer_date="2026-01-01T00:00:00Z",
            subject="second",
            body="",
            diff_stat="",
            diff_hash="sha256:" + "1" * 64,
            files_changed=[],
            ai_signals_detected=[],
            is_ai_authored=False,
        )
        receipt_one = cli.build_commit_receipt(commit_one)
        receipt_two = cli.build_commit_receipt(commit_two)

        with tempfile.TemporaryDirectory() as td:
            ledger_dir = Path(td) / ".aiir"
            ledger_dir.mkdir(parents=True, exist_ok=True)
            (ledger_dir / "receipts.jsonl").write_text(
                json.dumps(receipt_one) + "\n" + json.dumps(receipt_two) + "\n",
                encoding="utf-8",
            )
            captured_out = io.StringIO()
            with patch("sys.stdout", captured_out):
                code = cli.main(["ci", "--ledger", str(ledger_dir), "--json"])

        self.assertEqual(code, 0)
        payload = json.loads(captured_out.getvalue())
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["receipts"], 2)
        self.assertEqual(payload["ai_commits"], 1)

    def test_quickstart_jsonl_rejected_as_json_payload(self):
        """quickstart --jsonl --json should return a structured error."""
        import io

        captured_out = io.StringIO()
        with patch("sys.stdout", captured_out):
            code = cli.main(["quickstart", "--json", "--jsonl"])

        self.assertEqual(code, 1)
        payload = json.loads(captured_out.getvalue())
        self.assertEqual(payload["mode"], "quickstart")
        self.assertFalse(payload["ok"])

    def test_quickstart_jsonl_rejected_as_stderr_message(self):
        """quickstart --jsonl should fail with a plain stderr error."""
        import io

        captured_err = io.StringIO()
        with patch("sys.stderr", captured_err):
            code = cli.main(["quickstart", "--jsonl"])

        self.assertEqual(code, 1)
        self.assertIn(
            "--quickstart supports --json, not --jsonl.", captured_err.getvalue()
        )

    def test_quickstart_repo_root_failure(self):
        """quickstart should fail cleanly when no git repo root is available."""
        import io

        captured_err = io.StringIO()
        with (
            patch("aiir.cli.get_repo_root", side_effect=RuntimeError("not a git repo")),
            patch("sys.stderr", captured_err),
        ):
            code = cli.main(["quickstart"])

        self.assertEqual(code, 1)
        self.assertIn("not a git repo", captured_err.getvalue())

    def test_quickstart_install_hook_runtime_error(self):
        """quickstart should surface managed-hook installation failures."""
        import io

        captured_err = io.StringIO()
        with (
            patch("aiir.cli.get_repo_root", return_value="/tmp/repo"),
            patch(
                "aiir.cli._install_managed_post_commit_hook",
                side_effect=RuntimeError("hook install failed"),
            ),
            patch("sys.stderr", captured_err),
        ):
            code = cli.main(["quickstart"])

        self.assertEqual(code, 1)
        self.assertIn("hook install failed", captured_err.getvalue())

    def test_quickstart_generate_receipt_none_fails(self):
        """quickstart should fail if the demo receipt cannot be generated."""
        import io

        captured_err = io.StringIO()
        with (
            patch("aiir.cli.get_repo_root", return_value="/tmp/repo"),
            patch("aiir.cli._install_managed_post_commit_hook"),
            patch("aiir.cli._ensure_ledger_initialized"),
            patch("aiir.cli.generate_receipt", return_value=None),
            patch("sys.stderr", captured_err),
        ):
            code = cli.main(["quickstart"])

        self.assertEqual(code, 1)
        self.assertIn("Could not generate demo receipt", captured_err.getvalue())

    def test_quickstart_append_failure_is_reported(self):
        """quickstart should report ledger append failures."""
        import io

        commit = cli.CommitInfo(
            sha="deadbeef" * 5,
            author_name="Test",
            author_email="t@t.com",
            author_date="2026-01-01T00:00:00Z",
            committer_name="Test",
            committer_email="t@t.com",
            committer_date="2026-01-01T00:00:00Z",
            subject="test",
            body="test",
            diff_stat="",
            diff_hash="sha256:0000",
            files_changed=[],
            ai_signals_detected=[],
            is_ai_authored=False,
        )
        receipt = cli.build_commit_receipt(commit)
        captured_err = io.StringIO()
        with (
            patch("aiir.cli.get_repo_root", return_value="/tmp/repo"),
            patch("aiir.cli._install_managed_post_commit_hook"),
            patch("aiir.cli._ensure_ledger_initialized"),
            patch("aiir.cli.generate_receipt", return_value=receipt),
            patch(
                "aiir.cli.append_to_ledger", side_effect=RuntimeError("append failed")
            ),
            patch("sys.stderr", captured_err),
        ):
            code = cli.main(["quickstart"])

        self.assertEqual(code, 1)
        self.assertIn("append failed", captured_err.getvalue())

    def test_quickstart_verify_failure_is_reported(self):
        """quickstart should fail if ledger verification fails after seeding."""
        import io

        commit = cli.CommitInfo(
            sha="deadbeef" * 5,
            author_name="Test",
            author_email="t@t.com",
            author_date="2026-01-01T00:00:00Z",
            committer_name="Test",
            committer_email="t@t.com",
            committer_date="2026-01-01T00:00:00Z",
            subject="test",
            body="test",
            diff_stat="",
            diff_hash="sha256:0000",
            files_changed=[],
            ai_signals_detected=[],
            is_ai_authored=False,
        )
        receipt = cli.build_commit_receipt(commit)
        captured_err = io.StringIO()
        with (
            patch("aiir.cli.get_repo_root", return_value="/tmp/repo"),
            patch("aiir.cli._install_managed_post_commit_hook"),
            patch("aiir.cli._ensure_ledger_initialized"),
            patch("aiir.cli.generate_receipt", return_value=receipt),
            patch("aiir.cli.append_to_ledger"),
            patch("aiir.cli.verify_receipt_ledger_file", return_value={"valid": False}),
            patch("sys.stderr", captured_err),
        ):
            code = cli.main(["quickstart"])

        self.assertEqual(code, 1)
        self.assertIn("Quickstart verification failed", captured_err.getvalue())

    def test_status_jsonl_rejected_as_json_payload(self):
        """status --jsonl --json should return a structured error."""
        import io

        captured_out = io.StringIO()
        with patch("sys.stdout", captured_out):
            code = cli.main(["status", "--json", "--jsonl"])

        self.assertEqual(code, 1)
        payload = json.loads(captured_out.getvalue())
        self.assertEqual(payload["mode"], "status")
        self.assertFalse(payload["ok"])

    def test_status_jsonl_rejected_as_stderr_message(self):
        """status --jsonl should fail with a plain stderr error."""
        import io

        captured_err = io.StringIO()
        with patch("sys.stderr", captured_err):
            code = cli.main(["status", "--jsonl"])

        self.assertEqual(code, 1)
        self.assertIn("--status supports --json, not --jsonl.", captured_err.getvalue())

    def test_ci_jsonl_rejected_as_json_payload(self):
        """ci --jsonl --json should return a structured error."""
        import io

        captured_out = io.StringIO()
        with patch("sys.stdout", captured_out):
            code = cli.main(["ci", "--json", "--jsonl"])

        self.assertEqual(code, 1)
        payload = json.loads(captured_out.getvalue())
        self.assertEqual(payload["mode"], "ci")
        self.assertFalse(payload["ok"])

    def test_ci_jsonl_rejected_as_stderr_message(self):
        """ci --jsonl should fail with a plain stderr error."""
        import io

        captured_err = io.StringIO()
        with patch("sys.stderr", captured_err):
            code = cli.main(["ci", "--jsonl"])

        self.assertEqual(code, 1)
        self.assertIn("--ci supports --json, not --jsonl.", captured_err.getvalue())

    def test_ci_verify_failure_returns_structured_error(self):
        """ci --json should report ledger verification failures structurally."""
        import io

        with tempfile.TemporaryDirectory() as td:
            ledger_dir = Path(td) / ".aiir"
            ledger_dir.mkdir(parents=True, exist_ok=True)
            (ledger_dir / "receipts.jsonl").write_text("{}\n", encoding="utf-8")
            captured_out = io.StringIO()
            with (
                patch(
                    "aiir.cli.verify_receipt_ledger_file", return_value={"valid": False}
                ),
                patch("sys.stdout", captured_out),
            ):
                code = cli.main(["ci", "--ledger", str(ledger_dir), "--json"])

        self.assertEqual(code, 1)
        payload = json.loads(captured_out.getvalue())
        self.assertEqual(payload["mode"], "ci")
        self.assertFalse(payload["valid"])
        self.assertIn("Receipt verification failed", payload["error"])

    def test_ci_verify_failure_reports_stderr_message(self):
        """ci should print a stderr error when ledger verification fails."""
        import io

        with tempfile.TemporaryDirectory() as td:
            ledger_dir = Path(td) / ".aiir"
            ledger_dir.mkdir(parents=True, exist_ok=True)
            (ledger_dir / "receipts.jsonl").write_text("{}\n", encoding="utf-8")
            captured_err = io.StringIO()
            with (
                patch(
                    "aiir.cli.verify_receipt_ledger_file", return_value={"valid": False}
                ),
                patch("sys.stderr", captured_err),
            ):
                code = cli.main(["ci", "--ledger", str(ledger_dir)])

        self.assertEqual(code, 1)
        self.assertIn("Receipt verification failed", captured_err.getvalue())


class TestReceiptLedgerVerification(unittest.TestCase):
    """Targeted tests for JSONL ledger verification branches."""

    def test_verify_receipt_ledger_file_missing(self):
        result = cli.verify_receipt_ledger_file("/nonexistent/ledger.jsonl")

        self.assertFalse(result["valid"])
        self.assertIn("File not found", result["error"])

    def test_verify_receipt_ledger_file_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "ledger.jsonl"
            target.write_text("{}\n", encoding="utf-8")
            link = Path(td) / "ledger-link.jsonl"
            link.symlink_to(target)

            result = cli.verify_receipt_ledger_file(str(link))

        self.assertFalse(result["valid"])
        self.assertIn("symlink", result["error"])

    def test_verify_receipt_ledger_file_oversized_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "ledger.jsonl"
            ledger.write_text("{}\n", encoding="utf-8")
            with patch("aiir._verify.MAX_RECEIPT_FILE_SIZE", 1):
                result = cli.verify_receipt_ledger_file(str(ledger))

        self.assertFalse(result["valid"])
        self.assertIn("File too large", result["error"])

    def test_verify_receipt_ledger_file_collects_parse_and_verification_errors(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "ledger.jsonl"
            ledger.write_text("\nnot-json\n[]\n{}\n", encoding="utf-8")
            with patch(
                "aiir._verify.verify_receipt",
                return_value={"valid": False, "errors": ["content hash mismatch"]},
            ):
                result = cli.verify_receipt_ledger_file(str(ledger))

        self.assertFalse(result["valid"])
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["valid_receipts"], 0)
        self.assertTrue(any("Invalid JSON" in error for error in result["errors"]))
        self.assertTrue(
            any("Expected JSON object" in error for error in result["errors"])
        )
        self.assertTrue(
            any("content hash mismatch" in error for error in result["errors"])
        )

    def test_verify_receipt_ledger_file_handles_invalid_receipt_without_errors_list(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "ledger.jsonl"
            ledger.write_text("{}\n", encoding="utf-8")
            with patch("aiir._verify.verify_receipt", return_value={"valid": False}):
                result = cli.verify_receipt_ledger_file(str(ledger))

        self.assertFalse(result["valid"])
        self.assertIn("receipt verification failed", result["errors"][0])


class TestLedgerSummaryHelper(unittest.TestCase):
    """Close the small remaining branches in the receipt summary helper."""

    def test_summarize_ledger_receipts_missing_file(self):
        summary = cli._summarize_ledger_receipts(Path("/nonexistent/receipts.jsonl"))

        self.assertEqual(
            summary,
            {
                "receipt_count": 0,
                "ai_receipt_count": 0,
                "signed_receipt_count": 0,
                "unsigned_receipt_count": 0,
            },
        )

    def test_summarize_ledger_receipts_loader_error(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "receipts.jsonl"
            ledger.write_text("{}\n", encoding="utf-8")
            with patch(
                "aiir.cli._load_receipts_from_ledger",
                side_effect=ValueError("bad ledger"),
            ):
                summary = cli._summarize_ledger_receipts(ledger)

        self.assertEqual(
            summary,
            {
                "receipt_count": 0,
                "ai_receipt_count": 0,
                "signed_receipt_count": 0,
                "unsigned_receipt_count": 0,
            },
        )

    def test_summarize_ledger_receipts_uses_index_counts(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "receipts.jsonl"
            ledger.write_text("{}\n", encoding="utf-8")
            with patch(
                "aiir.cli._load_index",
                return_value={
                    "receipt_count": 3,
                    "ai_commit_count": 2,
                    "signed_receipt_count": 2,
                    "unsigned_receipt_count": 1,
                },
            ):
                summary = cli._summarize_ledger_receipts(ledger)

        self.assertEqual(
            summary,
            {
                "receipt_count": 3,
                "ai_receipt_count": 2,
                "signed_receipt_count": 2,
                "unsigned_receipt_count": 1,
            },
        )

    def test_summarize_ledger_receipts_falls_back_when_index_unreadable(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "receipts.jsonl"
            ledger.write_text("{}\n", encoding="utf-8")
            receipts = [
                {
                    "ai_attestation": {"is_ai_authored": True},
                    "extensions": {
                        "sigstore_bundle": {
                            "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                            "verificationMaterial": {
                                "certificate": {"rawBytes": "QQ=="}
                            },
                            "messageSignature": {"signature": "Zm9v"},
                        }
                    },
                },
                {
                    "ai_attestation": {"is_ai_authored": False},
                    "extensions": {},
                },
            ]
            with (
                patch("aiir.cli._load_index", side_effect=OSError("index missing")),
                patch("aiir.cli._load_receipts_from_ledger", return_value=receipts),
            ):
                summary = cli._summarize_ledger_receipts(ledger)

        self.assertEqual(
            summary,
            {
                "receipt_count": 2,
                "ai_receipt_count": 1,
                "signed_receipt_count": 1,
                "unsigned_receipt_count": 1,
            },
        )


class TestReceiptOnlyLedgerHelpers(unittest.TestCase):
    """Test receipt-only ledger helper edge cases."""

    def test_receipt_only_touches_ledger_rejects_non_dict_commit(self):
        self.assertFalse(cli._receipt_only_touches_ledger({"commit": None}, ".aiir"))

    def test_receipt_only_touches_ledger_accepts_dict_wrapped_files(self):
        receipt = {
            "commit": {
                "files": {
                    "files": [
                        ".aiir/index.json",
                        ".aiir/receipts/receipt_deadbeef.json",
                    ]
                }
            }
        }

        self.assertTrue(cli._receipt_only_touches_ledger(receipt, ".aiir"))

    def test_receipt_only_touches_ledger_rejects_empty_or_invalid_files(self):
        self.assertFalse(
            cli._receipt_only_touches_ledger({"commit": {"files": []}}, ".aiir")
        )
        self.assertFalse(
            cli._receipt_only_touches_ledger(
                {"commit": {"files": {"files": "bad"}}}, ".aiir"
            )
        )

    def test_receipt_only_touches_ledger_rejects_empty_ledger_root(self):
        receipt = {"commit": {"files": [".aiir/index.json"]}}

        self.assertFalse(cli._receipt_only_touches_ledger(receipt, "/"))

    def test_receipt_only_touches_ledger_rejects_non_string_or_non_ledger_paths(self):
        self.assertFalse(
            cli._receipt_only_touches_ledger({"commit": {"files": [123]}}, ".aiir")
        )
        self.assertFalse(
            cli._receipt_only_touches_ledger(
                {"commit": {"files": [".aiir/index.json", "src/app.py"]}}, ".aiir"
            )
        )


# ---------------------------------------------------------------------------
# Integration test with real git repo
# ---------------------------------------------------------------------------


class TestIntegrationWithGit(unittest.TestCase):
    """Integration tests using a temporary git repo."""

    def setUp(self):
        """Create a temporary git repo with a commit."""
        self.tmpdir = tempfile.mkdtemp()
        self._git(["init"])
        self._git(["config", "user.name", "Test User"])
        self._git(["config", "user.email", "test@example.com"])
        # Create initial commit
        Path(self.tmpdir, "README.md").write_text("# Test\n")
        self._git(["add", "README.md"])
        self._git(["commit", "-m", "initial commit"])

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _git(self, args):
        result = subprocess.run(
            ["git"] + args,
            cwd=self.tmpdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def test_receipt_head(self):
        """Generate a receipt for HEAD in a real git repo."""
        receipt = cli.generate_receipt("HEAD", cwd=self.tmpdir)
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt["commit"]["subject"], "initial commit")
        self.assertEqual(receipt["commit"]["author"]["name"], "Test User")

    def test_root_commit_handled(self):
        """VULN-12: Root commit (no parent) should not crash."""
        # The initial commit IS a root commit — this should work
        receipt = cli.generate_receipt("HEAD", cwd=self.tmpdir)
        self.assertIsNotNone(receipt)
        self.assertIn("diff_hash", receipt["commit"])

    def test_ai_commit_detected(self):
        """AI-authored commit should be flagged."""
        Path(self.tmpdir, "ai_code.py").write_text("print('hello')\n")
        self._git(["add", "ai_code.py"])
        self._git(["commit", "-m", "feat: add code\n\nCo-authored-by: Copilot"])
        receipt = cli.generate_receipt("HEAD", cwd=self.tmpdir)
        self.assertIsNotNone(receipt)
        self.assertTrue(receipt["ai_attestation"]["is_ai_authored"])

    def test_ai_only_filter(self):
        """--ai-only should skip non-AI commits."""
        receipt = cli.generate_receipt("HEAD", cwd=self.tmpdir, ai_only=True)
        self.assertIsNone(receipt)  # "initial commit" has no AI signals

    def test_receipt_verify_round_trip(self):
        """Build receipt from real commit, verify it."""
        receipt = cli.generate_receipt("HEAD", cwd=self.tmpdir)
        result = cli.verify_receipt(receipt)
        self.assertTrue(result["valid"])

    def test_pipe_in_author_name(self):
        """VULN-01: Author name containing | should parse correctly."""
        self._git(["config", "user.name", "Evil|User|Name"])
        Path(self.tmpdir, "evil.txt").write_text("test\n")
        self._git(["add", "evil.txt"])
        self._git(["commit", "-m", "test pipe"])
        receipt = cli.generate_receipt("HEAD", cwd=self.tmpdir)
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt["commit"]["author"]["name"], "Evil|User|Name")

    def test_range_with_multiple_commits(self):
        """Receipt multiple commits in a range."""
        for i in range(3):
            Path(self.tmpdir, f"file{i}.txt").write_text(f"content {i}\n")
            self._git(["add", f"file{i}.txt"])
            self._git(["commit", "-m", f"commit {i}"])

        receipts = cli.generate_receipts_for_range("HEAD~3..HEAD", cwd=self.tmpdir)
        self.assertEqual(len(receipts), 3)

    def test_option_injection_rejected(self):
        """VULN-03: --all as a ref should be rejected."""
        with self.assertRaises(ValueError):
            cli.generate_receipt("--all", cwd=self.tmpdir)

    def test_option_injection_range_rejected(self):
        """VULN-03: --all as a range should be rejected."""
        with self.assertRaises(ValueError):
            cli.generate_receipts_for_range("--all", cwd=self.tmpdir)


class TestDoctorCommand(unittest.TestCase):
    """Tests for the public --doctor CLI surface."""

    def setUp(self):
        self._cwd = os.getcwd()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        os.chdir(self._cwd)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _chdir(self):
        os.chdir(self.tmpdir)

    def _git(self, args):
        result = subprocess.run(
            ["git"] + args,
            cwd=self.tmpdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def _init_repo(self):
        self._git(["init"])
        self._git(["config", "user.name", "Test User"])
        self._git(["config", "user.email", "test@example.com"])
        Path(self.tmpdir, "README.md").write_text("# Test\n", encoding="utf-8")
        self._git(["add", "README.md"])
        self._git(["commit", "-m", "initial commit"])

    def _doctor_json(self, *args):
        import io

        captured_out = io.StringIO()
        captured_err = io.StringIO()
        with patch("sys.stdout", captured_out), patch("sys.stderr", captured_err):
            code = cli.main(["--doctor", "--json", *args])
        return code, json.loads(captured_out.getvalue()), captured_err.getvalue()

    def test_doctor_json_outside_repo_has_stable_missing_state(self):
        """Doctor JSON should stay stable even outside a git repository."""
        self._chdir()

        code, payload, stderr = self._doctor_json()

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(
            set(payload),
            {
                "cli_available",
                "cli_version",
                "git_available",
                "branch",
                "head_sha",
                "aiir_dir_exists",
                "ledger_exists",
                "index_exists",
                "policy_exists",
                "managed_hook_state",
                "head_receipt_status",
                "provenance_queue_exists",
            },
        )
        self.assertTrue(payload["cli_available"])
        self.assertIsNone(payload["branch"])
        self.assertIsNone(payload["head_sha"])
        self.assertFalse(payload["aiir_dir_exists"])
        self.assertFalse(payload["ledger_exists"])
        self.assertFalse(payload["index_exists"])
        self.assertFalse(payload["policy_exists"])
        self.assertEqual(payload["managed_hook_state"], "unknown")
        self.assertEqual(payload["head_receipt_status"], "unknown")
        self.assertFalse(payload["provenance_queue_exists"])

    def test_doctor_human_output_reports_initialized_repo_state(self):
        """Doctor should describe initialized repo state in human-readable form."""
        import io

        self._init_repo()
        aiir_dir = Path(self.tmpdir, ".aiir")
        aiir_dir.mkdir()
        (aiir_dir / "receipts.jsonl").write_text("", encoding="utf-8")
        (aiir_dir / "index.json").write_text(
            json.dumps({"receipt_count": 0, "commits": {}}, indent=2) + "\n",
            encoding="utf-8",
        )
        (aiir_dir / "policy.json").write_text("{}\n", encoding="utf-8")
        (aiir_dir / "editor_provenance.jsonl").write_text("{}\n", encoding="utf-8")
        self._chdir()

        captured_err = io.StringIO()
        with patch("sys.stderr", captured_err):
            code = cli.main(["--doctor"])

        report = captured_err.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("AIIR doctor", report)
        self.assertIn("CLI version:", report)
        self.assertIn("Git: available", report)
        self.assertIn(".aiir/: present", report)
        self.assertIn("Ledger: present", report)
        self.assertIn("Index: present", report)
        self.assertIn("Policy: present", report)
        self.assertIn("Managed hook: missing", report)
        self.assertIn("HEAD receipt: missing", report)
        self.assertIn("Provenance queue: present", report)

    def test_doctor_json_reports_managed_hook_and_head_receipt(self):
        """Doctor JSON should report managed hook state and HEAD receipt coverage."""
        self._init_repo()
        head_sha = self._git(["rev-parse", "HEAD"])
        aiir_dir = Path(self.tmpdir, ".aiir")
        aiir_dir.mkdir()
        (aiir_dir / "receipts.jsonl").write_text(
            json.dumps({"commit": {"sha": head_sha}}) + "\n",
            encoding="utf-8",
        )
        (aiir_dir / "index.json").write_text(
            json.dumps(
                {
                    "receipt_count": 1,
                    "commits": {head_sha: {"receipt_id": "g1-test", "line": 1}},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        hook_path = Path(self.tmpdir, ".git", "hooks", "post-commit")
        hook_path.write_text(
            "#!/bin/sh\n"
            "# >>> AIIR managed post-commit hook >>>\n"
            "aiir --pretty --skip-receipt-only-commits >/dev/null 2>&1 || aiir --pretty --skip-receipt-only-commits\n"
            "# <<< AIIR managed post-commit hook <<<\n",
            encoding="utf-8",
        )
        self._chdir()

        code, payload, _ = self._doctor_json()

        self.assertEqual(code, 0)
        self.assertEqual(payload["managed_hook_state"], "managed")
        self.assertEqual(payload["head_receipt_status"], "present")
        self.assertEqual(payload["head_sha"], head_sha)
        self.assertTrue(payload["ledger_exists"])
        self.assertTrue(payload["index_exists"])

    def test_doctor_json_reports_custom_hook(self):
        """Doctor should distinguish custom hooks from managed AIIR hooks."""
        self._init_repo()
        hook_path = Path(self.tmpdir, ".git", "hooks", "post-commit")
        hook_path.write_text("#!/bin/sh\necho custom\n", encoding="utf-8")
        self._chdir()

        code, payload, _ = self._doctor_json()

        self.assertEqual(code, 0)
        self.assertEqual(payload["managed_hook_state"], "custom")
        self.assertEqual(payload["head_receipt_status"], "missing")

    def test_doctor_json_handles_missing_git(self):
        """Doctor should report missing git cleanly without a traceback."""
        self._chdir()

        def _fake_run_git(args, cwd=None):
            if args == ["--version"]:
                raise FileNotFoundError("git")
            raise AssertionError("unexpected git invocation")

        with patch("aiir.cli._run_git", side_effect=_fake_run_git):
            code, payload, _ = self._doctor_json()

        self.assertEqual(code, 0)
        self.assertFalse(payload["git_available"])
        self.assertIsNone(payload["branch"])
        self.assertIsNone(payload["head_sha"])
        self.assertEqual(payload["managed_hook_state"], "unknown")
        self.assertEqual(payload["head_receipt_status"], "unknown")


class TestHookLifecycleCommand(unittest.TestCase):
    """Tests for public CLI-managed hook lifecycle."""

    def setUp(self):
        self._cwd = os.getcwd()
        self.tmpdir = tempfile.mkdtemp()
        self._git(["init"])
        self._git(["config", "user.name", "Test User"])
        self._git(["config", "user.email", "test@example.com"])
        Path(self.tmpdir, "README.md").write_text("# Test\n", encoding="utf-8")
        self._git(["add", "README.md"])
        self._git(["commit", "-m", "initial commit"])
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self._cwd)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _git(self, args):
        result = subprocess.run(
            ["git"] + args,
            cwd=self.tmpdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def _hook_path(self):
        return Path(self.tmpdir, ".git", "hooks", "post-commit")

    def _run_cli(self, args):
        import io

        captured_out = io.StringIO()
        captured_err = io.StringIO()
        with patch("sys.stdout", captured_out), patch("sys.stderr", captured_err):
            code = cli.main(args)
        return code, captured_out.getvalue(), captured_err.getvalue()

    def test_install_hook_creates_managed_hook_file(self):
        """Installing with no existing hook should create the managed hook file."""
        code, out, err = self._run_cli(["--install-hook"])

        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertIn("Installed managed AIIR post-commit hook", err)
        hook_text = self._hook_path().read_text(encoding="utf-8")
        self.assertIn("# >>> AIIR managed post-commit hook >>>", hook_text)
        self.assertIn("aiir --pretty --skip-receipt-only-commits", hook_text)

    def test_install_hook_updates_existing_managed_block(self):
        """Installing again should update the existing managed block in place."""
        hook_path = self._hook_path()
        hook_path.write_text(
            "#!/bin/sh\n\n"
            "# >>> AIIR managed post-commit hook >>>\n"
            "old command\n"
            "# <<< AIIR managed post-commit hook <<<\n",
            encoding="utf-8",
        )

        code, _, err = self._run_cli(["--install-hook"])

        self.assertEqual(code, 0)
        self.assertIn("Updated existing managed AIIR hook block", err)
        hook_text = hook_path.read_text(encoding="utf-8")
        self.assertNotIn("old command", hook_text)
        self.assertEqual(hook_text.count("# >>> AIIR managed post-commit hook >>>"), 1)

    def test_install_hook_requires_explicit_choice_for_custom_shell_hook(self):
        """A custom shell hook should not be changed without an explicit flag."""
        self._hook_path().write_text("#!/bin/sh\necho custom\n", encoding="utf-8")

        code, _, err = self._run_cli(["--install-hook"])

        self.assertEqual(code, 1)
        self.assertIn("--hook-append", err)
        self.assertIn("--hook-replace", err)
        self.assertNotIn(
            "AIIR managed post-commit hook",
            self._hook_path().read_text(encoding="utf-8"),
        )

    def test_install_hook_append_preserves_custom_shell_hook(self):
        """Appending should keep existing shell hook content and add the managed block."""
        self._hook_path().write_text("#!/bin/sh\necho custom\n", encoding="utf-8")

        code, _, err = self._run_cli(["--install-hook", "--hook-append"])

        self.assertEqual(code, 0)
        self.assertIn("Appended managed AIIR hook block", err)
        hook_text = self._hook_path().read_text(encoding="utf-8")
        self.assertIn("echo custom", hook_text)
        self.assertIn("# >>> AIIR managed post-commit hook >>>", hook_text)

    def test_install_hook_replace_replaces_non_shell_hook(self):
        """Replacing should allow explicit takeover of a non-shell hook."""
        self._hook_path().write_text("MZ binary-ish hook", encoding="utf-8")

        code, out, _ = self._run_cli(["--install-hook", "--hook-replace", "--json"])

        payload = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "replaced")
        self.assertEqual(payload["managed_hook_state"], "managed")
        hook_text = self._hook_path().read_text(encoding="utf-8")
        self.assertIn("# Managed by AIIR CLI.", hook_text)
        self.assertNotIn("MZ binary-ish hook", hook_text)

    def test_install_hook_replace_distinguishes_scripted_non_shell_hooks(self):
        """A non-shell shebang should take the non-shell replacement branch."""
        self._hook_path().write_text(
            "#!/usr/bin/env python3\nprint('custom hook')\n",
            encoding="utf-8",
        )

        code, out, _ = self._run_cli(["--install-hook", "--hook-replace", "--json"])

        payload = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(
            payload["detail"], "Replaced existing non-shell post-commit hook."
        )

    def test_install_hook_rejects_conflicting_append_and_replace_flags(self):
        """Install mode should reject append and replace together."""
        code, _, err = self._run_cli(
            ["--install-hook", "--hook-append", "--hook-replace"]
        )

        self.assertEqual(code, 1)
        self.assertIn("Choose only one of --hook-append or --hook-replace", err)

    def test_remove_hook_preserves_custom_content(self):
        """Removing should strip only the managed block when custom content remains."""
        self._hook_path().write_text(
            "#!/bin/sh\n"
            "echo custom\n\n"
            "# >>> AIIR managed post-commit hook >>>\n"
            "aiir --pretty --skip-receipt-only-commits >/dev/null 2>&1 || aiir --pretty --skip-receipt-only-commits\n"
            "# <<< AIIR managed post-commit hook <<<\n",
            encoding="utf-8",
        )

        code, _, err = self._run_cli(["--remove-hook"])

        self.assertEqual(code, 0)
        self.assertIn("Removed managed AIIR hook block", err)
        hook_text = self._hook_path().read_text(encoding="utf-8")
        self.assertIn("echo custom", hook_text)
        self.assertNotIn("# >>> AIIR managed post-commit hook >>>", hook_text)

    def test_remove_hook_deletes_managed_only_hook_file(self):
        """Removing the only managed block should delete the hook file entirely."""
        self._run_cli(["--install-hook"])

        code, out, _ = self._run_cli(["--remove-hook", "--json"])

        payload = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "removed")
        self.assertFalse(self._hook_path().exists())

    def test_remove_hook_reports_absent_for_custom_only_hook(self):
        """Removing should be a clean no-op when no managed block exists."""
        self._hook_path().write_text("#!/bin/sh\necho custom\n", encoding="utf-8")

        code, out, _ = self._run_cli(["--remove-hook", "--json"])

        payload = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "absent")
        self.assertEqual(payload["managed_hook_state"], "custom")

    def test_remove_hook_reports_absent_when_hook_file_is_missing(self):
        """Removing should report missing state when no hook file exists."""
        code, out, _ = self._run_cli(["--remove-hook", "--json"])

        payload = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "absent")
        self.assertEqual(payload["managed_hook_state"], "missing")

    def test_install_hook_jsonl_rejected(self):
        """Hook lifecycle commands only support object JSON output."""
        code, _, err = self._run_cli(["--install-hook", "--jsonl"])

        self.assertEqual(code, 1)
        self.assertIn("support --json, not --jsonl", err)

    def test_install_hook_reports_read_errors(self):
        """Hook install should surface filesystem read failures cleanly."""
        self._hook_path().write_text("#!/bin/sh\necho custom\n", encoding="utf-8")

        with patch.object(Path, "read_text", side_effect=OSError("boom")):
            code, _, err = self._run_cli(["--install-hook"])

        self.assertEqual(code, 1)
        self.assertIn("Could not read post-commit hook", err)

    def test_install_hook_reports_repo_root_resolution_errors(self):
        """Hook lifecycle should fail cleanly when the repo root cannot be resolved."""
        with patch("aiir.cli.get_repo_root", side_effect=RuntimeError("not a repo")):
            code, _, err = self._run_cli(["--install-hook"])

        self.assertEqual(code, 1)
        self.assertIn("not a repo", err)

    def test_remove_hook_reports_unlink_errors(self):
        """Hook removal should surface filesystem unlink failures cleanly."""
        self._run_cli(["--install-hook"])

        with patch.object(Path, "unlink", side_effect=OSError("boom")):
            code, _, err = self._run_cli(["--remove-hook"])

        self.assertEqual(code, 1)
        self.assertIn("Could not remove post-commit hook", err)


class TestDoctorAndHookHelpers(unittest.TestCase):
    """Direct helper coverage for managed hook and doctor-state edge paths."""

    def test_doctor_resolve_ledger_dir_keeps_absolute_path(self):
        base_dir = Path("/tmp/base")
        ledger_dir = cli._doctor_resolve_ledger_dir(base_dir, "/tmp/custom-ledger")
        self.assertEqual(ledger_dir, Path("/tmp/custom-ledger"))

    def test_get_post_commit_hook_path_keeps_absolute_git_path(self):
        with patch(
            "aiir.cli._run_git", return_value="/tmp/repo/.git/hooks/post-commit\n"
        ):
            hook_path = cli._get_post_commit_hook_path(Path("/tmp/repo"))

        self.assertEqual(hook_path, Path("/tmp/repo/.git/hooks/post-commit"))

    def test_looks_like_shell_hook_accepts_empty_content(self):
        self.assertTrue(cli._looks_like_shell_hook(""))

    def test_write_post_commit_hook_ignores_chmod_errors(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hook_path = Path(tmpdir, "hooks", "post-commit")

            with patch("aiir.cli.os.chmod", side_effect=OSError("boom")):
                cli._write_post_commit_hook(hook_path, "#!/bin/sh\n")

            self.assertEqual(hook_path.read_text(encoding="utf-8"), "#!/bin/sh\n")

    def test_install_managed_hook_requires_replace_for_non_shell_script(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            hook_path = repo_root / ".git" / "hooks" / "post-commit"
            hook_path.parent.mkdir(parents=True, exist_ok=True)
            hook_path.write_text(
                "#!/usr/bin/env python3\nprint('custom hook')\n",
                encoding="utf-8",
            )

            with (
                patch("aiir.cli._get_post_commit_hook_path", return_value=hook_path),
                self.assertRaisesRegex(
                    ValueError, "Existing non-shell post-commit hook found"
                ),
            ):
                cli._install_managed_post_commit_hook(repo_root)

    def test_remove_managed_hook_reports_read_errors(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            hook_path = repo_root / ".git" / "hooks" / "post-commit"
            hook_path.parent.mkdir(parents=True, exist_ok=True)
            hook_path.write_text("#!/bin/sh\n", encoding="utf-8")

            with (
                patch("aiir.cli._get_post_commit_hook_path", return_value=hook_path),
                patch.object(Path, "read_text", side_effect=OSError("boom")),
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "Could not read post-commit hook"
                ):
                    cli._remove_managed_post_commit_hook(repo_root)

    def test_doctor_detect_hook_state_returns_unknown_on_path_resolution_error(self):
        with patch(
            "aiir.cli._get_post_commit_hook_path", side_effect=RuntimeError("boom")
        ):
            self.assertEqual(
                cli._doctor_detect_hook_state(Path("/tmp/repo")), "unknown"
            )

    def test_doctor_detect_hook_state_returns_unknown_on_read_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            hook_path = repo_root / ".git" / "hooks" / "post-commit"
            hook_path.parent.mkdir(parents=True, exist_ok=True)
            hook_path.write_text("#!/bin/sh\n", encoding="utf-8")

            with (
                patch("aiir.cli._get_post_commit_hook_path", return_value=hook_path),
                patch.object(Path, "read_text", side_effect=OSError("boom")),
            ):
                self.assertEqual(cli._doctor_detect_hook_state(repo_root), "unknown")

    def test_doctor_detect_head_receipt_status_skips_invalid_index_and_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_dir = Path(tmpdir)
            (ledger_dir / "index.json").write_text("not-json", encoding="utf-8")
            (ledger_dir / "receipts.jsonl").write_text(
                "\n"
                "{bad json}\n"
                + json.dumps({"commit": {"sha": "0" * 40}})
                + "\n"
                + json.dumps({"commit": {"sha": "a" * 40}})
                + "\n",
                encoding="utf-8",
            )

            status = cli._doctor_detect_head_receipt_status("a" * 40, ledger_dir)

        self.assertEqual(status, "present")

    def test_doctor_detect_head_receipt_status_tolerates_non_matching_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_dir = Path(tmpdir)
            (ledger_dir / "index.json").write_text(
                json.dumps({"commits": {}}),
                encoding="utf-8",
            )

            status = cli._doctor_detect_head_receipt_status("a" * 40, ledger_dir)

        self.assertEqual(status, "missing")

    def test_doctor_detect_head_receipt_status_handles_index_loader_errors(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_dir = Path(tmpdir)
            (ledger_dir / "index.json").write_text("{}", encoding="utf-8")

            with patch("aiir.cli._load_index", side_effect=ValueError("boom")):
                status = cli._doctor_detect_head_receipt_status("a" * 40, ledger_dir)

        self.assertEqual(status, "missing")

    def test_doctor_detect_head_receipt_status_skips_non_dict_index_payloads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_dir = Path(tmpdir)
            (ledger_dir / "index.json").write_text("{}", encoding="utf-8")

            with patch("aiir.cli._load_index", return_value=[]):
                status = cli._doctor_detect_head_receipt_status("a" * 40, ledger_dir)

        self.assertEqual(status, "missing")

    def test_doctor_detect_head_receipt_status_prefers_index_hit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_dir = Path(tmpdir)
            head_sha = "a" * 40
            (ledger_dir / "index.json").write_text("{}", encoding="utf-8")

            with patch(
                "aiir.cli._load_index", return_value={"commits": {head_sha: {}}}
            ):
                status = cli._doctor_detect_head_receipt_status(head_sha, ledger_dir)

        self.assertEqual(status, "present")

    def test_doctor_detect_head_receipt_status_reports_ledger_read_errors(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_dir = Path(tmpdir)
            ledger_path = ledger_dir / "receipts.jsonl"
            ledger_path.write_text("", encoding="utf-8")

            with patch.object(Path, "open", side_effect=OSError("boom")):
                status = cli._doctor_detect_head_receipt_status("a" * 40, ledger_dir)

        self.assertEqual(status, "unknown")

    def test_collect_doctor_state_marks_git_available_on_runtime_error(self):
        with (
            patch("aiir.cli._run_git", side_effect=RuntimeError("git weird")),
            patch("aiir.cli.get_repo_root", side_effect=RuntimeError("not a repo")),
        ):
            state = cli._collect_doctor_state()

        self.assertTrue(state["git_available"])
        self.assertIsNone(state["branch"])

    def test_collect_doctor_state_handles_branch_and_head_lookup_failures(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            aiir_dir = repo_root / ".aiir"
            aiir_dir.mkdir()
            (aiir_dir / "policy.json").write_text("{}", encoding="utf-8")

            with (
                patch(
                    "aiir.cli._run_git",
                    side_effect=[
                        "git version 2.0.0",
                        RuntimeError("branch boom"),
                        RuntimeError("head boom"),
                    ],
                ),
                patch("aiir.cli.get_repo_root", return_value=str(repo_root)),
                patch("aiir.cli._doctor_detect_hook_state", return_value="missing"),
                patch(
                    "aiir.cli._doctor_detect_head_receipt_status",
                    return_value="unknown",
                ),
            ):
                state = cli._collect_doctor_state(str(aiir_dir))

        self.assertIsNone(state["branch"])
        self.assertIsNone(state["head_sha"])

    def test_collect_doctor_state_ignores_empty_branch_and_head(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)

            with (
                patch(
                    "aiir.cli._run_git",
                    side_effect=["git version 2.0.0", "", ""],
                ),
                patch("aiir.cli.get_repo_root", return_value=str(repo_root)),
                patch("aiir.cli._doctor_detect_hook_state", return_value="missing"),
                patch(
                    "aiir.cli._doctor_detect_head_receipt_status",
                    return_value="unknown",
                ),
            ):
                state = cli._collect_doctor_state()

        self.assertIsNone(state["branch"])
        self.assertIsNone(state["head_sha"])


# ---------------------------------------------------------------------------
# Red-team round 2 tests (HACK-02 through HACK-11)
# ---------------------------------------------------------------------------


class TestSignalListValidation(unittest.TestCase):
    """R9-SEC-01: Signal list items validated for type and capped in pretty formatter."""

    def test_non_string_signals_filtered(self):
        """Non-scalar signal types (dicts, lists) should be excluded."""
        receipt = {
            "receipt_id": "g1-test",
            "content_hash": "sha256:test",
            "timestamp": "2026-01-01T00:00:00Z",
            "commit": {
                "sha": "abc123",
                "subject": "test",
                "author": {"name": "test", "email": "t@t"},
                "files_changed": 1,
            },
            "ai_attestation": {
                "is_ai_authored": True,
                "signals_detected": [
                    "message_match:copilot",
                    {"injected": "dict"},
                    ["injected", "list"],
                    None,
                ],
            },
        }
        output = cli.format_receipt_pretty(receipt)
        self.assertIn("copilot", output)
        self.assertNotIn("injected", output)
        self.assertNotIn("None", output)

    def test_long_signal_truncated(self):
        """Signal strings longer than 80 chars should be truncated."""
        long_signal = "x" * 200
        receipt = {
            "receipt_id": "g1-test",
            "content_hash": "sha256:test",
            "timestamp": "2026-01-01T00:00:00Z",
            "commit": {
                "sha": "abc123",
                "subject": "test",
                "author": {"name": "test", "email": "t@t"},
                "files_changed": 1,
            },
            "ai_attestation": {
                "is_ai_authored": True,
                "signals_detected": [long_signal],
            },
        }
        output = cli.format_receipt_pretty(receipt)
        # The signal in the output should be at most 80 chars
        ai_line = [l for l in output.split("\n") if "AI:" in l][0]
        # Extract the signal part between parentheses
        # Should NOT contain the full 200-char string
        self.assertNotIn("x" * 200, ai_line)
        self.assertIn("x" * 80, ai_line)


class TestFormatReceiptDetail(unittest.TestCase):
    """Tests for format_receipt_detail — detailed human-readable output."""

    FULL_RECEIPT = {
        "type": "aiir.commit_receipt",
        "schema": "aiir/commit_receipt.v1",
        "version": "1.0.10",
        "commit": {
            "sha": "abcdef1234567890abcdef1234567890abcdef12",
            "author": {
                "name": "Jane Dev",
                "email": "jane@example.com",
                "date": "2026-03-08T10:00:00-05:00",
            },
            "committer": {
                "name": "CI Bot",
                "email": "ci@example.com",
                "date": "2026-03-08T10:01:00-05:00",
            },
            "subject": "feat: add auth middleware",
            "message_hash": "sha256:aaa111",
            "diff_hash": "sha256:bbb222",
            "files_changed": 3,
            "files": ["src/auth.py", "tests/test_auth.py", "README.md"],
        },
        "ai_attestation": {
            "is_ai_authored": True,
            "signals_detected": ["message_match:co-authored-by: copilot"],
            "signal_count": 1,
            "is_bot_authored": False,
            "bot_signals_detected": [],
            "bot_signal_count": 0,
            "authorship_class": "ai_assisted",
            "detection_method": "heuristic_v2",
        },
        "provenance": {
            "repository": "https://github.com/example/repo",
            "tool": "https://github.com/invariant-systems-ai/aiir@1.0.10",
            "generator": "aiir.cli",
        },
        "receipt_id": "g1-test-detail-receipt",
        "content_hash": "sha256:deadbeef1234",
        "timestamp": "2026-03-08T15:01:00Z",
        "extensions": {"namespace": "prod"},
    }

    def test_includes_schema_identity(self):
        output = cli.format_receipt_detail(self.FULL_RECEIPT)
        self.assertIn("aiir.commit_receipt", output)
        self.assertIn("aiir/commit_receipt.v1", output)
        self.assertIn("1.0.10", output)

    def test_includes_full_sha(self):
        """Detail mode shows the full 40-char SHA, not truncated."""
        output = cli.format_receipt_detail(self.FULL_RECEIPT)
        self.assertIn("abcdef1234567890abcdef1234567890abcdef12", output)

    def test_includes_committer(self):
        output = cli.format_receipt_detail(self.FULL_RECEIPT)
        self.assertIn("CI Bot", output)
        self.assertIn("ci@example.com", output)

    def test_includes_hashes(self):
        output = cli.format_receipt_detail(self.FULL_RECEIPT)
        self.assertIn("sha256:aaa111", output)
        self.assertIn("sha256:bbb222", output)

    def test_includes_file_list(self):
        output = cli.format_receipt_detail(self.FULL_RECEIPT)
        self.assertIn("src/auth.py", output)
        self.assertIn("tests/test_auth.py", output)
        self.assertIn("README.md", output)

    def test_includes_authorship_class(self):
        output = cli.format_receipt_detail(self.FULL_RECEIPT)
        self.assertIn("ai_assisted", output)

    def test_includes_detection_method(self):
        output = cli.format_receipt_detail(self.FULL_RECEIPT)
        self.assertIn("heuristic_v2", output)

    def test_includes_provenance(self):
        output = cli.format_receipt_detail(self.FULL_RECEIPT)
        self.assertIn("https://github.com/example/repo", output)
        self.assertIn("aiir.cli", output)

    def test_includes_extensions(self):
        output = cli.format_receipt_detail(self.FULL_RECEIPT)
        self.assertIn("namespace", output)
        self.assertIn("prod", output)

    def test_includes_signed_line(self):
        output = cli.format_receipt_detail(self.FULL_RECEIPT, signed="YES (sigstore)")
        self.assertIn("YES (sigstore)", output)

    def test_bot_field(self):
        output = cli.format_receipt_detail(self.FULL_RECEIPT)
        # Bot: no should be present
        bot_line = [l for l in output.split("\n") if "Bot:" in l][0]
        self.assertIn("no", bot_line)

    def test_caps_file_list_at_20(self):
        """Receipts with >20 files should be capped to prevent terminal flood."""
        receipt = {**self.FULL_RECEIPT}
        receipt["commit"] = {
            **self.FULL_RECEIPT["commit"],
            "files": [f"file_{i}.py" for i in range(30)],
            "files_changed": 30,
        }
        output = cli.format_receipt_detail(receipt)
        self.assertIn("file_19.py", output)
        self.assertNotIn("file_20.py", output)
        self.assertIn("and 10 more", output)

    def test_survives_empty_receipt(self):
        """Defensive: empty dict should not crash."""
        output = cli.format_receipt_detail({})
        self.assertIn("unknown", output)
        self.assertIsInstance(output, str)

    def test_survives_non_dict_nested_fields(self):
        """Defensive: non-dict commit/ai_attestation should not crash."""
        receipt = {
            "commit": "not a dict",
            "ai_attestation": 42,
            "provenance": ["list"],
            "extensions": "string",
        }
        output = cli.format_receipt_detail(receipt)
        self.assertIsInstance(output, str)

    def test_detail_is_superset_of_pretty(self):
        """Detail output should contain all info from pretty output."""
        pretty = cli.format_receipt_pretty(self.FULL_RECEIPT)
        detail = cli.format_receipt_detail(self.FULL_RECEIPT)
        # Detail has more lines
        self.assertGreater(len(detail.split("\n")), len(pretty.split("\n")))
        # Key fields from pretty are also in detail
        self.assertIn("feat: add auth middleware", detail)
        self.assertIn("Jane Dev", detail)
        self.assertIn("sha256:deadbeef1234", detail)


class TestRedactFilesFlag(unittest.TestCase):
    """I-05-FIX: --redact-files flag omits file paths from receipts."""

    def _make_commit_info(self):
        return cli.CommitInfo(
            sha="a" * 40,
            author_name="Test",
            author_email="t@t",
            author_date="2026-01-01T00:00:00Z",
            committer_name="Test",
            committer_email="t@t",
            committer_date="2026-01-01T00:00:00Z",
            subject="test commit",
            body="test body",
            diff_stat="1 file changed",
            diff_hash="sha256:abc",
            files_changed=["secret/internal.py", "another/path.py"],
            ai_signals_detected=[],
            is_ai_authored=False,
        )

    def test_default_includes_files(self):
        """By default, file paths should be included."""
        commit = self._make_commit_info()
        receipt = cli.build_commit_receipt(commit, redact_files=False)
        self.assertIn("files", receipt["commit"])
        self.assertEqual(
            receipt["commit"]["files"], ["secret/internal.py", "another/path.py"]
        )
        self.assertNotIn("files_redacted", receipt["commit"])

    def test_redact_files_omits_paths(self):
        """With redact_files=True, file paths should be omitted."""
        commit = self._make_commit_info()
        receipt = cli.build_commit_receipt(commit, redact_files=True)
        self.assertNotIn("files", receipt["commit"])
        self.assertTrue(receipt["commit"].get("files_redacted"))
        # files_changed count should still be present
        self.assertEqual(receipt["commit"]["files_changed"], 2)


class TestExitCodeDocumentation(unittest.TestCase):
    """R9-PUB-02: Exit codes documented in --help epilog."""

    def test_help_contains_exit_codes(self):
        """--help output should document exit codes."""
        import io

        buf = io.StringIO()
        try:
            with unittest.mock.patch("sys.stdout", buf):
                cli.main(["--help"])
        except SystemExit:
            pass
        help_text = buf.getvalue()
        self.assertIn("exit codes:", help_text)
        self.assertIn("0", help_text)
        self.assertIn("1", help_text)


class TestUnsignedReceiptWarning(unittest.TestCase):
    """R-03-FIX: CLI warns when generating unsigned receipts."""

    def setUp(self):
        self._old_cwd = os.getcwd()
        self._tmpdir = tempfile.mkdtemp()
        os.chdir(self._tmpdir)

    def tearDown(self):
        os.chdir(self._old_cwd)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    @unittest.mock.patch("aiir.cli.get_repo_root", return_value="/tmp/fakerepo")
    @unittest.mock.patch("aiir.cli.generate_receipt")
    def test_unsigned_warning_printed(self, mock_gen, mock_root):
        """When not signing, a warning about unsigned receipts should appear."""
        import io

        mock_gen.return_value = {
            "type": "aiir.commit_receipt",
            "receipt_id": "g1-test",
            "content_hash": "sha256:test",
            "timestamp": "2026-01-01T00:00:00Z",
            "commit": {"sha": "abc123", "subject": "test"},
            "ai_attestation": {"is_ai_authored": False},
        }
        with unittest.mock.patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            cli.main(["--pretty"])
            stderr_output = mock_err.getvalue()
        self.assertIn("unsigned", stderr_output.lower())
        self.assertIn("--sign", stderr_output)

    @unittest.mock.patch("aiir.cli.get_repo_root", return_value="/tmp/fakerepo")
    @unittest.mock.patch("aiir.cli.generate_receipt")
    def test_quiet_suppresses_unsigned_warning(self, mock_gen, mock_root):
        """With --quiet, no unsigned warning should appear."""
        import io

        mock_gen.return_value = {
            "type": "aiir.commit_receipt",
            "receipt_id": "g1-test",
            "content_hash": "sha256:test",
            "timestamp": "2026-01-01T00:00:00Z",
            "commit": {"sha": "abc123", "subject": "test"},
            "ai_attestation": {"is_ai_authored": False},
        }
        with unittest.mock.patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            cli.main(["--pretty", "--quiet"])
            stderr_output = mock_err.getvalue()
        self.assertNotIn("unsigned", stderr_output.lower())

    @unittest.mock.patch("aiir.cli.get_repo_root", return_value="/tmp/fakerepo")
    @unittest.mock.patch("aiir.cli.generate_receipt")
    def test_default_output_suppresses_privacy_hint(self, mock_gen, mock_root):
        """Default output keeps the privacy reminder off the happy path."""
        import io

        mock_gen.return_value = {
            "type": "aiir.commit_receipt",
            "receipt_id": "g1-test",
            "content_hash": "sha256:test",
            "timestamp": "2026-01-01T00:00:00Z",
            "commit": {"sha": "abc123", "subject": "test"},
            "provenance": {"repository": "https://example.invalid/repo.git"},
            "ai_attestation": {"is_ai_authored": False},
        }
        with unittest.mock.patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            cli.main(["--pretty"])
            stderr_output = mock_err.getvalue()
        self.assertNotIn("--redact-files", stderr_output)

    @unittest.mock.patch("aiir.cli.get_repo_root", return_value="/tmp/fakerepo")
    @unittest.mock.patch("aiir.cli.generate_receipt")
    def test_verbose_keeps_privacy_hint_available(self, mock_gen, mock_root):
        """Verbose mode still exposes the privacy reminder when requested."""
        import io

        mock_gen.return_value = {
            "type": "aiir.commit_receipt",
            "receipt_id": "g1-test",
            "content_hash": "sha256:test",
            "timestamp": "2026-01-01T00:00:00Z",
            "commit": {"sha": "abc123", "subject": "test"},
            "provenance": {"repository": "https://example.invalid/repo.git"},
            "ai_attestation": {"is_ai_authored": False},
        }
        with unittest.mock.patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            cli.main(["--pretty", "--verbose"])
            stderr_output = mock_err.getvalue()
        self.assertIn("--redact-files", stderr_output)
        self.assertIn("--redact-emails", stderr_output)


class TestStdoutClose(unittest.TestCase):
    """R9-TECH-02: _hash_diff_streaming must close stdout pipe."""

    def test_hash_diff_streaming_closes_stdout(self):
        """After _hash_diff_streaming, proc.stdout should be closed."""
        tmpdir = tempfile.mkdtemp()
        try:
            subprocess.run(["git", "init", tmpdir], capture_output=True, check=True)
            subprocess.run(
                ["git", "-C", tmpdir, "config", "user.email", "test@test.com"],
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "-C", tmpdir, "config", "user.name", "Test"],
                capture_output=True,
                check=True,
            )
            Path(tmpdir, "file.txt").write_text("hello\n")
            subprocess.run(
                ["git", "-C", tmpdir, "add", "."], capture_output=True, check=True
            )
            subprocess.run(
                ["git", "-C", tmpdir, "commit", "-m", "first"],
                capture_output=True,
                check=True,
            )
            # Create a second commit so there's a real parent
            Path(tmpdir, "file.txt").write_text("hello world\n")
            subprocess.run(
                ["git", "-C", tmpdir, "add", "."], capture_output=True, check=True
            )
            subprocess.run(
                ["git", "-C", tmpdir, "commit", "-m", "second"],
                capture_output=True,
                check=True,
            )
            sha = subprocess.run(
                ["git", "-C", tmpdir, "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            parent = subprocess.run(
                ["git", "-C", tmpdir, "rev-parse", "HEAD~1"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            # Should succeed without fd leaks
            result = cli._hash_diff_streaming(parent, sha, cwd=tmpdir)
            self.assertTrue(result.startswith("sha256:"))
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)


class TestCfStripping(unittest.TestCase):
    """R9-TECH-03: detect_ai_signals must strip Cf (format characters) from author fields."""

    def test_zwj_in_bot_name_detected(self):
        """A bot name with ZWJ inserted (e.g. 'dep\u200dendabot') must still be detected."""
        _, bot_signals = cli.detect_ai_signals(
            message="Bump lodash from 4.17.20 to 4.17.21",
            author_name="dep\u200dendabot[bot]",  # ZWJ between 'dep' and 'endabot'
            committer_name="GitHub",
        )
        # The ZWJ should be stripped, revealing 'dependabot[bot]'
        bot_found = any("dependabot" in s for s in bot_signals)
        self.assertTrue(bot_found, f"ZWJ in bot name evaded detection: {bot_signals}")

    def test_zwnj_in_committer_stripped(self):
        """ZWNJ (U+200C) should be stripped from committer fields."""
        _, bot_signals = cli.detect_ai_signals(
            message="test commit",
            author_name="human",
            committer_name="git\u200chub-actions[bot]",  # ZWNJ between 'git' and 'hub'
        )
        # Should detect github-actions[bot] pattern
        bot_found = any("github-actions" in s for s in bot_signals)
        self.assertTrue(bot_found, f"ZWNJ in committer evaded detection: {bot_signals}")

    def test_variation_selector_stripped(self):
        """Variation selectors (U+FE0F etc) are Mn/Me but Cf chars like U+200B must also go."""
        import unicodedata

        # Verify ZWS is category Cf
        self.assertEqual(unicodedata.category("\u200b"), "Cf")
        # Verify it's stripped in the field cleaning
        _, bot_signals = cli.detect_ai_signals(
            message="test",
            author_name="dep\u200bendabot[bot]",  # Zero-width space
            committer_name="GitHub",
        )
        bot_found = any("dependabot" in s for s in bot_signals)
        self.assertTrue(
            bot_found, f"ZWS (Cf) in bot name evaded detection: {bot_signals}"
        )


class TestTerminalEscapeSosDcs(unittest.TestCase):
    """R9-TECH-04: _strip_terminal_escapes must strip SOS and DCS sequences."""

    def test_sos_stripped(self):
        """SOS (ESC X ... ST) sequences should be removed."""
        text = "before\x1bXsome SOS payload\x1b\\after"
        result = cli._strip_terminal_escapes(text)
        self.assertNotIn("SOS payload", result)
        self.assertIn("before", result)
        self.assertIn("after", result)

    def test_dcs_stripped(self):
        """DCS (ESC P ... ST) sequences should be removed."""
        text = "before\x1bPsome DCS payload\x1b\\after"
        result = cli._strip_terminal_escapes(text)
        self.assertNotIn("DCS payload", result)
        self.assertIn("before", result)
        self.assertIn("after", result)

    def test_pm_still_stripped(self):
        """Existing PM (ESC ^ ... ST) stripping must still work."""
        text = "before\x1b^PM payload\x1b\\after"
        result = cli._strip_terminal_escapes(text)
        self.assertNotIn("PM payload", result)

    def test_apc_still_stripped(self):
        """Existing APC (ESC _ ... ST) stripping must still work."""
        text = "before\x1b_APC payload\x1b\\after"
        result = cli._strip_terminal_escapes(text)
        self.assertNotIn("APC payload", result)


class TestStripUrlCredentialsSafeFallback(unittest.TestCase):
    """R10-SEC-03: _strip_url_credentials must not leak credentials on exception."""

    def test_normal_stripping_works(self):
        """Credentials in a normal URL should be stripped."""
        result = cli._strip_url_credentials("https://user:token@github.com/org/repo")
        self.assertNotIn("user", result)
        self.assertNotIn("token", result)
        self.assertIn("github.com", result)

    def test_clean_url_passes_through(self):
        """A URL without credentials should pass through unchanged."""
        url = "https://github.com/org/repo.git"
        self.assertEqual(cli._strip_url_credentials(url), url)

    def test_exception_returns_safe_placeholder(self):
        """If URL reconstruction fails, a safe placeholder is returned (not the original)."""
        # Monkeypatch urlunparse to raise
        import aiir._core as _core_mod

        original = _core_mod.urlunparse

        def broken_unparse(*args, **kwargs):
            raise RuntimeError("simulated failure")

        _core_mod.urlunparse = broken_unparse
        try:
            result = cli._strip_url_credentials("https://user:secret@host.com/repo")
            self.assertNotIn("secret", result)
            self.assertIn("redacted", result.lower())
        finally:
            _core_mod.urlunparse = original


class TestMainCatchesOSError(unittest.TestCase):
    """R10-R-03: main() must catch OSError from filesystem failures."""

    @unittest.mock.patch("aiir.cli.get_repo_root")
    def test_oserror_returns_1(self, mock_root):
        """OSError during receipt generation should return exit code 1."""
        import io

        mock_root.side_effect = OSError("Permission denied: .git/HEAD")
        with unittest.mock.patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            exit_code = cli.main([])
        self.assertEqual(exit_code, 1)
        self.assertIn("Permission denied", mock_err.getvalue())


class TestReadmeStats(unittest.TestCase):
    """R10-PUB-01: README bottom stats must match actual control/test counts."""

    def test_readme_stats_not_stale(self):
        """The README security line should have correct stats."""
        readme = (Path(__file__).parent.parent / "README.md").read_text(
            encoding="utf-8"
        )
        # Should NOT have old stale numbers
        self.assertNotIn("73 security controls", readme)
        self.assertNotIn("285 tests", readme)
        self.assertNotIn("78 security controls", readme)
        self.assertNotIn("328 tests", readme)
        self.assertNotIn("89 security controls", readme)
        self.assertNotIn("345 tests", readme)
        self.assertNotIn("95 security controls", readme)
        self.assertNotIn("362 tests", readme)
        self.assertNotIn("96 security controls", readme)
        self.assertNotIn("368 tests", readme)
        self.assertNotIn("103 security controls", readme)
        self.assertNotIn("395 tests", readme)
        self.assertNotIn("407 tests", readme)
        self.assertNotIn("417 tests", readme)
        self.assertNotIn("2,110 collected tests", readme)
        self.assertNotIn("107 security controls", readme)
        self.assertNotIn("2,197 collected tests", readme)
        self.assertNotIn("367 tests", readme)
        self.assertNotIn("1075+ tests", readme)
        self.assertNotIn("1170+ tests", readme)
        self.assertNotIn("1600+ tests", readme)
        self.assertNotIn("1,860 tests", readme)
        self.assertNotIn("1,925 tests", readme)
        self.assertNotIn("2,016 tests", readme)
        self.assertNotIn("2,110 collected tests", readme)
        self.assertNotIn("2,214 collected tests", readme)
        self.assertNotIn("2,197 collected tests", readme)
        self.assertNotIn("153 security controls", readme)

        # Should have current content. The collected-test count is intentionally
        # NOT hardcoded — it drifts on every PR (the oss-hygiene audit finding
        # about the stale "2,499 collected tests" claim). The README now points
        # to CI for the live count instead, and these guards ensure no hardcoded
        # count is reintroduced.
        self.assertIn("security controls", readme)
        self.assertIn("100% test coverage (see CI for current count)", readme)
        self.assertNotRegex(readme, r"\d[\d,]* collected tests")


class TestThreatModelR03Consistency(unittest.TestCase):
    """R10-ACAD-01: R-03 status must be consistent with DREAD residual rating."""

    def test_r03_not_fully_mitigated(self):
        """R-03 should say 'Partially mitigated' since DREAD rates it Medium."""
        tm = (Path(__file__).parent.parent / "THREAT_MODEL.md").read_text(
            encoding="utf-8"
        )
        # Find the R-03 row in Section 3.3
        for line in tm.split("\n"):
            if "| R-03 |" in line and "Unsigned receipts" in line:
                self.assertIn("Partially mitigated", line)
                break
        else:
            self.fail("R-03 row not found in THREAT_MODEL")


# ---------------------------------------------------------------------------
# Round 11 tests
# ---------------------------------------------------------------------------


class TestHashDiffStreamingCleanup(unittest.TestCase):
    """R10-R-02: _hash_diff_streaming must clean up subprocess on exception."""

    def test_cleanup_comment_present(self):
        """The function should have exception cleanup logic."""
        import inspect

        source = inspect.getsource(cli._hash_diff_streaming)
        self.assertIn("proc.kill()", source)
        self.assertIn("try:", source)
        self.assertIn("except", source)


class TestFriendlyPathError(unittest.TestCase):
    """R16-UX-02: ValueError from write_receipt must produce a friendly
    one-line error, not a raw Python traceback."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        subprocess.run(["git", "init", self.tmpdir], capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=self.tmpdir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=self.tmpdir,
            capture_output=True,
            check=True,
        )
        Path(self.tmpdir, "file.txt").write_text("hello")
        subprocess.run(
            ["git", "add", "."], cwd=self.tmpdir, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=self.tmpdir,
            capture_output=True,
            check=True,
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_outside_cwd_output_shows_friendly_error(self):
        """R16-UX-02: --output /tmp/outside should print friendly error not traceback."""
        old_cwd = os.getcwd()
        try:
            os.chdir(self.tmpdir)
            from io import StringIO

            captured_err = StringIO()
            with patch("sys.stderr", captured_err):
                rc = cli.main(["--output", "/tmp/evil-outside-repo"])
            self.assertNotEqual(rc, 0, "Should return non-zero exit code")
            stderr_text = captured_err.getvalue()
            self.assertIn("\u274c", stderr_text, "Should show \u274c emoji prefix")
            self.assertIn("\U0001f4a1", stderr_text, "Should show \U0001f4a1 hint")
            self.assertNotIn("Traceback", stderr_text, "Must not show raw traceback")
        finally:
            os.chdir(old_cwd)

    def test_outside_cwd_with_pretty_shows_friendly_error(self):
        """R16-UX-02: --pretty --output /tmp/evil should also show friendly error."""
        old_cwd = os.getcwd()
        try:
            os.chdir(self.tmpdir)
            from io import StringIO

            captured_err = StringIO()
            with patch("sys.stderr", captured_err):
                rc = cli.main(["--pretty", "--output", "/tmp/evil-outside-repo"])
            self.assertNotEqual(rc, 0)
            stderr_text = captured_err.getvalue()
            self.assertIn("\u274c", stderr_text)
            self.assertNotIn("Traceback", stderr_text)
        finally:
            os.chdir(old_cwd)


class TestVerboseQuietMutualExclusion(unittest.TestCase):
    """R16-UX-03: --verbose and --quiet must be mutually exclusive."""

    def test_verbose_and_quiet_rejected(self):
        """R16-UX-03: Passing both --verbose and --quiet should fail."""
        # argparse mutually exclusive group will cause SystemExit(2)
        with self.assertRaises(SystemExit) as ctx:
            cli.main(["--verbose", "--quiet"])
        self.assertEqual(ctx.exception.code, 2, "argparse should exit with code 2")

    def test_verbose_alone_accepted(self):
        """--verbose alone should be accepted (may fail for other reasons like no git)."""
        # We just check it doesn't raise SystemExit(2) for argument conflict
        try:
            cli.main(["--verbose", "--version"])
        except SystemExit as e:
            # --version causes SystemExit(0), which is fine
            self.assertEqual(e.code, 0)

    def test_quiet_alone_accepted(self):
        """--quiet alone should be accepted."""
        try:
            cli.main(["--quiet", "--version"])
        except SystemExit as e:
            self.assertEqual(e.code, 0)


class TestFriendlyErrors(unittest.TestCase):
    """R17-UX-01: All error messages must use emoji + actionable hint."""

    def test_not_a_git_repo_shows_emoji_and_hint(self):
        """Running aiir outside a git repo should show ❌ + 💡 hint."""
        import tempfile

        tmpdir = tempfile.mkdtemp()
        old_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            from io import StringIO

            captured_err = StringIO()
            with patch("sys.stderr", captured_err):
                rc = cli.main([])
            self.assertEqual(rc, 1)
            stderr_text = captured_err.getvalue()
            self.assertIn("\u274c", stderr_text, "Should show ❌ emoji")
            self.assertIn("\U0001f4a1", stderr_text, "Should show 💡 hint")
            self.assertIn("git", stderr_text.lower(), "Hint should mention git")
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_no_git_binary_shows_emoji_and_hint(self):
        """If git is not on PATH, should show ❌ + 💡 with install link."""
        from io import StringIO

        captured_err = StringIO()
        with patch("aiir.cli.get_repo_root", side_effect=FileNotFoundError("git")):
            with patch("sys.stderr", captured_err):
                rc = cli.main([])
        self.assertEqual(rc, 1)
        stderr_text = captured_err.getvalue()
        self.assertIn("\u274c", stderr_text)
        self.assertIn("git-scm.com", stderr_text, "Should include install link")

    def test_sign_without_output_shows_emoji_and_hint(self):
        """--sign without --output should show ❌ + 💡 Try: ..."""
        import tempfile

        tmpdir = tempfile.mkdtemp()
        old_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True, check=True)
            subprocess.run(
                ["git", "config", "user.email", "t@t.t"],
                cwd=tmpdir,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "T"],
                cwd=tmpdir,
                capture_output=True,
                check=True,
            )
            Path(tmpdir, "f.txt").write_text("x")
            subprocess.run(
                ["git", "add", "."], cwd=tmpdir, capture_output=True, check=True
            )
            subprocess.run(
                ["git", "commit", "-m", "init"],
                cwd=tmpdir,
                capture_output=True,
                check=True,
            )

            from io import StringIO

            captured_err = StringIO()
            with patch("sys.stderr", captured_err):
                rc = cli.main(["--sign"])
            self.assertEqual(rc, 1)
            stderr_text = captured_err.getvalue()
            self.assertIn("\u274c", stderr_text, "Should show ❌")
            self.assertIn("--output", stderr_text, "Hint should suggest --output")
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_timeout_shows_emoji_and_hint(self):
        """Git timeout should show ❌ + 💡 hint."""
        from io import StringIO

        captured_err = StringIO()
        with patch("aiir.cli.get_repo_root", return_value="/tmp"):
            with patch(
                "aiir.cli.generate_receipt",
                side_effect=subprocess.TimeoutExpired("git", 300),
            ):
                with patch("sys.stderr", captured_err):
                    rc = cli.main([])
        self.assertEqual(rc, 1)
        stderr_text = captured_err.getvalue()
        self.assertIn("\u274c", stderr_text, "Should show ❌")
        self.assertIn("too long", stderr_text.lower(), "Should say it took too long")


class TestFriendlyNoReceipts(unittest.TestCase):
    """R17-UX-02: 'No commits' message should show 🤷 + 💡 hint."""

    def test_no_commits_ai_only_shows_hint(self):
        """--ai-only with no AI commits should show remove hint."""
        from io import StringIO

        captured_err = StringIO()
        with patch("aiir.cli.get_repo_root", return_value="/tmp"):
            with patch("aiir.cli.generate_receipt", return_value=None):
                with patch("sys.stderr", captured_err):
                    rc = cli.main(["--ai-only"])
        self.assertEqual(rc, 0)
        stderr_text = captured_err.getvalue()
        self.assertIn("\U0001f937", stderr_text, "Should show 🤷")
        self.assertIn("--ai-only", stderr_text, "Hint should mention --ai-only")

    def test_no_commits_no_flags_shows_hint(self):
        """No commits (no flags) should suggest checking git log."""
        from io import StringIO

        captured_err = StringIO()
        with patch("aiir.cli.get_repo_root", return_value="/tmp"):
            with patch("aiir.cli.generate_receipt", return_value=None):
                with patch("sys.stderr", captured_err):
                    rc = cli.main([])
        self.assertEqual(rc, 0)
        stderr_text = captured_err.getvalue()
        self.assertIn("\U0001f937", stderr_text, "Should show 🤷")
        self.assertIn("git log", stderr_text, "Hint should mention git log")

    def test_no_commits_gitlab_ci_sets_zero_signing_outputs(self):
        """--gitlab-ci with no receipts should still emit zero signing aggregates."""
        with (
            patch("aiir.cli.get_repo_root", return_value="/tmp"),
            patch("aiir.cli.generate_receipt", return_value=None),
            patch("aiir.cli.set_gitlab_ci_output") as set_gitlab_output,
        ):
            rc = cli.main(["--gitlab-ci"])

        self.assertEqual(rc, 0)
        self.assertEqual(set_gitlab_output.call_count, 4)
        set_gitlab_output.assert_any_call("AIIR_RECEIPT_COUNT", "0")
        set_gitlab_output.assert_any_call("AIIR_AI_COMMIT_COUNT", "0")
        set_gitlab_output.assert_any_call("AIIR_SIGNED_RECEIPT_COUNT", "0")
        set_gitlab_output.assert_any_call("AIIR_UNSIGNED_RECEIPT_COUNT", "0")


class TestDidYouMean(unittest.TestCase):
    """R17-UX-05: Misspelled flags should suggest closest match."""

    def test_prettty_suggests_pretty(self):
        """--prettty should suggest --pretty."""
        from io import StringIO

        captured_err = StringIO()
        with self.assertRaises(SystemExit) as ctx:
            with patch("sys.stderr", captured_err):
                cli.main(["--prettty"])
        self.assertEqual(ctx.exception.code, 2)
        stderr_text = captured_err.getvalue()
        self.assertIn("--pretty", stderr_text, "Should suggest --pretty")

    def test_verfy_suggests_verify(self):
        """--verfy should suggest --verify."""
        from io import StringIO

        captured_err = StringIO()
        with self.assertRaises(SystemExit) as ctx:
            with patch("sys.stderr", captured_err):
                cli.main(["--verfy"])
        self.assertEqual(ctx.exception.code, 2)
        stderr_text = captured_err.getvalue()
        self.assertIn("--verify", stderr_text, "Should suggest --verify")

    def test_completely_wrong_flag_no_crash(self):
        """--zzzzz should not crash (no close match)."""
        with self.assertRaises(SystemExit) as ctx:
            cli.main(["--zzzzz"])
        self.assertEqual(ctx.exception.code, 2)


class TestHelpEpilog(unittest.TestCase):
    """R17-UX-04: --help epilog should include usage examples."""

    def test_help_shows_examples(self):
        """--help should contain example commands."""
        from io import StringIO

        captured_out = StringIO()
        with self.assertRaises(SystemExit) as ctx:
            with patch("sys.stdout", captured_out):
                cli.main(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        help_text = captured_out.getvalue()
        self.assertIn("examples:", help_text, "Help should have examples section")
        self.assertIn("aiir --pretty", help_text, "Should show --pretty example")
        self.assertIn("-o .receipts", help_text, "Should show -o example")


class TestFriendlySummary(unittest.TestCase):
    """R17-UX-03: Post-generation summary should use ✅ emoji."""

    def test_summary_has_checkmark(self):
        """Summary line should contain ✅."""
        import tempfile

        tmpdir = tempfile.mkdtemp()
        old_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True, check=True)
            subprocess.run(
                ["git", "config", "user.email", "t@t.t"],
                cwd=tmpdir,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "T"],
                cwd=tmpdir,
                capture_output=True,
                check=True,
            )
            Path(tmpdir, "f.txt").write_text("x")
            subprocess.run(
                ["git", "add", "."], cwd=tmpdir, capture_output=True, check=True
            )
            subprocess.run(
                ["git", "commit", "-m", "init"],
                cwd=tmpdir,
                capture_output=True,
                check=True,
            )

            from io import StringIO

            captured_err = StringIO()
            with patch("sys.stderr", captured_err):
                rc = cli.main(["--pretty"])
            self.assertEqual(rc, 0)
            stderr_text = captured_err.getvalue()
            self.assertIn("\u2705", stderr_text, "Summary should show ✅")
            self.assertIn("receipt", stderr_text.lower())
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_unsigned_tip_has_emoji(self):
        """Unsigned-receipt tip should contain 📝."""
        import tempfile

        tmpdir = tempfile.mkdtemp()
        old_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True, check=True)
            subprocess.run(
                ["git", "config", "user.email", "t@t.t"],
                cwd=tmpdir,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "T"],
                cwd=tmpdir,
                capture_output=True,
                check=True,
            )
            Path(tmpdir, "f.txt").write_text("x")
            subprocess.run(
                ["git", "add", "."], cwd=tmpdir, capture_output=True, check=True
            )
            subprocess.run(
                ["git", "commit", "-m", "init"],
                cwd=tmpdir,
                capture_output=True,
                check=True,
            )

            from io import StringIO

            captured_err = StringIO()
            with patch("sys.stderr", captured_err):
                rc = cli.main(["--pretty"])
            self.assertEqual(rc, 0)
            stderr_text = captured_err.getvalue()
            self.assertIn("\U0001f4dd", stderr_text, "Tip should show 📝")
            self.assertIn("--sign", stderr_text, "Tip should mention --sign")
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestFriendlyVerify(unittest.TestCase):
    """R17-UX-06: Verify output should be friendlier."""

    def test_verify_pass_says_all_good(self):
        """Successful verify should say 'All good!'."""
        import tempfile

        tmpdir = tempfile.mkdtemp()
        old_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True, check=True)
            subprocess.run(
                ["git", "config", "user.email", "t@t.t"],
                cwd=tmpdir,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "T"],
                cwd=tmpdir,
                capture_output=True,
                check=True,
            )
            Path(tmpdir, "f.txt").write_text("x")
            subprocess.run(
                ["git", "add", "."], cwd=tmpdir, capture_output=True, check=True
            )
            subprocess.run(
                ["git", "commit", "-m", "init"],
                cwd=tmpdir,
                capture_output=True,
                check=True,
            )

            # Generate a receipt to a file
            out_dir = Path(tmpdir, ".receipts")
            from io import StringIO

            captured_err = StringIO()
            with patch("sys.stderr", captured_err):
                rc = cli.main(["--output", str(out_dir)])
            self.assertEqual(rc, 0)

            # Find the receipt file
            receipt_files = list(out_dir.glob("receipt_*.json"))
            self.assertTrue(len(receipt_files) > 0, "Should have a receipt file")

            # Verify it
            captured_err2 = StringIO()
            with patch("sys.stderr", captured_err2):
                rc2 = cli.main(["--verify", str(receipt_files[0])])
            self.assertEqual(rc2, 0)
            stderr_text = captured_err2.getvalue()
            self.assertIn("All good", stderr_text, "Should say 'All good'")
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_verify_fail_shows_hint(self):
        """Failed verify should show 💡 hint."""
        import tempfile

        tmpdir = tempfile.mkdtemp()
        try:
            tampered = Path(tmpdir, "bad.json")
            tampered.write_text(
                '{"type":"aiir.commit_receipt","schema":"aiir/commit_receipt.v1","version":"1.0.0","commit":{"sha":"abc"},"ai_attestation":{},"provenance":{},"receipt_id":"g1-wrong","content_hash":"sha256:wrong"}'
            )
            from io import StringIO

            captured_err = StringIO()
            with patch("sys.stderr", captured_err):
                rc = cli.main(["--verify", str(tampered)])
            self.assertEqual(rc, 1)
            stderr_text = captured_err.getvalue()
            self.assertIn("\u274c", stderr_text, "Should show ❌")
            self.assertIn("\U0001f4a1", stderr_text, "Should show 💡 hint")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestVerifyPathBoundary(unittest.TestCase):
    """CLI --verify is intentionally NOT CWD-restricted (unlike MCP).

    The MCP server restricts verify to CWD to prevent AI-assistant oracle
    attacks (F4-02).  CLI --verify is read-only and the user explicitly
    supplies the path, so cross-directory verification is allowed.
    Write operations (--output, --export) ARE CWD-restricted.
    """

    def test_verify_outside_cwd_is_allowed(self):
        """CLI --verify should accept valid receipts from any readable path."""
        import tempfile

        parent = tempfile.mkdtemp()
        project_dir = Path(parent, "project")
        outside_dir = Path(parent, "outside")
        project_dir.mkdir()
        outside_dir.mkdir()

        receipt = {
            "type": "aiir.commit_receipt",
            "schema": "aiir/commit_receipt.v1",
            "version": "1.0.0",
            "commit": {
                "sha": "a" * 40,
                "author": {},
                "committer": {},
                "subject": "test",
                "message_hash": "",
                "diff_hash": "",
                "files_changed": 0,
                "files": [],
            },
            "ai_attestation": {
                "is_ai_authored": False,
                "signals_detected": [],
                "signal_count": 0,
                "detection_method": "heuristic_v2",
            },
            "provenance": {"repository": "", "tool": "", "generator": "test"},
        }
        from aiir._core import _canonical_json, _sha256

        core_keys = {
            "type",
            "schema",
            "version",
            "commit",
            "ai_attestation",
            "provenance",
        }
        core = {k: v for k, v in receipt.items() if k in core_keys}
        core_json = _canonical_json(core)
        receipt["content_hash"] = "sha256:" + _sha256(core_json)
        receipt["receipt_id"] = "g1-" + _sha256(core_json)[:32]
        receipt["timestamp"] = "2026-01-01T00:00:00Z"
        receipt["extensions"] = {}

        outside_file = outside_dir / "receipt.json"
        outside_file.write_text(json.dumps(receipt))

        old_cwd = os.getcwd()
        try:
            os.chdir(project_dir)
            # Should succeed — CLI verify is read-only, no CWD restriction
            result = cli.verify_receipt_file(str(outside_file))
            self.assertTrue(
                result["valid"],
                f"CLI --verify should allow outside-CWD reads: {result}",
            )
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(parent, ignore_errors=True)

    def test_mcp_verify_rejects_outside_cwd(self):
        """MCP verify MUST reject outside-CWD paths (F4-02 oracle prevention)."""
        from aiir.mcp_server import _safe_verify_path
        import tempfile

        parent = tempfile.mkdtemp()
        project_dir = Path(parent, "project")
        outside_dir = Path(parent, "outside")
        project_dir.mkdir()
        outside_dir.mkdir()

        outside_file = outside_dir / "receipt.json"
        outside_file.write_text("{}")

        old_cwd = os.getcwd()
        try:
            os.chdir(project_dir)
            with self.assertRaises(ValueError) as ctx:
                _safe_verify_path(str(outside_file))
            self.assertIn("current working directory", str(ctx.exception))
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(parent, ignore_errors=True)


class TestTerminalEscapeInErrors(unittest.TestCase):
    """R18-SEC-01 / R18-SEC-02: User input in error messages must be sanitised."""

    def test_friendly_parser_strips_escapes_from_bad_flag(self):
        """ANSI escapes in an unrecognised flag must not appear in stderr."""
        from io import StringIO

        captured_err = StringIO()
        with patch("sys.stderr", captured_err):
            try:
                cli.main(["--\x1b[2Jfoo"])
            except SystemExit:
                pass
        stderr_text = captured_err.getvalue()
        self.assertNotIn("\x1b", stderr_text, "ANSI escape must be stripped")
        self.assertIn("\u274c", stderr_text, "Should show ❌ prefix")

    def test_range_hint_strips_escapes(self):
        """ANSI escapes in --range spec must not appear in hint message."""
        import tempfile

        tmpdir = tempfile.mkdtemp()
        old_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True, check=True)
            subprocess.run(
                ["git", "config", "user.email", "t@t.t"],
                cwd=tmpdir,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "T"],
                cwd=tmpdir,
                capture_output=True,
                check=True,
            )
            Path(tmpdir, "f.txt").write_text("x")
            subprocess.run(
                ["git", "add", "."], cwd=tmpdir, capture_output=True, check=True
            )
            subprocess.run(
                ["git", "commit", "-m", "init"],
                cwd=tmpdir,
                capture_output=True,
                check=True,
            )

            from io import StringIO

            captured_err = StringIO()
            # An empty range + escape in the spec
            with patch("sys.stderr", captured_err):
                rc = cli.main(["--range", "HEAD..HEAD\x1b[31mevil\x1b[0m"])
            stderr_text = captured_err.getvalue()
            # Whether it errors or shows "nothing to receipt", ESC must be gone
            self.assertNotIn(
                "\x1b", stderr_text, "ANSI escape must be stripped from range hint"
            )
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_run_git_stderr_strips_escapes(self):
        """_run_git should strip terminal escapes from git stderr in exceptions."""
        # Simulate git returning stderr with an ANSI escape
        fake_result = unittest.mock.MagicMock()
        fake_result.returncode = 128
        fake_result.stderr = "fatal: bad revision '\x1b[2Jevil'\n"
        fake_result.stdout = ""
        with patch("subprocess.run", return_value=fake_result):
            try:
                cli._run_git(["log", "HEAD"])
                self.fail("Should have raised RuntimeError")
            except RuntimeError as e:
                self.assertNotIn(
                    "\x1b", str(e), "ANSI escape must be stripped from git error"
                )


class TestConsistentFriendlyErrors(unittest.TestCase):
    """R18-PUB-01: Unrecognised flags should always show ❌, even without suggestions."""

    def test_no_match_still_shows_emoji(self):
        """A totally wrong flag should still get the ❌ prefix, not default argparse error."""
        from io import StringIO

        captured_err = StringIO()
        with patch("sys.stderr", captured_err):
            try:
                cli.main(["--zzzzzzzzzzz"])
            except SystemExit:
                pass
        stderr_text = captured_err.getvalue()
        self.assertIn("\u274c", stderr_text, "Should show ❌ even with no close match")

    def test_close_match_shows_emoji_and_hint(self):
        """A close-but-wrong flag should show ❌ + 💡."""
        from io import StringIO

        captured_err = StringIO()
        with patch("sys.stderr", captured_err):
            try:
                cli.main(["--prettty"])
            except SystemExit:
                pass
        stderr_text = captured_err.getvalue()
        self.assertIn("\u274c", stderr_text, "Should show ❌")
        self.assertIn("\U0001f4a1", stderr_text, "Should show 💡 hint")
        self.assertIn("--pretty", stderr_text, "Should suggest --pretty")


class TestEmptyRepoMessage(unittest.TestCase):
    """R20-UX-02: Empty repo (no commits) must show a friendly message."""

    @patch("aiir.cli.get_repo_root", return_value="/fake")
    @patch(
        "aiir.cli.generate_receipt",
        side_effect=RuntimeError("git log failed: unknown revision or path"),
    )
    def test_empty_repo_shows_friendly_message(self, mock_gen, mock_root):
        """Empty repo error must NOT leak raw git stderr."""
        import io

        captured_err = io.StringIO()
        with (
            patch("sys.stderr", captured_err),
            patch("sys.stdout", io.StringIO()),
            patch("sys.argv", ["aiir"]),
        ):
            code = cli.main()

        err = captured_err.getvalue()
        self.assertEqual(code, 1)
        self.assertIn("No commits yet", err)
        self.assertIn("first commit", err)
        # Must NOT contain raw git error details
        self.assertNotIn("fatal:", err)
        self.assertNotIn("ambiguous argument", err)

    @patch("aiir.cli.get_repo_root", return_value="/fake")
    @patch(
        "aiir.cli.generate_receipt",
        side_effect=RuntimeError("git log failed: bad default revision 'HEAD'"),
    )
    def test_bad_default_revision_friendly(self, mock_gen, mock_root):
        """'bad default revision' variant also gets a friendly message."""
        import io

        captured_err = io.StringIO()
        with (
            patch("sys.stderr", captured_err),
            patch("sys.stdout", io.StringIO()),
            patch("sys.argv", ["aiir"]),
        ):
            code = cli.main()

        err = captured_err.getvalue()
        self.assertEqual(code, 1)
        self.assertIn("No commits yet", err)

    @patch("aiir.cli.get_repo_root", return_value="/fake")
    @patch(
        "aiir.cli.generate_receipt",
        side_effect=RuntimeError("git log failed: permission denied"),
    )
    def test_non_empty_repo_error_still_shown(self, mock_gen, mock_root):
        """Other RuntimeErrors must still display the actual error message."""
        import io

        captured_err = io.StringIO()
        with (
            patch("sys.stderr", captured_err),
            patch("sys.stdout", io.StringIO()),
            patch("sys.argv", ["aiir"]),
        ):
            code = cli.main()

        err = captured_err.getvalue()
        self.assertEqual(code, 1)
        self.assertIn("permission denied", err)
        self.assertNotIn("No commits yet", err)
