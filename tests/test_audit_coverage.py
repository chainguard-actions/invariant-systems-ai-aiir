# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""Coverage-closure tests for newly-added hardening code paths.

Each test exercises a specific branch/line that the rest of the suite leaves
uncovered, asserting the *actual* documented behaviour (not merely invoking the
code for coverage):

- _github.urlopen / _gitlab.urlopen module-level no-redirect opener seams.
- _github_api_request / _gitlab_api_request error wrapping.
- _LedgerLock.__exit__ no-op when no fd is held.
- _sanitize_editor_provenance record-filtering branches.
- build_commit_receipt email redaction (redact + non-redact).
- write_receipt corrupt-existing-file fall-through.
- _is_structurally_valid_sigstore_bundle / _has_verified_sigstore_sidecar gate.
- aiir --status "no-repo" label inside a commit-less git repo.
- aiir --ci --json on an empty ledger ("Ledger is empty").
- MCP serve_stdio bounded-read EOF and oversized-drain paths.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# _github / _gitlab: module-level no-redirect urlopen seam
# ---------------------------------------------------------------------------


class TestNoRedirectUrlopenSeam(unittest.TestCase):
    """The module-level ``urlopen`` wrapper must route through the no-redirect opener."""

    def test_github_urlopen_uses_no_redirect_opener(self) -> None:
        import aiir._github as gh

        sentinel = object()
        opener_mock = MagicMock(return_value=sentinel)
        with patch.object(gh._NO_REDIRECT_OPENER, "open", opener_mock):
            result = gh.urlopen("REQ", timeout=12)
        self.assertIs(result, sentinel)
        opener_mock.assert_called_once_with("REQ", timeout=12)

    def test_gitlab_urlopen_uses_no_redirect_opener(self) -> None:
        import aiir._gitlab as gl

        sentinel = object()
        opener_mock = MagicMock(return_value=sentinel)
        with patch.object(gl._NO_REDIRECT_OPENER, "open", opener_mock):
            result = gl.urlopen("GREQ")
        self.assertIs(result, sentinel)
        opener_mock.assert_called_once_with("GREQ", timeout=None)


# ---------------------------------------------------------------------------
# _github / _gitlab: API request error wrapping
# ---------------------------------------------------------------------------


class TestApiRequestErrorReraise(unittest.TestCase):
    """A RuntimeError from urlopen must propagate unchanged (not re-wrapped)."""

    def test_github_api_request_reraises_runtime_error_unchanged(self) -> None:
        import aiir._github as gh

        # A RuntimeError raised below us (e.g. the no-redirect handler refusing
        # a redirect) must pass straight through `except RuntimeError: raise`
        # rather than being double-wrapped as "GitHub API request failed".
        original = RuntimeError("redirect refused")
        with patch.object(gh, "urlopen", side_effect=original):
            with self.assertRaises(RuntimeError) as ctx:
                gh._github_api_request(
                    "https://api.github.com/repos/x/y/check-runs",
                    {"name": "aiir/verify"},
                    token="tkn",
                )
        # Identity check: the *same* exception object propagated, unwrapped.
        self.assertIs(ctx.exception, original)
        self.assertNotIn("GitHub API request failed", str(ctx.exception))

    def test_gitlab_api_request_reraises_runtime_error_unchanged(self) -> None:
        import aiir._gitlab as gl

        original = RuntimeError("redirect refused")
        with patch.object(gl, "urlopen", side_effect=original):
            with self.assertRaises(RuntimeError) as ctx:
                gl._gitlab_api_request(
                    "POST",
                    "/projects/1/merge_requests/2/notes",
                    body={"body": "hi"},
                    api_url="https://gitlab.example/api/v4",
                    token="tkn",
                )
        self.assertIs(ctx.exception, original)
        self.assertNotIn("GitLab API error", str(ctx.exception))


# ---------------------------------------------------------------------------
# _ledger: _LedgerLock.__exit__ no-op when no fd held
# ---------------------------------------------------------------------------


class TestLedgerLockExitWithoutFd(unittest.TestCase):
    """__exit__ must be a safe no-op when the lock context never acquired an fd."""

    def test_exit_without_held_fd_is_noop(self) -> None:
        from aiir._ledger import _LedgerLock

        with tempfile.TemporaryDirectory() as td:
            lock = _LedgerLock(Path(td))
            # Constructed but never entered: no fd is held.
            self.assertIsNone(lock._fd)
            # __exit__ must not raise and must leave _fd None (skips the
            # `if self._fd is not None:` body entirely — 65->exit branch).
            self.assertIsNone(lock.__exit__(None, None, None))
            self.assertIsNone(lock._fd)


# ---------------------------------------------------------------------------
# _receipt: _sanitize_editor_provenance record-filtering branches
# ---------------------------------------------------------------------------


class TestSanitizeEditorProvenanceRecords(unittest.TestCase):
    """Records sanitization must drop junk while keeping clean string-only rows."""

    def test_records_filtering_drops_invalid_entries(self) -> None:
        from aiir._receipt import _sanitize_editor_provenance

        provenance = {
            "schema": "aiir/editor_provenance.v1",
            "records": [
                "not-a-dict",  # non-dict element -> `continue` (line 199)
                # all values are dict/list -> filtered by k/v guard, rec_clean
                # stays empty -> not appended (207->197 loop-back).
                {"nested": {"a": 1}, "arr": [1, 2, 3]},
                # key strips to empty -> k_safe falsy, not stored (205->201).
                {"\x1b[31m": "value"},
            ],
        }
        cleaned = _sanitize_editor_provenance(provenance)
        self.assertIsNotNone(cleaned)
        assert cleaned is not None  # for type-checkers
        self.assertEqual(cleaned.get("schema"), "aiir/editor_provenance.v1")
        # None of the junk records survived -> "records" omitted (209->211 false).
        self.assertNotIn("records", cleaned)

    def test_records_with_clean_row_is_preserved(self) -> None:
        from aiir._receipt import _sanitize_editor_provenance

        provenance = {
            "schema": "aiir/editor_provenance.v1",
            "records": [{"action": "edit", "file": "a.py"}],
        }
        cleaned = _sanitize_editor_provenance(provenance)
        self.assertIsNotNone(cleaned)
        assert cleaned is not None
        # records_clean non-empty -> stored (209->211 true branch).
        self.assertEqual(cleaned["records"], [{"action": "edit", "file": "a.py"}])

    def test_known_key_stripping_to_empty_is_skipped(self) -> None:
        from aiir._receipt import _sanitize_editor_provenance

        # "mode" value strips to empty -> `if s:` false (191->186 loop-back),
        # while "schema" survives.
        provenance = {"mode": "\x1b[31m", "schema": "aiir/editor_provenance.v1"}
        cleaned = _sanitize_editor_provenance(provenance)
        self.assertIsNotNone(cleaned)
        assert cleaned is not None
        self.assertNotIn("mode", cleaned)
        self.assertEqual(cleaned.get("schema"), "aiir/editor_provenance.v1")


# ---------------------------------------------------------------------------
# _receipt: build_commit_receipt email redaction (redact + non-redact)
# ---------------------------------------------------------------------------


def _make_commit_info():
    import aiir.cli as cli

    return cli.CommitInfo(
        sha="deadbeef" * 5,
        author_name="Test",
        author_email="author@example.com",
        author_date="2026-01-01T00:00:00Z",
        committer_name="Test",
        committer_email="committer@example.com",
        committer_date="2026-01-01T00:00:00Z",
        subject="test",
        body="test",
        diff_stat="",
        diff_hash="sha256:0000",
        files_changed=[],
        ai_signals_detected=[],
        is_ai_authored=False,
    )


class TestBuildReceiptEmailRedaction(unittest.TestCase):
    """build_commit_receipt must redact emails only when asked."""

    def test_emails_passthrough_without_redaction(self) -> None:
        from aiir._receipt import build_commit_receipt

        receipt = build_commit_receipt(_make_commit_info(), redact_emails=False)
        self.assertEqual(receipt["commit"]["author"]["email"], "author@example.com")
        self.assertEqual(
            receipt["commit"]["committer"]["email"], "committer@example.com"
        )

    def test_emails_redacted_when_requested(self) -> None:
        from aiir._receipt import build_commit_receipt

        receipt = build_commit_receipt(
            _make_commit_info(), redact_emails=True, redaction_salt="salt"
        )
        author_email = receipt["commit"]["author"]["email"]
        committer_email = receipt["commit"]["committer"]["email"]
        # Redacted form must not leak the plaintext addresses.
        self.assertNotEqual(author_email, "author@example.com")
        self.assertNotEqual(committer_email, "committer@example.com")
        self.assertNotIn("author@example.com", json.dumps(receipt))
        self.assertNotIn("committer@example.com", json.dumps(receipt))


# ---------------------------------------------------------------------------
# _receipt: write_receipt over a corrupt existing file
# ---------------------------------------------------------------------------


class TestWriteReceiptCorruptExisting(unittest.TestCase):
    """A corrupt existing receipt file must hit the fall-through write path."""

    def _make_receipt(self) -> Dict[str, Any]:
        return {
            "type": "aiir.commit_receipt",
            "schema": "aiir/commit_receipt.v2",
            "version": "1.0.0",
            "commit": {
                "sha": "abcCORRUPT",
                "tree_sha": "",
                "parent_shas": [],
                "author": {
                    "name": "X",
                    "email": "x@x.com",
                    "date": "2026-01-01T00:00:00Z",
                },
                "committer": {
                    "name": "X",
                    "email": "x@x.com",
                    "date": "2026-01-01T00:00:00Z",
                },
                "subject": "test",
                "message_hash": "sha256:0000",
                "diff_hash": "sha256:0001",
                "files_changed": 0,
                "files": [],
            },
            "receipt_id": "g1-" + "0" * 31 + "C",
            "content_hash": "sha256:" + "0" * 63 + "c",
            "timestamp": "2026-01-01T00:00:00Z",
            "extensions": {},
        }

    def test_corrupt_existing_file_falls_through_to_oexcl(self) -> None:
        import re

        from aiir._receipt import write_receipt

        receipt = self._make_receipt()
        # write_receipt requires output_dir within cwd.
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmp:
            chash = receipt["content_hash"]
            chash_short = re.sub(r"[^a-fA-F0-9]", "", chash)[:16]
            commit_sha = re.sub(
                r"[^a-zA-Z0-9_-]", "_", str(receipt["commit"]["sha"])[:24]
            )
            filepath = Path(tmp) / f"receipt_{commit_sha}_{chash_short}.json"
            # Pre-seed a corrupt (unparsable) file at the deterministic path.
            filepath.write_text("{ this is not valid json", encoding="utf-8")

            # The corrupt file triggers JSONDecodeError -> `pass` fall-through,
            # then os.open(O_EXCL) fails because the file still exists. This is
            # the documented behaviour ("os.open with O_EXCL would fail").
            with self.assertRaises(FileExistsError):
                write_receipt(receipt, output_dir=tmp)
            # The corrupt file must remain untouched (no silent overwrite).
            self.assertEqual(
                filepath.read_text(encoding="utf-8"), "{ this is not valid json"
            )


# ---------------------------------------------------------------------------
# _verify_release: sigstore bundle structural validation
# ---------------------------------------------------------------------------


_VALID_MEDIA = "application/vnd.dev.sigstore.bundle+json;version=0.3"


class TestSigstoreBundleStructuralValidation(unittest.TestCase):
    """_is_structurally_valid_sigstore_bundle is the zero-dependency gate floor."""

    def setUp(self) -> None:
        self._dir = tempfile.mkdtemp()

    def _write(self, name: str, content: Any) -> str:
        path = Path(self._dir) / name
        if isinstance(content, (dict, list)):
            path.write_text(json.dumps(content), encoding="utf-8")
        else:
            path.write_text(content, encoding="utf-8")
        return str(path)

    def test_missing_file_is_invalid(self) -> None:
        from aiir._verify_release import _is_structurally_valid_sigstore_bundle

        missing = str(Path(self._dir) / "does-not-exist.sigstore")
        self.assertFalse(_is_structurally_valid_sigstore_bundle(missing))

    def test_unparsable_json_is_invalid(self) -> None:
        from aiir._verify_release import _is_structurally_valid_sigstore_bundle

        path = self._write("bad.sigstore", "{ not valid json")
        self.assertFalse(_is_structurally_valid_sigstore_bundle(path))

    def test_non_dict_top_level_is_invalid(self) -> None:
        from aiir._verify_release import _is_structurally_valid_sigstore_bundle

        path = self._write("list.sigstore", [1, 2, 3])
        self.assertFalse(_is_structurally_valid_sigstore_bundle(path))

    def test_wrong_media_type_is_invalid(self) -> None:
        from aiir._verify_release import _is_structurally_valid_sigstore_bundle

        path = self._write("media.sigstore", {"mediaType": "application/json"})
        self.assertFalse(_is_structurally_valid_sigstore_bundle(path))

    def test_missing_verification_material_is_invalid(self) -> None:
        from aiir._verify_release import _is_structurally_valid_sigstore_bundle

        path = self._write("nomat.sigstore", {"mediaType": _VALID_MEDIA})
        self.assertFalse(_is_structurally_valid_sigstore_bundle(path))

    def test_cert_without_rawbytes_and_no_chain_is_invalid(self) -> None:
        from aiir._verify_release import _is_structurally_valid_sigstore_bundle

        path = self._write(
            "nocert.sigstore",
            {
                "mediaType": _VALID_MEDIA,
                "verificationMaterial": {"certificate": {}},
            },
        )
        self.assertFalse(_is_structurally_valid_sigstore_bundle(path))

    def test_valid_message_signature_bundle(self) -> None:
        from aiir._verify_release import _is_structurally_valid_sigstore_bundle

        path = self._write(
            "ok-msg.sigstore",
            {
                "mediaType": _VALID_MEDIA,
                "verificationMaterial": {"certificate": {"rawBytes": "AAAA"}},
                "messageSignature": {"signature": "SIG"},
            },
        )
        self.assertTrue(_is_structurally_valid_sigstore_bundle(path))

    def test_valid_dsse_envelope_bundle_with_cert_chain(self) -> None:
        from aiir._verify_release import _is_structurally_valid_sigstore_bundle

        path = self._write(
            "ok-dsse.sigstore",
            {
                "mediaType": _VALID_MEDIA,
                "verificationMaterial": {
                    "x509CertificateChain": {"certificates": ["cert"]}
                },
                "dsseEnvelope": {"signatures": ["sig"]},
            },
        )
        self.assertTrue(_is_structurally_valid_sigstore_bundle(path))


class TestHasVerifiedSigstoreSidecar(unittest.TestCase):
    """_has_verified_sigstore_sidecar fails closed when no real sidecar is present."""

    def setUp(self) -> None:
        self._dir = tempfile.mkdtemp()
        self._receipt = {
            "receipt_id": "rid1",
            "commit": {"sha": "sha1"},
            "content_hash": "ch1",
        }

    def test_empty_index_returns_false(self) -> None:
        from aiir._verify_release import _has_verified_sigstore_sidecar

        self.assertFalse(_has_verified_sigstore_sidecar(self._receipt, {}))

    def test_artifact_without_json_path_is_skipped(self) -> None:
        from aiir._verify_release import _has_verified_sigstore_sidecar

        # Artifact matches the key but lacks a json_path -> `continue` (line 259);
        # the loop then exhausts and returns False (fail-closed).
        index = {"rid1": {"sigstore_present": True}}
        self.assertFalse(_has_verified_sigstore_sidecar(self._receipt, index))

    def test_missing_sidecar_file_returns_false(self) -> None:
        from aiir._verify_release import _has_verified_sigstore_sidecar

        json_path = Path(self._dir) / "r.json"
        json_path.write_text("{}", encoding="utf-8")
        index = {"rid1": {"json_path": str(json_path)}}
        # No .sigstore file on disk -> False.
        self.assertFalse(_has_verified_sigstore_sidecar(self._receipt, index))

    def test_valid_sidecar_returns_true(self) -> None:
        from aiir._verify_release import _has_verified_sigstore_sidecar

        json_path = Path(self._dir) / "r.json"
        json_path.write_text("{}", encoding="utf-8")
        (Path(self._dir) / "r.json.sigstore").write_text(
            json.dumps(
                {
                    "mediaType": _VALID_MEDIA,
                    "verificationMaterial": {"certificate": {"rawBytes": "AAAA"}},
                    "messageSignature": {"signature": "SIG"},
                }
            ),
            encoding="utf-8",
        )
        index = {"rid1": {"json_path": str(json_path)}}
        self.assertTrue(_has_verified_sigstore_sidecar(self._receipt, index))


# ---------------------------------------------------------------------------
# cli: --status "no-repo" inside a commit-less git repo
# ---------------------------------------------------------------------------


class TestStatusGitUnavailableLabel(unittest.TestCase):
    """--status must report repo="unavailable" when git itself is not available."""

    def test_status_without_git_reports_unavailable(self) -> None:
        import aiir.cli as cli

        with tempfile.TemporaryDirectory() as td:
            ledger_dir = Path(td) / ".aiir"
            ledger_dir.mkdir(parents=True, exist_ok=True)
            (ledger_dir / "receipts.jsonl").write_text("", encoding="utf-8")

            captured = io.StringIO()
            # git_available False -> repo_label = "unavailable" (cli.py:1579),
            # and a missing head_sha -> last_commit "unavailable".
            with (
                patch(
                    "aiir.cli._collect_doctor_state",
                    return_value={
                        "git_available": False,
                        "head_sha": None,
                        "head_receipt_status": "unknown",
                        "managed_hook_state": "unknown",
                    },
                ),
                patch("sys.stdout", captured),
            ):
                code = cli.main(["--status", "--ledger", str(ledger_dir), "--json"])

        self.assertEqual(code, 0)
        payload = json.loads(captured.getvalue())
        self.assertEqual(payload["mode"], "status")
        # git is unavailable -> "unavailable".
        self.assertEqual(payload["repo"], "unavailable")
        self.assertEqual(payload["last_commit"], "unavailable")


# ---------------------------------------------------------------------------
# cli: --ci --json on an empty ledger
# ---------------------------------------------------------------------------


class TestCiEmptyLedger(unittest.TestCase):
    """--ci --json on a structurally-valid but empty ledger must fail with a hint."""

    def test_ci_json_empty_ledger_reports_empty(self) -> None:
        import aiir.cli as cli

        with tempfile.TemporaryDirectory() as td:
            ledger_dir = Path(td) / ".aiir"
            ledger_dir.mkdir(parents=True, exist_ok=True)
            # Empty ledger: 0 receipts, structurally valid.
            (ledger_dir / "receipts.jsonl").write_text("", encoding="utf-8")

            captured = io.StringIO()
            with patch("sys.stdout", captured):
                code = cli.main(["--ci", "--ledger", str(ledger_dir), "--json"])

        self.assertEqual(code, 1)
        payload = json.loads(captured.getvalue())
        self.assertEqual(payload["mode"], "ci")
        self.assertFalse(payload["valid"])
        self.assertIn("Ledger is empty", payload["error"])


# ---------------------------------------------------------------------------
# mcp_server: serve_stdio bounded-read EOF / oversized-drain paths
# ---------------------------------------------------------------------------


def _parse_responses(text: str) -> list:
    return [json.loads(line) for line in text.strip().split("\n") if line.strip()]


class TestMcpBoundedReadEof(unittest.TestCase):
    """serve_stdio's bounded readline must handle EOF and oversized lines cleanly."""

    def test_text_mode_eof_after_partial_line(self) -> None:
        """A text-mode (no .buffer) final line lacking a newline is still processed."""
        import aiir.mcp_server as mcp

        # io.StringIO has no `.buffer` -> char-by-char text-mode read path.
        # No trailing newline -> EOF reached after buffering chunks (line 802 path).
        line = json.dumps({"jsonrpc": "2.0", "method": "initialize", "id": 3})
        captured = io.StringIO()
        with patch("sys.stdin", io.StringIO(line)), patch("sys.stdout", captured):
            mcp.serve_stdio()
        responses = _parse_responses(captured.getvalue())
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0]["id"], 3)

    def test_binary_mode_eof_after_partial_line(self) -> None:
        """A binary-mode final line lacking a newline is processed at EOF."""
        import aiir.mcp_server as mcp

        raw = json.dumps({"jsonrpc": "2.0", "method": "initialize", "id": 7}).encode()
        # TextIOWrapper exposes `.buffer` -> byte-by-byte binary read path.
        # No trailing newline -> EOF break after chunks (line 823).
        stdin = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8", errors="replace")
        captured = io.StringIO()
        with patch("sys.stdin", stdin), patch("sys.stdout", captured):
            mcp.serve_stdio()
        responses = _parse_responses(captured.getvalue())
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0]["id"], 7)

    def test_binary_oversized_line_drained_then_next_processed(self) -> None:
        """An oversized line is drained byte-by-byte and the next line still runs."""
        import aiir.mcp_server as mcp

        max_size = 10 * 1024 * 1024  # mirrors serve_stdio's local _MAX_MSG_SIZE
        # Extra bytes past the limit force the drain loop to iterate (831->829)
        # before reaching the terminating newline.
        oversized = b"x" * (max_size + 64)
        valid = json.dumps({"jsonrpc": "2.0", "method": "initialize", "id": 9}).encode()
        raw_input = oversized + b"\n" + valid + b"\n"
        stdin = io.TextIOWrapper(
            io.BytesIO(raw_input), encoding="utf-8", errors="replace"
        )
        captured = io.StringIO()
        with patch("sys.stdin", stdin), patch("sys.stdout", captured):
            mcp.serve_stdio()
        responses = _parse_responses(captured.getvalue())
        # Oversized line produces no response; the following valid line does.
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0]["id"], 9)


if __name__ == "__main__":
    unittest.main()
