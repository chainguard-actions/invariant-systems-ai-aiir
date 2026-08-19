"""Tests for GitHub integration (outputs, summary, action.yml)."""
# Copyright 2025-2026 Invariant Systems, Inc.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Import the module under test
import aiir.cli as cli


class TestGitHubOutputs(unittest.TestCase):
    """Test set_github_output uses heredoc pattern for multiline values."""

    def test_multiline_value_uses_delimiter(self):
        """Multiline values must use the heredoc pattern, not plain echo."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            tmppath = f.name

        try:
            with patch.dict(os.environ, {"GITHUB_OUTPUT": tmppath}):
                cli.set_github_output("test_key", "line1\nline2")

            content = Path(tmppath).read_text()
            # Should use delimiter pattern, not key=value
            self.assertIn("test_key<<", content)
            self.assertIn("line1\nline2", content)
            # Should NOT have the vulnerable pattern
            self.assertNotIn("test_key=line1", content)
        finally:
            os.unlink(tmppath)

    def test_single_line_value(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            tmppath = f.name

        try:
            with patch.dict(os.environ, {"GITHUB_OUTPUT": tmppath}):
                cli.set_github_output("count", "42")

            content = Path(tmppath).read_text()
            self.assertIn("count=42", content)
        finally:
            os.unlink(tmppath)


# ---------------------------------------------------------------------------
# CLI argument parsing tests
# ---------------------------------------------------------------------------


class TestGitHubOutputValueCap(unittest.TestCase):
    """R9-SEC-02: set_github_output must reject values exceeding 4 MB."""

    def test_value_under_limit_accepted(self):
        """Values under 4 MB should pass through normally."""
        tmpdir = tempfile.mkdtemp()
        output_file = Path(tmpdir, "GITHUB_OUTPUT")
        output_file.write_text("")
        try:
            with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_file)}):
                cli.set_github_output("key", "short_value")
            content = output_file.read_text()
            self.assertIn("key=short_value", content)
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_value_over_limit_rejected(self):
        """Values over 4 MB must raise ValueError."""
        huge_value = "x" * (4 * 1024 * 1024 + 1)
        with self.assertRaises(ValueError) as ctx:
            cli.set_github_output("key", huge_value)
        self.assertIn("too large", str(ctx.exception))

    def test_value_at_exact_limit_accepted(self):
        """Value at exactly 4 MB should be accepted."""
        tmpdir = tempfile.mkdtemp()
        output_file = Path(tmpdir, "GITHUB_OUTPUT")
        output_file.write_text("")
        exact_value = "x" * (4 * 1024 * 1024)
        try:
            with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_file)}):
                cli.set_github_output("k", exact_value)
            # Should not raise
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)


class TestActionYmlSafePath(unittest.TestCase):
    """R10-SEC-01: action.yml must use -P flag to prevent module shadowing."""

    def test_action_yml_uses_safe_path_flag(self):
        """The python invocation in action.yml must include -P."""
        action_path = Path(__file__).parent.parent / "action.yml"
        content = action_path.read_text(encoding="utf-8")
        self.assertIn("python -P -m aiir", content)

    def test_action_yml_has_sec01_comment(self):
        """The -P flag should have a comment explaining why."""
        action_path = Path(__file__).parent.parent / "action.yml"
        content = action_path.read_text(encoding="utf-8")
        self.assertIn("-P flag", content)


class TestGitHubApiRequestHardening(unittest.TestCase):
    """Coverage for URL scheme hardening in _github_api_request."""

    def test_rejects_non_http_scheme(self):
        """http:// and non-http schemes must be rejected to protect auth tokens.

        WS-E: GitHub API calls now require HTTPS. Both http:// (cleartext) and
        other non-HTTPS schemes (e.g. file://) must be rejected outright with a
        message that makes the HTTPS requirement clear. This test asserts the
        hardened behavior — reverting the fix would cause it to fail.
        """
        from aiir._github import _github_api_request

        # file:// must be rejected
        with self.assertRaises(RuntimeError) as ctx:
            _github_api_request(
                "file:///etc/passwd",
                {"ok": True},
                token="ghp_test",
                method="POST",
            )
        msg = str(ctx.exception)
        self.assertTrue(
            "non-HTTPS" in msg or "require HTTPS" in msg or "HTTPS" in msg,
            f"Expected HTTPS-required message, got: {msg!r}",
        )

        # http:// (cleartext) must also be rejected — auth tokens must not
        # travel over an unencrypted channel.
        with self.assertRaises(RuntimeError) as ctx2:
            _github_api_request(
                "http://api.github.com/repos/owner/repo/check-runs",
                {"ok": True},
                token="ghp_test",
                method="POST",
            )
        msg2 = str(ctx2.exception)
        self.assertTrue(
            "non-HTTPS" in msg2 or "require HTTPS" in msg2 or "HTTPS" in msg2,
            f"Expected HTTPS-required message for http://, got: {msg2!r}",
        )


class TestFindExistingCommentHttpsGuard(unittest.TestCase):
    """D4(net): _find_existing_comment must enforce the same HTTPS scheme guard
    as _github_api_request — an http:// GITHUB_API_URL must raise before any
    network contact, so the Bearer token is never sent in cleartext.

    EXPLOIT PROVEN (pre-fix): a local plaintext HTTP server captured the full
    Authorization header when GITHUB_API_URL=http://...

    POST-FIX: _find_existing_comment inspects the api_url scheme before
    building the request and raises RuntimeError for non-HTTPS schemes.
    """

    def test_http_api_url_raises_before_network_contact(self):
        """http:// GITHUB_API_URL must be rejected; no urlopen call must occur.

        This is the regression test for the PROVEN exploit: previously the
        function bypassed the HTTPS guard and sent the Bearer token over HTTP.
        After the fix it must raise immediately and NEVER call urlopen.
        """
        from aiir._github import _find_existing_comment

        with patch.dict(os.environ, {"GITHUB_API_URL": "http://evil.example.com"}):
            # Patch urlopen at the module level to detect if it is ever called.
            with patch("aiir._github.urlopen") as mock_urlopen:
                with self.assertRaises(RuntimeError) as ctx:
                    _find_existing_comment("owner/repo", "42", token="SECRET_TOKEN")

        # The raised error must mention HTTPS requirements.
        msg = str(ctx.exception)
        self.assertTrue(
            "HTTPS" in msg,
            f"Expected HTTPS error message, got: {msg!r}",
        )
        # urlopen must NEVER have been called — no bytes sent to the remote.
        mock_urlopen.assert_not_called()

    def test_http_scheme_no_token_leaked(self):
        """With http:// GITHUB_API_URL, the token must not be transmitted.

        Belt-and-suspenders check: even if the mock were bypassed, the token
        value should not appear in any captured network traffic.  We verify
        the exception is raised before the Request object is even opened.
        """
        from aiir._github import _find_existing_comment

        network_calls: list = []

        def fake_urlopen(req, timeout=None):
            # Record what would have been sent; test asserts this never runs.
            network_calls.append(getattr(req, "full_url", str(req)))
            raise AssertionError("urlopen must not be called for http:// URLs")

        with patch.dict(os.environ, {"GITHUB_API_URL": "http://attacker.example"}):
            with patch("aiir._github.urlopen", side_effect=fake_urlopen):
                with self.assertRaises(RuntimeError) as ctx:
                    _find_existing_comment("owner/repo", "1", token="TOP_SECRET")

        self.assertEqual(
            network_calls, [], "urlopen was invoked — token may have leaked"
        )
        self.assertIn("HTTPS", str(ctx.exception))

    def test_https_api_url_accepted_and_returns_comment_id(self):
        """https:// GITHUB_API_URL must pass the guard and return a comment id.

        Mocks the urlopen seam so no real network connection is made.
        """
        from aiir._github import _find_existing_comment, _PR_COMMENT_MARKER

        fake_comments = [
            {"id": 9001, "body": f"some preamble\n{_PR_COMMENT_MARKER}\nrest"},
            {"id": 9002, "body": "unrelated comment"},
        ]
        fake_response_bytes = json.dumps(fake_comments).encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_response_bytes
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch.dict(os.environ, {"GITHUB_API_URL": "https://api.github.com"}):
            with patch("aiir._github.urlopen", return_value=mock_resp) as mock_open:
                result = _find_existing_comment("owner/repo", "42", token="ghp_test")

        self.assertEqual(result, 9001)
        mock_open.assert_called_once()
        # Verify the request used HTTPS
        req_arg = mock_open.call_args[0][0]
        self.assertTrue(
            req_arg.full_url.startswith("https://"),
            f"Expected HTTPS URL, got {req_arg.full_url!r}",
        )

    def test_https_returns_none_when_no_aiir_comment(self):
        """https:// returns None when no comment contains the AIIR marker."""
        from aiir._github import _find_existing_comment

        fake_comments = [
            {"id": 1, "body": "just a normal comment"},
            {"id": 2, "body": "another comment without the marker"},
        ]
        fake_response_bytes = json.dumps(fake_comments).encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_response_bytes
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch.dict(os.environ, {"GITHUB_API_URL": "https://api.github.com"}):
            with patch("aiir._github.urlopen", return_value=mock_resp):
                result = _find_existing_comment("owner/repo", "7", token="ghp_test")

        self.assertIsNone(result)

    def test_missing_token_returns_none_without_network(self):
        """No token → return None immediately; never attempt a network call."""
        from aiir._github import _find_existing_comment

        with patch.dict(
            os.environ, {"GITHUB_API_URL": "https://api.github.com"}, clear=False
        ):
            # Ensure GITHUB_TOKEN is absent so the function falls back to no-token path.
            env = {k: v for k, v in os.environ.items() if k != "GITHUB_TOKEN"}
            with patch.dict(os.environ, env, clear=True):
                with patch("aiir._github.urlopen") as mock_open:
                    result = _find_existing_comment("owner/repo", "1", token=None)

        self.assertIsNone(result)
        mock_open.assert_not_called()


class TestValidateRepoShape(unittest.TestCase):
    """_validate_repo_shape must block path-traversal and query injection."""

    def _validate(self, repo: str):
        from aiir._github import _validate_repo_shape

        return _validate_repo_shape(repo)

    def test_valid_repos_accepted(self):
        """Standard owner/repo values must pass validation."""
        valid_repos = [
            "owner/repo",
            "my-org/my-repo",
            "Org123/Repo.name",
            "a_b/c-d",
            "A/B",
        ]
        for repo in valid_repos:
            with self.subTest(repo=repo):
                # Must not raise.
                self._validate(repo)

    def test_path_traversal_rejected(self):
        """Path-traversal segments must be rejected."""
        with self.assertRaises(RuntimeError) as ctx:
            self._validate("../etc/passwd")
        self.assertIn("Invalid repo shape", str(ctx.exception))

    def test_query_injection_rejected(self):
        """Repos with query strings must be rejected."""
        with self.assertRaises(RuntimeError) as ctx:
            self._validate("owner/repo?foo=bar")
        self.assertIn("Invalid repo shape", str(ctx.exception))

    def test_no_slash_rejected(self):
        """A value without a slash is not a valid owner/repo."""
        with self.assertRaises(RuntimeError):
            self._validate("noslash")

    def test_too_many_slashes_rejected(self):
        """More than one slash (a/b/c) must be rejected."""
        with self.assertRaises(RuntimeError):
            self._validate("a/b/c")

    def test_special_chars_rejected(self):
        """Dollar signs, semicolons and other special chars must be rejected."""
        bad = ["own$er/repo", "owner/re;po", "owner/re po", "owner/<script>"]
        for repo in bad:
            with self.subTest(repo=repo):
                with self.assertRaises(RuntimeError):
                    self._validate(repo)

    def test_empty_string_rejected(self):
        """Empty string is not a valid repo."""
        with self.assertRaises(RuntimeError):
            self._validate("")

    def test_find_existing_comment_rejects_bad_repo(self):
        """_find_existing_comment must raise for path-injection repo shapes."""
        from aiir._github import _find_existing_comment

        with patch.dict(os.environ, {"GITHUB_API_URL": "https://api.github.com"}):
            with patch("aiir._github.urlopen") as mock_open:
                with self.assertRaises(RuntimeError) as ctx:
                    _find_existing_comment("../evil/path", "1", token="tok")

        self.assertIn("Invalid repo shape", str(ctx.exception))
        mock_open.assert_not_called()

    def test_post_pr_comment_rejects_bad_repo(self):
        """post_pr_comment must raise for path-injection repo shapes."""
        from aiir._github import post_pr_comment

        with patch.dict(os.environ, {"GITHUB_API_URL": "https://api.github.com"}):
            with self.assertRaises(RuntimeError) as ctx:
                post_pr_comment(
                    [],
                    repo="../evil/path",
                    pr_number="1",
                    token="tok",
                )

        self.assertIn("Invalid repo shape", str(ctx.exception))
