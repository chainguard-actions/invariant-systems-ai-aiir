"""Tests for ledger append, dedup, index, config, namespace, export, badge, stats, check."""
# Copyright 2025-2026 Invariant Systems, Inc.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

# Import the module under test
import aiir.cli as cli


class TestLedgerAppend(unittest.TestCase):
    """append_to_ledger: basic append, dedup, index creation."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self.old_cwd)
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_receipt(self, sha="abc123def456"):
        return {
            "type": "aiir.commit_receipt",
            "schema": "aiir/commit_receipt.v1",
            "version": "1.0.0",
            "commit": {"sha": sha, "author": {"name": "T", "email": "t@t"}},
            "ai_attestation": {"is_ai_authored": False, "signals_detected": []},
            "provenance": {"repository": None, "tool": "test", "generator": "test"},
            "extensions": {},
            "receipt_id": f"g1-{sha[:32]}",
            "content_hash": f"sha256:{sha}",
            "timestamp": "2026-01-01T00:00:00Z",
        }

    def test_append_creates_dir_and_files(self):
        """First call should create .aiir/, ledger, and index."""
        r = self._make_receipt()
        appended, skipped, path = cli.append_to_ledger([r])
        self.assertEqual(appended, 1)
        self.assertEqual(skipped, 0)
        self.assertTrue(Path(path).exists())
        self.assertTrue((Path(".aiir") / "index.json").exists())

    def test_dedup_by_sha(self):
        """Same commit SHA should be skipped on second append."""
        r = self._make_receipt("aaa")
        cli.append_to_ledger([r])
        appended, skipped, _ = cli.append_to_ledger([r])
        self.assertEqual(appended, 0)
        self.assertEqual(skipped, 1)
        # Ledger should have exactly 1 line
        lines = Path(".aiir/receipts.jsonl").read_text().strip().split("\n")
        self.assertEqual(len(lines), 1)

    def test_index_counts(self):
        """Index should track AI and signing aggregates.

        Updated (D4 fix): sigstore_bundle must have a structurally-valid
        Sigstore bundle shape — a bare dict like {"bundle": "present"} is no
        longer accepted as signed.  This test now uses a real shape so it
        continues to exercise the signed=True path correctly.
        """
        r1 = self._make_receipt("sha_human")
        r2 = self._make_receipt("sha_ai")
        r2["ai_attestation"]["is_ai_authored"] = True
        # D4: must be a structurally-valid Sigstore bundle (not merely truthy).
        r2["extensions"]["sigstore_bundle"] = {
            "mediaType": "application/vnd.dev.sigstore.bundle+json;version=0.2",
            "verificationMaterial": {"certificate": {"rawBytes": "AAAA"}},
            "messageSignature": {"signature": "BBBB"},
        }
        cli.append_to_ledger([r1, r2])
        idx = json.loads(Path(".aiir/index.json").read_text())
        self.assertEqual(idx["receipt_count"], 2)
        self.assertEqual(idx["ai_commit_count"], 1)
        self.assertEqual(idx["signed_receipt_count"], 1)
        self.assertEqual(idx["unsigned_receipt_count"], 1)
        self.assertIn("sha_human", idx["commits"])
        self.assertIn("sha_ai", idx["commits"])
        self.assertFalse(idx["commits"]["sha_human"]["ai"])
        self.assertTrue(idx["commits"]["sha_ai"]["ai"])
        self.assertFalse(idx["commits"]["sha_human"]["signed"])
        self.assertTrue(idx["commits"]["sha_ai"]["signed"])

    def test_incremental_append(self):
        """Two separate appends should accumulate correctly."""
        r1 = self._make_receipt("first")
        r2 = self._make_receipt("second")
        cli.append_to_ledger([r1])
        cli.append_to_ledger([r2])
        lines = Path(".aiir/receipts.jsonl").read_text().strip().split("\n")
        self.assertEqual(len(lines), 2)
        idx = json.loads(Path(".aiir/index.json").read_text())
        self.assertEqual(idx["receipt_count"], 2)

    def test_custom_ledger_dir(self):
        """--ledger with a custom path should work."""
        r = self._make_receipt()
        custom = os.path.join(self.tmpdir, "custom-audit")
        appended, _, path = cli.append_to_ledger([r], ledger_dir=custom)
        self.assertEqual(appended, 1)
        self.assertIn("custom-audit", path)
        self.assertTrue(Path(custom, "receipts.jsonl").exists())

    def test_path_traversal_blocked(self):
        """Ledger dir outside cwd must raise ValueError."""
        r = self._make_receipt()
        with self.assertRaises(ValueError):
            cli.append_to_ledger([r], ledger_dir="/tmp")

    @unittest.skipIf(
        sys.platform == "win32", "Unix file permissions not applicable on Windows"
    )
    def test_ledger_file_permissions(self):
        """Ledger and index should be 0o600 (owner-only)."""
        r = self._make_receipt()
        cli.append_to_ledger([r])
        ledger_mode = oct(os.stat(".aiir/receipts.jsonl").st_mode & 0o777)
        index_mode = oct(os.stat(".aiir/index.json").st_mode & 0o777)
        self.assertEqual(ledger_mode, "0o600")
        self.assertEqual(index_mode, "0o600")

    def test_empty_receipts_list(self):
        """Appending empty list should be a no-op."""
        appended, skipped, _ = cli.append_to_ledger([])
        self.assertEqual(appended, 0)
        self.assertEqual(skipped, 0)

    def test_receipt_without_sha_skipped(self):
        """Receipt with no commit.sha should be silently skipped."""
        r = self._make_receipt()
        del r["commit"]["sha"]
        appended, skipped, _ = cli.append_to_ledger([r])
        self.assertEqual(appended, 0)
        self.assertEqual(skipped, 0)

    def test_ledger_lines_are_valid_json(self):
        """Each line in the ledger must parse as valid JSON."""
        r1 = self._make_receipt("one")
        r2 = self._make_receipt("two")
        cli.append_to_ledger([r1, r2])
        for line in Path(".aiir/receipts.jsonl").read_text().strip().split("\n"):
            data = json.loads(line)
            self.assertIn("commit", data)


class TestLedgerDefaultMode(unittest.TestCase):
    """CLI default mode should use the ledger."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmpdir)
        # Set up a minimal git repo
        subprocess.run(["git", "init", self.tmpdir], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", self.tmpdir, "config", "user.email", "t@t"],
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "-C", self.tmpdir, "config", "user.name", "T"],
            capture_output=True,
            check=True,
        )
        Path(self.tmpdir, "f.txt").write_text("x\n")
        subprocess.run(
            ["git", "-C", self.tmpdir, "add", "."], capture_output=True, check=True
        )
        subprocess.run(
            ["git", "-C", self.tmpdir, "commit", "-m", "init"],
            capture_output=True,
            check=True,
        )

    def tearDown(self):
        os.chdir(self.old_cwd)
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_bare_aiir_writes_ledger(self):
        """Running `aiir` with no flags should create .aiir/receipts.jsonl."""
        import io

        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            rc = cli.main([])
        self.assertEqual(rc, 0)
        self.assertTrue(Path(".aiir/receipts.jsonl").exists())
        self.assertTrue(Path(".aiir/index.json").exists())

    def test_json_flag_bypasses_ledger(self):
        """Running `aiir --json` should NOT create .aiir/."""
        import io

        captured = io.StringIO()
        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", captured):
            rc = cli.main(["--json"])
        self.assertEqual(rc, 0)
        self.assertFalse(Path(".aiir").exists())
        # stdout should have JSON
        data = json.loads(captured.getvalue())
        self.assertEqual(data["type"], "aiir.commit_receipt")

    def test_output_flag_bypasses_ledger(self):
        """Running `aiir --output .receipts` should NOT create .aiir/."""
        import io

        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            rc = cli.main(["--output", ".receipts"])
        self.assertEqual(rc, 0)
        self.assertFalse(Path(".aiir").exists())
        self.assertTrue(Path(".receipts").exists())


# ---------------------------------------------------------------------------
# Config, instance_id, namespace, richer index, and export tests
# ---------------------------------------------------------------------------


class TestConfigAndInstanceId(unittest.TestCase):
    """Tests for .aiir/config.json and instance_id generation."""

    def setUp(self):
        self._orig = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)
        subprocess.run(["git", "init"], capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], capture_output=True)
        Path("f.txt").write_text("x")
        subprocess.run(["git", "add", "."], capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], capture_output=True)

    def tearDown(self):
        os.chdir(self._orig)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_config_created_on_first_ledger_run(self):
        """First `aiir` run (ledger mode) creates config.json with instance_id."""
        import io

        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            cli.main([])
        cfg = json.loads(Path(".aiir/config.json").read_text())
        self.assertIn("instance_id", cfg)
        self.assertIn("created", cfg)
        # instance_id should be a valid UUID4
        uuid.UUID(cfg["instance_id"], version=4)

    def test_instance_id_persists_across_runs(self):
        """instance_id stays the same on second run."""
        import io

        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            cli.main([])
        first_id = json.loads(Path(".aiir/config.json").read_text())["instance_id"]
        # Make a second commit
        Path("g.txt").write_text("y")
        subprocess.run(["git", "add", "."], capture_output=True)
        subprocess.run(["git", "commit", "-m", "second"], capture_output=True)
        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            cli.main([])
        second_id = json.loads(Path(".aiir/config.json").read_text())["instance_id"]
        self.assertEqual(first_id, second_id)

    def test_instance_id_in_receipt_extensions(self):
        """Receipt extensions should contain the instance_id in ledger mode."""
        import io

        captured = io.StringIO()
        # Use ledger mode (default) — then read the JSONL
        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", captured):
            cli.main([])
        receipt = json.loads(Path(".aiir/receipts.jsonl").read_text().strip())
        self.assertIn("instance_id", receipt["extensions"])
        cfg = json.loads(Path(".aiir/config.json").read_text())
        self.assertEqual(receipt["extensions"]["instance_id"], cfg["instance_id"])

    def test_json_mode_no_instance_id(self):
        """--json mode should NOT populate instance_id (no config loaded)."""
        import io

        captured = io.StringIO()
        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", captured):
            cli.main(["--json"])
        receipt = json.loads(captured.getvalue())
        # extensions should be empty — no config loaded
        self.assertEqual(receipt["extensions"], {})

    def test_instance_id_excluded_from_content_hash(self):
        """instance_id in extensions must not affect content_hash."""
        commit = cli.CommitInfo(
            sha="abc123",
            author_name="Test",
            author_email="test@test.com",
            author_date="2026-01-01T00:00:00Z",
            committer_name="Test",
            committer_email="test@test.com",
            committer_date="2026-01-01T00:00:00Z",
            subject="test",
            body="test",
            diff_stat="",
            diff_hash="sha256:abc",
        )
        with patch(
            "aiir.cli._run_git", return_value="https://github.com/org/repo.git\n"
        ):
            r1 = cli.build_commit_receipt(commit)
            r2 = cli.build_commit_receipt(commit, instance_id="test-uuid-1234")
        self.assertEqual(r1["content_hash"], r2["content_hash"])
        self.assertEqual(r1["receipt_id"], r2["receipt_id"])
        self.assertEqual(r2["extensions"]["instance_id"], "test-uuid-1234")


class TestNamespace(unittest.TestCase):
    """Tests for --namespace flag."""

    def setUp(self):
        self._orig = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)
        subprocess.run(["git", "init"], capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], capture_output=True)
        Path("f.txt").write_text("x")
        subprocess.run(["git", "add", "."], capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], capture_output=True)

    def tearDown(self):
        os.chdir(self._orig)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_namespace_in_receipt_extensions(self):
        """--namespace should appear in receipt extensions."""
        import io

        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            cli.main(["--namespace", "acme-corp"])
        receipt = json.loads(Path(".aiir/receipts.jsonl").read_text().strip())
        self.assertEqual(receipt["extensions"]["namespace"], "acme-corp")

    def test_namespace_persisted_to_config(self):
        """--namespace should be saved to config.json."""
        import io

        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            cli.main(["--namespace", "acme-corp"])
        cfg = json.loads(Path(".aiir/config.json").read_text())
        self.assertEqual(cfg["namespace"], "acme-corp")

    def test_namespace_excluded_from_content_hash(self):
        """namespace in extensions must not affect content_hash."""
        commit = cli.CommitInfo(
            sha="abc123",
            author_name="Test",
            author_email="test@test.com",
            author_date="2026-01-01T00:00:00Z",
            committer_name="Test",
            committer_email="test@test.com",
            committer_date="2026-01-01T00:00:00Z",
            subject="test",
            body="test",
            diff_stat="",
            diff_hash="sha256:abc",
        )
        with patch(
            "aiir.cli._run_git", return_value="https://github.com/org/repo.git\n"
        ):
            r1 = cli.build_commit_receipt(commit)
            r2 = cli.build_commit_receipt(commit, namespace="acme-corp")
        self.assertEqual(r1["content_hash"], r2["content_hash"])
        self.assertEqual(r2["extensions"]["namespace"], "acme-corp")


class TestRicherIndex(unittest.TestCase):
    """Tests for richer index.json stats."""

    def setUp(self):
        self._orig = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)
        subprocess.run(["git", "init"], capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], capture_output=True)
        Path("f.txt").write_text("x")
        subprocess.run(["git", "add", "."], capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], capture_output=True)

    def tearDown(self):
        os.chdir(self._orig)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_index_has_richer_stats(self):
        """index.json should contain first_receipt, unique_authors, ai_percentage."""
        import io

        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            cli.main([])
        idx = json.loads(Path(".aiir/index.json").read_text())
        self.assertIn("first_receipt", idx)
        self.assertIn("unique_authors", idx)
        self.assertIn("ai_percentage", idx)
        self.assertIsNotNone(idx["first_receipt"])
        self.assertEqual(idx["unique_authors"], 1)
        self.assertIsInstance(idx["ai_percentage"], float)

    def test_index_tracks_multiple_authors(self):
        """unique_authors should count distinct commit authors."""
        import io

        # First commit already done in setUp by "Test <t@t.com>"
        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            cli.main([])
        # Second commit with different author
        subprocess.run(["git", "config", "user.name", "Other"], capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "other@test.com"], capture_output=True
        )
        Path("g.txt").write_text("y")
        subprocess.run(["git", "add", "."], capture_output=True)
        subprocess.run(["git", "commit", "-m", "second"], capture_output=True)
        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            cli.main([])
        idx = json.loads(Path(".aiir/index.json").read_text())
        self.assertEqual(idx["unique_authors"], 2)

    def test_index_tracks_multiple_redacted_authors(self):
        """unique_authors should still count distinct authors with redacted emails."""
        import io

        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            cli.main(["--redact-emails"])
        subprocess.run(["git", "config", "user.name", "Other"], capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "other@test.com"], capture_output=True
        )
        Path("g.txt").write_text("y")
        subprocess.run(["git", "add", "."], capture_output=True)
        subprocess.run(["git", "commit", "-m", "second"], capture_output=True)
        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            cli.main(["--redact-emails"])
        idx = json.loads(Path(".aiir/index.json").read_text())
        self.assertEqual(idx["unique_authors"], 2)
        author_values = {commit["author"] for commit in idx["commits"].values()}
        self.assertEqual(len(author_values), 2)
        self.assertTrue(
            all(value.endswith("@users.noreply.aiir") for value in author_values)
        )


class TestExport(unittest.TestCase):
    """Tests for aiir --export."""

    def setUp(self):
        self._orig = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)
        subprocess.run(["git", "init"], capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], capture_output=True)
        Path("f.txt").write_text("x")
        subprocess.run(["git", "add", "."], capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], capture_output=True)

    def tearDown(self):
        os.chdir(self._orig)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_export_creates_bundle(self):
        """--export should create a JSON bundle with all receipts."""
        import io

        # Generate receipts first
        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            cli.main([])
        # Export
        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            rc = cli.main(["--export", "bundle.json"])
        self.assertEqual(rc, 0)
        bundle = json.loads(Path("bundle.json").read_text())
        self.assertEqual(bundle["format"], "aiir.export.v1")
        self.assertIn("exported_at", bundle)
        self.assertIn("instance_id", bundle)
        self.assertIn("index", bundle)
        self.assertIn("receipts", bundle)
        self.assertEqual(len(bundle["receipts"]), 1)

    def test_export_default_filename(self):
        """--export with no arg should use 'aiir-export.json'."""
        import io

        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            cli.main([])
        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            rc = cli.main(["--export"])
        self.assertEqual(rc, 0)
        self.assertTrue(Path("aiir-export.json").exists())

    def test_export_rejects_path_traversal(self):
        """--export should reject paths with '..'."""
        import io

        # Must generate a ledger first so we reach the path validation check.
        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            cli.main([])
        stderr = io.StringIO()
        with patch("sys.stderr", stderr), patch("sys.stdout", io.StringIO()):
            rc = cli.main(["--export", "../evil.json"])
        self.assertEqual(rc, 1)
        self.assertIn("relative", stderr.getvalue())

    def test_export_rejects_absolute_path(self):
        """--export should reject absolute paths."""
        import io

        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            cli.main([])
        stderr = io.StringIO()
        with patch("sys.stderr", stderr), patch("sys.stdout", io.StringIO()):
            rc = cli.main(["--export", "/tmp/evil.json"])
        self.assertEqual(rc, 1)
        self.assertIn("relative", stderr.getvalue())

    def test_export_failure_error_path(self):
        """--export should handle export_ledger() failure gracefully."""
        import io

        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            cli.main([])
        stderr = io.StringIO()
        with (
            patch("aiir.cli.export_ledger", side_effect=RuntimeError("disk full")),
            patch("sys.stderr", stderr),
            patch("sys.stdout", io.StringIO()),
        ):
            rc = cli.main(["--export", "bundle.json"])
        self.assertEqual(rc, 1)
        self.assertIn("Export failed", stderr.getvalue())

    def test_export_includes_namespace(self):
        """Export bundle should include namespace from config."""
        import io

        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            cli.main(["--namespace", "acme-corp"])
        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            rc = cli.main(["--export", "bundle.json"])
        self.assertEqual(rc, 0)
        bundle = json.loads(Path("bundle.json").read_text())
        self.assertEqual(bundle["namespace"], "acme-corp")

    def test_export_no_ledger_fails(self):
        """--export with no ledger should fail gracefully (not create .aiir/)."""
        import io

        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            rc = cli.main(["--export", "bundle.json"])
        self.assertEqual(rc, 1)
        # Must NOT have created .aiir/config.json as a side effect.
        self.assertFalse(Path(".aiir/config.json").exists())
        self.assertFalse(Path("bundle.json").exists())


class TestLedgerJsonCombo(unittest.TestCase):
    """Combining --ledger with --json should write to both destinations."""

    def setUp(self):
        self._orig = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)
        subprocess.run(["git", "init"], capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], capture_output=True)
        Path("f.txt").write_text("x")
        subprocess.run(["git", "add", "."], capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], capture_output=True)

    def tearDown(self):
        os.chdir(self._orig)
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_ledger_plus_json_writes_both(self):
        """--ledger --json should write to ledger AND print to stdout."""
        import io

        stdout = io.StringIO()
        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", stdout):
            rc = cli.main(["--ledger", "--json"])
        self.assertEqual(rc, 0)
        # stdout should have JSON
        data = json.loads(stdout.getvalue())
        self.assertEqual(data["type"], "aiir.commit_receipt")
        # Ledger should also exist
        self.assertTrue(Path(".aiir/receipts.jsonl").exists())

    def test_ledger_plus_output_writes_both(self):
        """--ledger --output should write to ledger AND individual files."""
        import io

        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            rc = cli.main(["--ledger", "--output", ".receipts"])
        self.assertEqual(rc, 0)
        self.assertTrue(Path(".aiir/receipts.jsonl").exists())
        self.assertTrue(Path(".receipts").exists())
        self.assertTrue(any(Path(".receipts").iterdir()))


# ---------------------------------------------------------------------------
# Badge tests
# ---------------------------------------------------------------------------


class TestBadge(unittest.TestCase):
    """Tests for the --badge command."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        subprocess.run(["git", "init"], capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "a@b"], capture_output=True)
        subprocess.run(["git", "config", "user.name", "A"], capture_output=True)
        Path("f.txt").write_text("x")
        subprocess.run(["git", "add", "."], capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], capture_output=True)

    def tearDown(self):
        os.chdir(self._orig)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_badge_outputs_markdown(self):
        """--badge should print a shields.io Markdown snippet to stdout."""
        import io

        # Generate a receipt first (creates ledger).
        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            cli.main([])
        stdout = io.StringIO()
        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", stdout):
            rc = cli.main(["--badge"])
        self.assertEqual(rc, 0)
        output = stdout.getvalue()
        self.assertIn("img.shields.io/badge", output)
        self.assertIn("invariant-systems-ai/aiir", output)

    def test_badge_no_ledger_fails(self):
        """--badge with no ledger should fail gracefully."""
        import io

        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            rc = cli.main(["--badge"])
        self.assertEqual(rc, 1)

    def test_badge_url_structure(self):
        """format_badge should return well-formed URL and markdown."""
        index = {"receipt_count": 10, "ai_percentage": 25.0}
        result = cli.format_badge(index)
        self.assertIn("img.shields.io/badge", result["url"])
        self.assertIn("25.0", result["url"])
        self.assertTrue(result["markdown"].startswith("[!["))
        self.assertIn("25.0", result["text"])

    def test_badge_empty_index(self):
        """format_badge with zero receipts should show 'no receipts'."""
        index = {"receipt_count": 0, "ai_percentage": 0.0}
        result = cli.format_badge(index)
        self.assertIn("no_receipts", result["url"])
        self.assertIn("lightgrey", result["url"])


# ---------------------------------------------------------------------------
# Stats tests
# ---------------------------------------------------------------------------


class TestStats(unittest.TestCase):
    """Tests for the --stats command."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        subprocess.run(["git", "init"], capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "a@b"], capture_output=True)
        subprocess.run(["git", "config", "user.name", "A"], capture_output=True)
        Path("f.txt").write_text("x")
        subprocess.run(["git", "add", "."], capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], capture_output=True)

    def tearDown(self):
        os.chdir(self._orig)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_stats_output(self):
        """--stats should print a summary dashboard to stderr."""
        import io

        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            cli.main([])
        stderr = io.StringIO()
        with patch("sys.stderr", stderr), patch("sys.stdout", io.StringIO()):
            rc = cli.main(["--stats"])
        self.assertEqual(rc, 0)
        output = stderr.getvalue()
        self.assertIn("AIIR Ledger", output)
        self.assertIn("1 receipt", output)
        self.assertIn("AI-authored", output)
        self.assertIn("Signing:", output)
        self.assertIn("0 signed, 1 unsigned", output)

    def test_stats_no_ledger_fails(self):
        """--stats with no ledger should fail gracefully."""
        import io

        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            rc = cli.main(["--stats"])
        self.assertEqual(rc, 1)

    def test_format_stats_includes_namespace(self):
        """format_stats should include namespace when present in config."""
        index = {
            "receipt_count": 5,
            "ai_commit_count": 1,
            "ai_percentage": 20.0,
            "signed_receipt_count": 3,
            "unsigned_receipt_count": 2,
            "unique_authors": 2,
            "first_receipt": "2026-01-01T00:00:00Z",
            "latest_timestamp": "2026-03-07T00:00:00Z",
        }
        config = {"namespace": "acme-corp", "instance_id": "abc12345-xxxx"}
        output = cli.format_stats(index, config=config)
        self.assertIn("acme-corp", output)
        self.assertIn("abc12345", output)
        self.assertIn("5 receipts", output)
        self.assertIn("20.0%", output)
        self.assertIn("3 signed, 2 unsigned", output)


# ---------------------------------------------------------------------------
# Check / policy gate tests
# ---------------------------------------------------------------------------


class TestCheck(unittest.TestCase):
    """Tests for the --check / --max-ai-percent policy gate."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        subprocess.run(["git", "init"], capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "a@b"], capture_output=True)
        subprocess.run(["git", "config", "user.name", "A"], capture_output=True)
        Path("f.txt").write_text("x")
        subprocess.run(["git", "add", "."], capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], capture_output=True)

    def tearDown(self):
        os.chdir(self._orig)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_check_passes_within_threshold(self):
        """--check --max-ai-percent 50 should pass when AI% is 0."""
        import io

        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            cli.main([])
        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            rc = cli.main(["--check", "--max-ai-percent", "50"])
        self.assertEqual(rc, 0)

    def test_check_fails_above_threshold(self):
        """check_policy should fail when AI% exceeds threshold."""
        index = {"receipt_count": 10, "ai_commit_count": 8, "ai_percentage": 80.0}
        passed, msg = cli.check_policy(index, max_ai_percent=50.0)
        self.assertFalse(passed)
        self.assertIn("FAIL", msg)
        self.assertIn("80.0%", msg)

    def test_check_passes_at_threshold(self):
        """check_policy should pass when AI% equals threshold."""
        index = {"receipt_count": 10, "ai_commit_count": 5, "ai_percentage": 50.0}
        passed, msg = cli.check_policy(index, max_ai_percent=50.0)
        self.assertTrue(passed)
        self.assertIn("PASS", msg)

    def test_check_no_ledger_fails(self):
        """--check with no ledger should fail gracefully."""
        import io

        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            rc = cli.main(["--check", "--max-ai-percent", "50"])
        self.assertEqual(rc, 1)

    def test_check_no_threshold_ok(self):
        """--check without --max-ai-percent should just report status."""
        import io

        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            cli.main([])
        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            rc = cli.main(["--check"])
        self.assertEqual(rc, 0)

    def test_max_ai_percent_implies_check(self):
        """--max-ai-percent alone (without --check) should still run the gate."""
        import io

        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            cli.main([])
        with patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            rc = cli.main(["--max-ai-percent", "90"])
        self.assertEqual(rc, 0)


# ---------------------------------------------------------------------------
# Security regression tests: D1 agent-segregation + D4 signed-status fixes
# ---------------------------------------------------------------------------


class TestD1AgentReceiptSegregation(unittest.TestCase):
    """D1: Agent receipts MUST NOT contribute to commit-level aggregates.

    Exploit scenario: a hybrid receipt that has contract_version matching
    the agent receipt pattern AND grafted ai_attestation/commit fields.
    Before the fix this forged ai_commit_count=1, ai_percentage=100,
    unique_authors=1.  After the fix these stay at 0.
    """

    def setUp(self):
        self._orig = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._orig)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _make_agent_receipt(self, record_id_suffix: str = "a" * 32) -> dict:
        """Return a hybrid agent receipt with grafted ai_attestation/commit."""
        from aiir._agent_receipt import AGENT_RECEIPT_CONTRACT_VERSION

        return {
            "contract_version": AGENT_RECEIPT_CONTRACT_VERSION,
            "record_id": "a1-" + record_id_suffix,
            # Unauthenticated grafts — must be ignored by ledger aggregates.
            "ai_attestation": {
                "is_ai_authored": True,
                "is_bot_authored": True,
                "authorship_class": "ai_primary",
            },
            "commit": {
                "sha": "fake_sha_graft",
                "author": {"name": "Attacker", "email": "attacker@evil.com"},
            },
            "extensions": {"sigstore": "fake"},
            "receipt_id": "r1-" + "b" * 32,
            "timestamp": "2026-01-01T00:00:00Z",
        }

    def test_agent_receipt_does_not_forge_ai_commit_count(self):
        """PROVEN EXPLOIT -> BLOCKED: agent receipt must not bump ai_commit_count."""
        from aiir._ledger import append_to_ledger

        receipt = self._make_agent_receipt()
        appended, _skipped, _path = append_to_ledger([receipt])
        self.assertEqual(appended, 1)

        idx = json.loads(Path(".aiir/index.json").read_text())
        # Before fix: ai_commit_count == 1.  After fix: must be 0.
        self.assertEqual(
            idx["ai_commit_count"], 0, "D1 FAIL: ai_commit_count was forged"
        )
        self.assertEqual(
            idx["bot_commit_count"], 0, "D1 FAIL: bot_commit_count was forged"
        )

    def test_agent_receipt_does_not_inflate_ai_percentage(self):
        """PROVEN EXPLOIT -> BLOCKED: agent receipt must not set ai_percentage=100."""
        from aiir._ledger import append_to_ledger

        receipt = self._make_agent_receipt("c" * 32)
        append_to_ledger([receipt])

        idx = json.loads(Path(".aiir/index.json").read_text())
        # Before fix: ai_percentage == 100.0.  After fix: must be 0.0.
        self.assertEqual(idx["ai_percentage"], 0.0, "D1 FAIL: ai_percentage was forged")

    def test_agent_receipt_does_not_inflate_unique_authors(self):
        """PROVEN EXPLOIT -> BLOCKED: agent receipt must not add to unique_authors."""
        from aiir._ledger import append_to_ledger

        receipt = self._make_agent_receipt("d" * 32)
        append_to_ledger([receipt])

        idx = json.loads(Path(".aiir/index.json").read_text())
        # Before fix: unique_authors == 1.  After fix: must be 0.
        self.assertEqual(idx["unique_authors"], 0, "D1 FAIL: unique_authors was forged")

    def test_agent_receipt_tracked_separately(self):
        """Agent receipts should increment agent_receipt_count, not receipt aggregates."""
        from aiir._ledger import append_to_ledger

        receipt = self._make_agent_receipt("e" * 32)
        append_to_ledger([receipt])

        idx = json.loads(Path(".aiir/index.json").read_text())
        self.assertEqual(idx.get("agent_receipt_count", 0), 1)
        # receipt_count still includes agent receipts in total.
        self.assertEqual(idx["receipt_count"], 1)

    def test_ai_percentage_denominator_excludes_agent_receipts(self):
        """ai_percentage denominator is commit receipts only, not total receipts."""
        from aiir._ledger import append_to_ledger

        agent = self._make_agent_receipt("f" * 32)
        commit = {
            "type": "aiir.commit_receipt",
            "commit": {
                "sha": "real_commit_sha",
                "author": {"email": "dev@example.com"},
            },
            "ai_attestation": {"is_ai_authored": True},
            "extensions": {},
            "receipt_id": "r1-" + "g" * 32,
            "timestamp": "2026-01-02T00:00:00Z",
        }
        append_to_ledger([agent, commit])

        idx = json.loads(Path(".aiir/index.json").read_text())
        # ai_percentage = 1 AI commit / 1 commit receipt = 100.0
        # NOT 1 AI / 2 total = 50.0 (which would be wrong if agent were in denominator).
        self.assertEqual(idx["ai_commit_count"], 1)
        self.assertEqual(idx["ai_percentage"], 100.0)
        self.assertEqual(idx["unique_authors"], 1)


class TestD4SignedStatusReceipt(unittest.TestCase):
    """D4: _receipt_is_signed must return False for agent receipts and require
    a structurally-valid Sigstore bundle shape for commit receipts.

    Exploit scenario: agent receipt with extensions={'sigstore':'fake'} or
    commit receipt with extensions={'sigstore_bundle': True} currently inflates
    signed_receipt_count.  After fix these are correctly counted as unsigned.
    """

    def setUp(self):
        self._orig = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._orig)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _valid_bundle(self) -> dict:
        return {
            "mediaType": "application/vnd.dev.sigstore.bundle+json;version=0.2",
            "verificationMaterial": {"certificate": {"rawBytes": "AAAA"}},
            "messageSignature": {"signature": "BBBB"},
        }

    def test_agent_receipt_with_fake_sigstore_is_unsigned(self):
        """PROVEN EXPLOIT -> BLOCKED: agent receipt with fake sigstore must be unsigned."""
        from aiir._agent_receipt import AGENT_RECEIPT_CONTRACT_VERSION
        from aiir._ledger import _receipt_is_signed, append_to_ledger

        receipt = {
            "contract_version": AGENT_RECEIPT_CONTRACT_VERSION,
            "record_id": "a1-" + "a" * 32,
            "extensions": {"sigstore": "fake"},
            "timestamp": "2026-01-01T00:00:00Z",
        }
        # Direct function check.
        self.assertFalse(
            _receipt_is_signed(receipt),
            "D4 FAIL: agent receipt with fake sigstore counted as signed",
        )
        # Through append path: signed_receipt_count must stay 0.
        append_to_ledger([receipt])
        idx = json.loads(Path(".aiir/index.json").read_text())
        self.assertEqual(
            idx["signed_receipt_count"],
            0,
            "D4 FAIL: agent receipt inflated signed_receipt_count",
        )

    def test_commit_receipt_with_truthy_sigstore_string_is_unsigned(self):
        """PROVEN EXPLOIT -> BLOCKED: bare string in sigstore must not count as signed."""
        from aiir._ledger import _receipt_is_signed

        receipt = {
            "type": "aiir.commit_receipt",
            "commit": {"sha": "abc123", "author": {"email": "t@t"}},
            "ai_attestation": {"is_ai_authored": False},
            "extensions": {"sigstore": "fake"},
        }
        self.assertFalse(
            _receipt_is_signed(receipt),
            "D4 FAIL: bare string sigstore counted as signed",
        )

    def test_commit_receipt_with_truthy_sigstore_bundle_bool_is_unsigned(self):
        """PROVEN EXPLOIT -> BLOCKED: sigstore_bundle=True must not count as signed."""
        from aiir._ledger import _receipt_is_signed

        receipt = {
            "type": "aiir.commit_receipt",
            "commit": {"sha": "abc123", "author": {"email": "t@t"}},
            "ai_attestation": {"is_ai_authored": False},
            "extensions": {"sigstore_bundle": True},
        }
        self.assertFalse(
            _receipt_is_signed(receipt),
            "D4 FAIL: sigstore_bundle=True counted as signed",
        )

    def test_commit_receipt_with_partial_bundle_is_unsigned(self):
        """Incomplete bundle (missing cert or signature) must not count as signed."""
        from aiir._ledger import _receipt_is_signed

        # Missing messageSignature/dsseEnvelope.
        receipt = {
            "type": "aiir.commit_receipt",
            "extensions": {
                "sigstore_bundle": {
                    "mediaType": "application/vnd.dev.sigstore.bundle+json;version=0.2",
                    "verificationMaterial": {"certificate": {"rawBytes": "AAAA"}},
                    # No messageSignature, no dsseEnvelope.
                }
            },
        }
        self.assertFalse(_receipt_is_signed(receipt))

    def test_commit_receipt_with_valid_bundle_is_signed(self):
        """A structurally-valid Sigstore bundle must count as signed."""
        from aiir._ledger import _receipt_is_signed

        receipt = {
            "type": "aiir.commit_receipt",
            "commit": {"sha": "abc123", "author": {"email": "t@t"}},
            "ai_attestation": {"is_ai_authored": False},
            "extensions": {"sigstore_bundle": self._valid_bundle()},
        }
        self.assertTrue(
            _receipt_is_signed(receipt), "D4: valid bundle should be signed"
        )

    def test_commit_receipt_with_valid_dsse_bundle_is_signed(self):
        """A bundle using dsseEnvelope (instead of messageSignature) must be accepted."""
        from aiir._ledger import _receipt_is_signed

        bundle = {
            "mediaType": "application/vnd.dev.sigstore.bundle+json;version=0.2",
            "verificationMaterial": {
                "x509CertificateChain": {"certificates": [{"rawBytes": "AAAA"}]}
            },
            "dsseEnvelope": {"signature": "CCCC"},
        }
        receipt = {
            "type": "aiir.commit_receipt",
            "extensions": {"sigstore_bundle": bundle},
        }
        self.assertTrue(_receipt_is_signed(receipt), "D4: dsse bundle should be signed")

    def test_agent_receipt_with_valid_bundle_still_unsigned(self):
        """Even with a structurally-valid bundle, agent receipts are always unsigned."""
        from aiir._agent_receipt import AGENT_RECEIPT_CONTRACT_VERSION
        from aiir._ledger import _receipt_is_signed

        receipt = {
            "contract_version": AGENT_RECEIPT_CONTRACT_VERSION,
            "record_id": "a1-" + "b" * 32,
            "extensions": {"sigstore_bundle": self._valid_bundle()},
        }
        self.assertFalse(
            _receipt_is_signed(receipt),
            "D4: agent receipts have no Sigstore path and must always be unsigned",
        )

    def test_fake_bundle_inflates_signed_count_is_blocked(self):
        """PROVEN EXPLOIT -> BLOCKED: fake bundle in append path must not inflate signed count."""
        from aiir._ledger import append_to_ledger

        commit = {
            "type": "aiir.commit_receipt",
            "commit": {"sha": "exploit_sha", "author": {"email": "t@t"}},
            "ai_attestation": {"is_ai_authored": False},
            "extensions": {
                "sigstore_bundle": {"bundle": "fake", "mediaType": "not-sigstore"}
            },
            "receipt_id": "r1-" + "c" * 32,
            "timestamp": "2026-01-01T00:00:00Z",
        }
        append_to_ledger([commit])
        idx = json.loads(Path(".aiir/index.json").read_text())
        # Before fix: signed_receipt_count == 1.  After fix: must be 0.
        self.assertEqual(
            idx["signed_receipt_count"],
            0,
            "D4 FAIL: fake bundle inflated signed_receipt_count",
        )
        self.assertEqual(idx["unsigned_receipt_count"], 1)


# ---------------------------------------------------------------------------
# Cross-platform / OS-portability tests
# ---------------------------------------------------------------------------
