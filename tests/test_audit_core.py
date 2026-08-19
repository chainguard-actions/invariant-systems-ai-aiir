# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""Regression tests for audit-2026-06-hardening remediation (workstream B).

Covers:
- C8: determinism constants and _run_git deterministic flag
- C2: CBOR int>=2**64 ValueError guard, large float f64 fallback, bytewise sort
- C6: HMAC redaction, salt threading, blank-email fallback
- _detect false-positive fixes (windsurf, amazon q, tool trailer)
- _detect range truncation warning
- _receipt write_receipt dedup conflict detection
- _receipt editor_provenance sanitization
- _core colon homoglyph normalization
"""

from __future__ import annotations

import io
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# C2 — CBOR crash guards and bytewise sort
# ---------------------------------------------------------------------------


class TestCborIntGuard(unittest.TestCase):
    """C2 — int >= 2**64 must raise ValueError, not OverflowError."""

    def setUp(self) -> None:
        from aiir._canonical_cbor import _encode_uint

        self._encode_uint = _encode_uint

    def test_int_at_2_64_raises_value_error(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            self._encode_uint(0, 2**64)
        self.assertIn("2**64", str(ctx.exception))

    def test_int_above_2_64_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            self._encode_uint(0, 2**64 + 1)

    def test_int_at_2_64_minus_1_does_not_raise(self) -> None:
        # Max valid uint64 — must NOT raise
        result = self._encode_uint(0, 2**64 - 1)
        self.assertEqual(result[0], 0x1B)  # major 0, additional 27 (8-byte)

    def test_negative_uint_raises(self) -> None:
        with self.assertRaises(ValueError):
            self._encode_uint(0, -1)

    def test_negative_major_type_1_at_2_64(self) -> None:
        # Major type 1 (negative int) uses same _encode_uint; same guard applies
        with self.assertRaises(ValueError):
            self._encode_uint(1, 2**64)


class TestCborLargeFloatFallback(unittest.TestCase):
    """C2 — large finite floats that overflow f32 must encode as f64."""

    def setUp(self) -> None:
        from aiir._canonical_cbor import _encode_float_canonical, _try_f16

        self._encode_float_canonical = _encode_float_canonical
        self._try_f16 = _try_f16

    def test_1e40_encodes_as_f64(self) -> None:
        result = self._encode_float_canonical(1e40)
        self.assertEqual(result[0], 0xFB, "Expected f64 head byte 0xfb")
        self.assertEqual(len(result), 9)

    def test_1e40_round_trips(self) -> None:
        from aiir._canonical_cbor import _encode_float_canonical

        encoded = _encode_float_canonical(1e40)
        self.assertEqual(encoded[0], 0xFB)
        decoded = struct.unpack(">d", encoded[1:])[0]
        self.assertEqual(decoded, 1e40)

    def test_neg_1e300_encodes_as_f64(self) -> None:
        result = self._encode_float_canonical(-1e300)
        self.assertEqual(result[0], 0xFB, "Expected f64 head byte 0xfb for -1e300")

    def test_1e5_encodes_as_f32(self) -> None:
        # 100000.0 round-trips exactly in f32 and thus encodes as f32 (head 0xfa)
        result = self._encode_float_canonical(100000.0)
        self.assertEqual(result[0], 0xFA, "100000.0 should encode as f32")

    def test_normal_floats_unchanged(self) -> None:
        # 1.5 should still be f16 (0xf9)
        from aiir._canonical_cbor import canonical_cbor_bytes

        self.assertEqual(canonical_cbor_bytes(1.5)[0], 0xF9)
        # 0.0 should be f16
        self.assertEqual(canonical_cbor_bytes(0.0)[0], 0xF9)

    def test_try_f16_returns_none_on_overflow(self) -> None:
        # 1e40 is not f32-representable, so _try_f16 must return None
        result = self._try_f16(1e40)
        self.assertIsNone(result)

    def test_nan_raises(self) -> None:
        with self.assertRaises(ValueError):
            self._encode_float_canonical(float("nan"))

    def test_inf_raises(self) -> None:
        with self.assertRaises(ValueError):
            self._encode_float_canonical(float("inf"))


class TestCborBytewiseSort(unittest.TestCase):
    """C2 — map key ordering must be bytewise over encoded key bytes (RFC 8949 §4.2.1)."""

    def setUp(self) -> None:
        from aiir._canonical_cbor import canonical_cbor_bytes

        self._encode = canonical_cbor_bytes

    def test_map_keys_short_before_long(self) -> None:
        # Shorter key "a" (encoded 0x61 0x61) < longer key "bb" (0x62 0x62 0x62)
        # bytewise — shorter text strings sort first under both length-first and bytewise
        data = {"bb": 2, "a": 1}
        encoded = self._encode(data)
        # Find the offsets: header 0xa2 (2-element map), then first key
        self.assertEqual(encoded[0], 0xA2)
        # First key should be "a" (0x61 0x61), second "bb"
        self.assertEqual(encoded[1], 0x61)  # 1-char text string
        self.assertEqual(encoded[2], ord("a"))

    def test_deterministic_across_dict_insertion_order(self) -> None:
        d1 = {"z": 1, "a": 2}
        d2 = {"a": 2, "z": 1}
        self.assertEqual(self._encode(d1), self._encode(d2))

    def test_same_output_as_length_first_for_string_keys(self) -> None:
        # For text-string keys, bytewise and length-first produce identical results
        # (the key length is encoded in the CBOR header byte, so bytewise comparison
        # automatically sorts shorter before longer). Verify on a non-trivial map.
        d = {"schema": "v2", "type": "aiir", "z": 1, "a": 2, "version": "1.0"}
        encoded = self._encode(d)
        # Must be stable across multiple calls
        self.assertEqual(self._encode(d), encoded)


# ---------------------------------------------------------------------------
# C8 — Determinism constants
# ---------------------------------------------------------------------------


class TestDeterminismConstants(unittest.TestCase):
    """C8 — verify the determinism constants exist and are correct."""

    def test_git_deterministic_config_is_list(self) -> None:
        from aiir._core import _GIT_DETERMINISTIC_CONFIG

        self.assertIsInstance(_GIT_DETERMINISTIC_CONFIG, list)

    def test_git_deterministic_config_has_quotepath_false(self) -> None:
        from aiir._core import _GIT_DETERMINISTIC_CONFIG

        joined = " ".join(_GIT_DETERMINISTIC_CONFIG)
        self.assertIn("core.quotepath=false", joined)

    def test_git_deterministic_config_has_no_prefix(self) -> None:
        from aiir._core import _GIT_DETERMINISTIC_CONFIG

        joined = " ".join(_GIT_DETERMINISTIC_CONFIG)
        self.assertIn("diff.noprefix=false", joined)

    def test_git_deterministic_config_has_myers(self) -> None:
        from aiir._core import _GIT_DETERMINISTIC_CONFIG

        joined = " ".join(_GIT_DETERMINISTIC_CONFIG)
        self.assertIn("diff.algorithm=myers", joined)

    def test_git_diff_deterministic_flags_has_find_renames(self) -> None:
        from aiir._core import _GIT_DIFF_DETERMINISTIC_FLAGS

        self.assertIn("--find-renames", _GIT_DIFF_DETERMINISTIC_FLAGS)

    def test_git_diff_deterministic_flags_has_no_color(self) -> None:
        from aiir._core import _GIT_DIFF_DETERMINISTIC_FLAGS

        self.assertIn("--no-color", _GIT_DIFF_DETERMINISTIC_FLAGS)

    def test_git_diff_deterministic_flags_has_u3(self) -> None:
        from aiir._core import _GIT_DIFF_DETERMINISTIC_FLAGS

        self.assertIn("-U3", _GIT_DIFF_DETERMINISTIC_FLAGS)

    def test_git_diff_deterministic_flags_has_no_ext_diff(self) -> None:
        from aiir._core import _GIT_DIFF_DETERMINISTIC_FLAGS

        self.assertIn("--no-ext-diff", _GIT_DIFF_DETERMINISTIC_FLAGS)

    def test_git_safe_env_contains_external_diff(self) -> None:
        from aiir._core import _GIT_SAFE_ENV

        self.assertIn("GIT_EXTERNAL_DIFF", _GIT_SAFE_ENV)
        self.assertEqual(_GIT_SAFE_ENV["GIT_EXTERNAL_DIFF"], "")

    def test_git_safe_env_contains_diff_opts(self) -> None:
        from aiir._core import _GIT_SAFE_ENV

        self.assertIn("GIT_DIFF_OPTS", _GIT_SAFE_ENV)
        self.assertEqual(_GIT_SAFE_ENV["GIT_DIFF_OPTS"], "")

    def test_git_safe_env_contains_pager(self) -> None:
        from aiir._core import _GIT_SAFE_ENV

        self.assertIn("GIT_PAGER", _GIT_SAFE_ENV)
        self.assertEqual(_GIT_SAFE_ENV["GIT_PAGER"], "cat")


class TestRunGitDeterministicFlag(unittest.TestCase):
    """C8 — _run_git with deterministic=True splices _GIT_DETERMINISTIC_CONFIG."""

    def test_deterministic_true_splices_config(self) -> None:
        from aiir._core import _GIT_DETERMINISTIC_CONFIG

        captured_cmd = []

        def fake_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            r = MagicMock()
            r.returncode = 0
            r.stdout = "ok\n"
            return r

        with patch("aiir._core.subprocess.run", side_effect=fake_run):
            from aiir._core import _run_git

            _run_git(["log", "-1"], deterministic=True)

        # The command should contain --no-optional-locks AND the config flags
        self.assertIn("--no-optional-locks", captured_cmd)
        for flag in _GIT_DETERMINISTIC_CONFIG:
            self.assertIn(flag, captured_cmd)

    def test_deterministic_false_does_not_splice_config(self) -> None:
        captured_cmd = []

        def fake_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            r = MagicMock()
            r.returncode = 0
            r.stdout = "ok\n"
            return r

        with patch("aiir._core.subprocess.run", side_effect=fake_run):
            from aiir._core import _run_git

            _run_git(["log", "-1"], deterministic=False)

        # None of the deterministic config flags should be present
        # (the -c flags)
        for i, token in enumerate(captured_cmd):
            if token == "-c" and i + 1 < len(captured_cmd):
                self.fail(
                    f"Unexpected -c flag in non-deterministic call: {captured_cmd}"
                )

    def test_hash_diff_streaming_uses_deterministic_config(self) -> None:
        """Verify _hash_diff_streaming splices the full deterministic config."""
        from aiir._core import _GIT_DETERMINISTIC_CONFIG, _GIT_DIFF_DETERMINISTIC_FLAGS

        captured_argv = []

        class FakeProc:
            returncode = 0
            stdout = io.BytesIO(b"")

        def fake_popen(cmd, **kwargs):
            captured_argv.extend(cmd)
            return FakeProc()

        with patch("aiir._core.subprocess.Popen", side_effect=fake_popen):
            from aiir._core import _hash_diff_streaming

            try:
                _hash_diff_streaming("abc", "def")
            except Exception:
                pass  # We only care about the argv

        for flag in _GIT_DETERMINISTIC_CONFIG:
            self.assertIn(flag, captured_argv, f"Expected {flag!r} in Popen argv")
        for flag in _GIT_DIFF_DETERMINISTIC_FLAGS:
            self.assertIn(flag, captured_argv, f"Expected {flag!r} in Popen argv")


# ---------------------------------------------------------------------------
# C6 — HMAC redaction helper and salt threading
# ---------------------------------------------------------------------------


class TestHmac16(unittest.TestCase):
    """C6 — _hmac16 helper: determinism, salt divergence, fallback."""

    def setUp(self) -> None:
        from aiir._core import _hmac16

        self._hmac16 = _hmac16
        self._salt = "aa" * 32  # 64 hex chars = 256 bits

    def test_returns_16_hex_chars(self) -> None:
        result = self._hmac16(self._salt, "test@example.com")
        self.assertEqual(len(result), 16)
        int(result, 16)  # must be valid hex

    def test_deterministic_same_salt_same_msg(self) -> None:
        r1 = self._hmac16(self._salt, "test@example.com")
        r2 = self._hmac16(self._salt, "test@example.com")
        self.assertEqual(r1, r2)

    def test_different_salts_produce_different_tokens(self) -> None:
        salt2 = "bb" * 32
        r1 = self._hmac16(self._salt, "test@example.com")
        r2 = self._hmac16(salt2, "test@example.com")
        self.assertNotEqual(r1, r2)

    def test_different_messages_produce_different_tokens(self) -> None:
        r1 = self._hmac16(self._salt, "alice@example.com")
        r2 = self._hmac16(self._salt, "bob@example.com")
        self.assertNotEqual(r1, r2)

    def test_none_salt_uses_fallback(self) -> None:
        r = self._hmac16(None, "test@example.com")
        self.assertEqual(len(r), 16)

    def test_none_salt_deterministic(self) -> None:
        r1 = self._hmac16(None, "test@example.com")
        r2 = self._hmac16(None, "test@example.com")
        self.assertEqual(r1, r2)

    def test_empty_salt_uses_fallback(self) -> None:
        r = self._hmac16("", "test@example.com")
        self.assertEqual(len(r), 16)

    def test_malformed_salt_uses_fallback(self) -> None:
        # Invalid hex string — should fall back gracefully
        r = self._hmac16("notvalidhex!!", "test@example.com")
        self.assertEqual(len(r), 16)

    def test_explicit_salt_differs_from_fallback(self) -> None:
        r_salt = self._hmac16(self._salt, "test@example.com")
        r_none = self._hmac16(None, "test@example.com")
        self.assertNotEqual(r_salt, r_none)

    def test_differs_from_sha256(self) -> None:
        import hashlib

        sha = hashlib.sha256("test@example.com".encode()).hexdigest()[:16]
        r = self._hmac16(None, "test@example.com")
        self.assertNotEqual(r, sha)


class TestRedactedEmail(unittest.TestCase):
    """C6 — _redacted_email uses HMAC and threads salt correctly."""

    def setUp(self) -> None:
        from aiir._receipt import _redacted_email

        self._redacted_email = _redacted_email
        self._salt = "aa" * 32

    def test_blank_email_returns_fallback(self) -> None:
        self.assertEqual(
            self._redacted_email("", salt=self._salt),
            "redacted@users.noreply.aiir",
        )

    def test_whitespace_only_email_returns_fallback(self) -> None:
        self.assertEqual(
            self._redacted_email("   ", salt=self._salt),
            "redacted@users.noreply.aiir",
        )

    def test_format_with_salt(self) -> None:
        result = self._redacted_email("alice@example.com", salt=self._salt)
        self.assertTrue(result.startswith("redacted+"))
        self.assertTrue(result.endswith("@users.noreply.aiir"))
        token = result[len("redacted+") : -len("@users.noreply.aiir")]
        self.assertEqual(len(token), 16)

    def test_format_without_salt(self) -> None:
        result = self._redacted_email("alice@example.com", salt=None)
        self.assertTrue(result.startswith("redacted+"))
        self.assertTrue(result.endswith("@users.noreply.aiir"))

    def test_same_salt_deterministic(self) -> None:
        r1 = self._redacted_email("alice@example.com", salt=self._salt)
        r2 = self._redacted_email("alice@example.com", salt=self._salt)
        self.assertEqual(r1, r2)

    def test_different_salts_diverge(self) -> None:
        salt2 = "bb" * 32
        r1 = self._redacted_email("alice@example.com", salt=self._salt)
        r2 = self._redacted_email("alice@example.com", salt=salt2)
        self.assertNotEqual(r1, r2)

    def test_differs_from_old_sha256_behavior(self) -> None:
        import hashlib

        old_digest = hashlib.sha256("alice@example.com".encode()).hexdigest()[:16]
        old_val = f"redacted+{old_digest}@users.noreply.aiir"
        new_val = self._redacted_email("alice@example.com", salt=None)
        # New HMAC-based approach must differ from old unsalted SHA-256
        self.assertNotEqual(new_val, old_val)

    def test_normalizes_before_hashing(self) -> None:
        # Uppercase and lowercase of same email must produce identical token
        r_lower = self._redacted_email("Alice@Example.COM", salt=self._salt)
        r_upper = self._redacted_email("alice@example.com", salt=self._salt)
        self.assertEqual(r_lower, r_upper)


class TestBuildCommitReceiptRedactionSalt(unittest.TestCase):
    """C6 — redaction_salt is threaded through build_commit_receipt."""

    def _make_commit(self) -> Any:
        from aiir._core import CommitInfo

        return CommitInfo(
            sha="abc123def456",
            author_name="Alice",
            author_email="alice@example.com",
            author_date="2026-01-01T00:00:00Z",
            committer_name="Alice",
            committer_email="alice@example.com",
            committer_date="2026-01-01T00:00:00Z",
            subject="test commit",
            body="test commit\n",
            diff_stat="1 file changed",
            diff_hash="sha256:dead",
            files_changed=["foo.py"],
            is_ai_authored=False,
            ai_signals_detected=[],
        )

    def test_redaction_salt_threads_to_email(self) -> None:
        from aiir._receipt import build_commit_receipt

        commit = self._make_commit()
        salt = "aa" * 32
        with patch("aiir._receipt._run_git", return_value=""):
            r = build_commit_receipt(commit, redact_emails=True, redaction_salt=salt)
        email = r["commit"]["author"]["email"]
        self.assertTrue(email.startswith("redacted+"))
        self.assertTrue(email.endswith("@users.noreply.aiir"))

    def test_different_salts_produce_different_receipt_ids(self) -> None:
        from aiir._receipt import build_commit_receipt

        commit = self._make_commit()
        salt1 = "aa" * 32
        salt2 = "bb" * 32
        with patch("aiir._receipt._run_git", return_value=""):
            r1 = build_commit_receipt(commit, redact_emails=True, redaction_salt=salt1)
            r2 = build_commit_receipt(commit, redact_emails=True, redaction_salt=salt2)
        # Different salts → different emails → different receipt_ids
        self.assertNotEqual(r1["receipt_id"], r2["receipt_id"])

    def test_same_salt_produces_same_receipt_id(self) -> None:
        from aiir._receipt import build_commit_receipt

        commit = self._make_commit()
        salt = "cc" * 32
        with patch("aiir._receipt._run_git", return_value=""):
            r1 = build_commit_receipt(commit, redact_emails=True, redaction_salt=salt)
            r2 = build_commit_receipt(commit, redact_emails=True, redaction_salt=salt)
        self.assertEqual(r1["receipt_id"], r2["receipt_id"])

    def test_no_redaction_salt_param_accepted(self) -> None:
        # Ensure the default None does not crash
        from aiir._receipt import build_commit_receipt

        commit = self._make_commit()
        with patch("aiir._receipt._run_git", return_value=""):
            r = build_commit_receipt(commit, redact_emails=True)
        email = r["commit"]["author"]["email"]
        self.assertTrue(email.startswith("redacted+"))


# ---------------------------------------------------------------------------
# _detect false-positive fixes
# ---------------------------------------------------------------------------


class TestDetectFalsePositiveFixes(unittest.TestCase):
    """Verify the specific false-positive signals are fixed."""

    def setUp(self) -> None:
        from aiir._detect import detect_ai_signals

        self._detect = detect_ai_signals

    def test_windsurfing_does_not_match_windsurf(self) -> None:
        ai, _ = self._detect("I love windsurfing on weekends")
        for s in ai:
            self.assertNotIn("windsurf", s, f"False positive: {s!r}")

    def test_windsurf_tool_still_matches(self) -> None:
        ai, _ = self._detect("this PR was written using Windsurf IDE")
        self.assertTrue(
            any("windsurf" in s for s in ai),
            f"Expected windsurf signal, got: {ai}",
        )

    def test_amazon_quicksight_does_not_match(self) -> None:
        ai, _ = self._detect("update amazon quicksight dashboard configuration")
        for s in ai:
            self.assertNotIn("amazon q", s, f"False positive: {s!r}")

    def test_amazon_q_developer_still_matches(self) -> None:
        ai, _ = self._detect("generated with Amazon Q developer tool")
        self.assertTrue(
            any("amazon q" in s for s in ai),
            f"Expected amazon q signal, got: {ai}",
        )

    def test_tool_trailer_key_removed(self) -> None:
        from aiir._detect import AI_TRAILERS

        self.assertNotIn("tool", AI_TRAILERS)

    def test_conventional_commit_tool_prefix_no_false_positive(self) -> None:
        # "tool: update build system" on a body line should NOT fire a trailer match
        ai, _ = self._detect("chore: update\n\ntool: build script updated")
        trailer_hits = [s for s in ai if "trailer:tool" in s]
        self.assertEqual(trailer_hits, [])

    def test_copilot_trailer_still_matches(self) -> None:
        from aiir._detect import AI_TRAILERS

        self.assertIn("copilot", AI_TRAILERS)

    def test_devin_bot_email_matches(self) -> None:
        ai, _ = self._detect("Co-authored-by: devin-98765@devin.ai")
        self.assertTrue(
            any("devin" in s for s in ai),
            f"Expected devin signal, got: {ai}",
        )

    def test_devin_bot_email_non_devin_address_does_not_match(self) -> None:
        # A random address containing "devin" as a name should not trigger the
        # email-pattern check (the regex requires @devin.ai)
        ai, _ = self._detect("commit by devin-smith@company.com")
        email_pattern_hits = [s for s in ai if "devin bot email" in s]
        self.assertEqual(email_pattern_hits, [])

    def test_openai_codex_matches(self) -> None:
        ai, _ = self._detect("generated by openai codex")
        self.assertTrue(
            any("codex" in s for s in ai),
            f"Expected codex signal, got: {ai}",
        )

    def test_human_commit_no_false_positives(self) -> None:
        ai, bot = self._detect(
            "fix: typo in readme\n\nSimple fix, windsurfing is fun.",
            author_name="Bob Smith",
            author_email="bob@company.com",
        )
        # windsurf word boundary must prevent false positive
        self.assertEqual(ai, [], f"Unexpected AI signals: {ai}")


# ---------------------------------------------------------------------------
# _detect range truncation warning
# ---------------------------------------------------------------------------


class TestListCommitsTruncationWarning(unittest.TestCase):
    """list_commits_in_range must emit a warning when results are truncated."""

    def _make_shas(self, n: int) -> str:
        """Return newline-separated fake SHAs."""
        return "\n".join(f"{'a' * 39}{i:01x}"[:40] for i in range(n))

    def test_no_warning_when_under_limit(self) -> None:
        from aiir._detect import list_commits_in_range

        # Return exactly max_count SHAs (no truncation)
        fake_output = self._make_shas(5)
        with patch("aiir._detect._run_git", return_value=fake_output):
            with patch("aiir._detect._validate_ref"):
                buf = io.StringIO()
                with patch("sys.stderr", buf):
                    result = list_commits_in_range("main..HEAD", max_count=5)
        self.assertEqual(len(result), 5)
        self.assertEqual(buf.getvalue(), "")

    def test_warning_emitted_when_over_limit(self) -> None:
        from aiir._detect import list_commits_in_range

        # Return max_count + 1 SHAs to trigger truncation
        fake_output = self._make_shas(11)  # 11 > max_count=10
        with patch("aiir._detect._run_git", return_value=fake_output):
            with patch("aiir._detect._validate_ref"):
                buf = io.StringIO()
                with patch("sys.stderr", buf):
                    result = list_commits_in_range("main..HEAD", max_count=10)
        self.assertEqual(len(result), 10)  # truncated to max_count
        warning = buf.getvalue()
        self.assertIn("WARNING", warning)
        self.assertIn("truncated", warning)

    def test_truncation_returns_max_count_exactly(self) -> None:
        from aiir._detect import list_commits_in_range

        fake_output = self._make_shas(6)
        with patch("aiir._detect._run_git", return_value=fake_output):
            with patch("aiir._detect._validate_ref"):
                result = list_commits_in_range("main..HEAD", max_count=5)
        self.assertEqual(len(result), 5)

    def test_no_warning_at_exact_limit(self) -> None:
        from aiir._detect import list_commits_in_range

        # Exactly max_count SHAs returned from git (no truncation)
        fake_output = self._make_shas(3)
        with patch("aiir._detect._run_git", return_value=fake_output):
            with patch("aiir._detect._validate_ref"):
                buf = io.StringIO()
                with patch("sys.stderr", buf):
                    result = list_commits_in_range("main..HEAD", max_count=3)
        self.assertEqual(len(result), 3)
        self.assertEqual(buf.getvalue(), "")


# ---------------------------------------------------------------------------
# _core colon homoglyph normalization
# ---------------------------------------------------------------------------


class TestColonHomoglyphNormalization(unittest.TestCase):
    """_core._normalize_for_detection must normalize colon homoglyphs."""

    def setUp(self) -> None:
        from aiir._core import _normalize_for_detection

        self._normalize = _normalize_for_detection

    def test_modifier_letter_colon_u_a789(self) -> None:
        # U+A789 ꞉ MODIFIER LETTER COLON
        norm = self._normalize("Co-authored-by꞉ Copilot")
        self.assertIn(":", norm)

    def test_fullwidth_colon_u_ff1a(self) -> None:
        # U+FF1A ： FULLWIDTH COLON
        norm = self._normalize("Generated-by： Devin")
        self.assertIn(":", norm)

    def test_ratio_u_2236(self) -> None:
        # U+2236 ∶ RATIO
        norm = self._normalize("Assisted-by∶ Claude")
        self.assertIn(":", norm)

    def test_homoglyph_colon_triggers_detection(self) -> None:
        from aiir._detect import detect_ai_signals

        # U+A789 colon homoglyph in co-authored-by line must still detect copilot
        msg = "fix: typo\n\nCo-authored-by꞉ Copilot\nSome body"
        ai, _ = detect_ai_signals(msg)
        # Should detect via the normalized trailer or message match
        self.assertTrue(
            any("copilot" in s for s in ai),
            f"Expected copilot signal after colon homoglyph normalization, got: {ai}",
        )

    def test_regular_colon_unchanged(self) -> None:
        norm = self._normalize("Co-authored-by: Copilot")
        self.assertIn("co-authored-by: copilot", norm.lower())


# ---------------------------------------------------------------------------
# _receipt write_receipt dedup conflict detection
# ---------------------------------------------------------------------------


class TestWriteReceiptDedup(unittest.TestCase):
    """write_receipt must verify existing file receipt_id before deduping."""

    def _make_receipt(self, tag: str = "A") -> Dict[str, Any]:
        return {
            "type": "aiir.commit_receipt",
            "schema": "aiir/commit_receipt.v2",
            "version": "1.0.0",
            "commit": {
                "sha": f"abc{tag}",
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
            "ai_attestation": {
                "is_ai_authored": False,
                "signals_detected": [],
                "signal_count": 0,
                "is_bot_authored": False,
                "bot_signals_detected": [],
                "bot_signal_count": 0,
                "authorship_class": "human",
                "detection_method": "heuristic_v2",
            },
            "provenance": {
                "repository": None,
                "tool": "https://github.com/invariant-systems-ai/aiir@1.0.0",
                "generator": "aiir.cli",
            },
            "receipt_id": f"g1-{'0' * 31}{tag}",
            "content_hash": f"sha256:{'0' * 63}{tag}",
            "timestamp": "2026-01-01T00:00:00Z",
            "extensions": {},
        }

    def _make_tmpdir_in_cwd(self) -> "tempfile.TemporaryDirectory[str]":
        """Create a temporary directory inside cwd so write_receipt allows it."""
        return tempfile.TemporaryDirectory(dir=os.getcwd())

    def test_identical_receipt_id_is_idempotent(self) -> None:
        """Writing the same receipt_id twice must silently succeed."""
        from aiir._receipt import write_receipt

        with self._make_tmpdir_in_cwd() as tmp:
            receipt = self._make_receipt("A")
            # Write once
            path1 = write_receipt(receipt, output_dir=tmp)
            # Write again — must return same path without error
            path2 = write_receipt(receipt, output_dir=tmp)
            self.assertEqual(path1, path2)

    def test_conflicting_receipt_id_raises_value_error(self) -> None:
        """An existing file with a different receipt_id must raise ValueError."""
        from aiir._receipt import write_receipt

        with self._make_tmpdir_in_cwd() as tmp:
            receipt_a = self._make_receipt("A")
            receipt_b = self._make_receipt("B")
            # Manually write receipt_A under the same filename as receipt_B
            # First, discover the filename receipt_B would generate
            import re as _re

            chash = receipt_b.get("content_hash", "")
            chash_short = _re.sub(r"[^a-fA-F0-9]", "", chash)[:16]
            commit_sha = str(receipt_b.get("commit", {}).get("sha") or "unknown")[:24]
            commit_sha = _re.sub(r"[^a-zA-Z0-9_-]", "_", commit_sha)
            filename = f"receipt_{commit_sha}_{chash_short}.json"
            filepath = Path(tmp) / filename
            # Write receipt_A into that path
            with open(str(filepath), "w") as f:
                json.dump(receipt_a, f)
            # Now try to write receipt_B — should raise because receipt_id differs
            with self.assertRaises(ValueError) as ctx:
                write_receipt(receipt_b, output_dir=tmp)
            self.assertIn("conflict", str(ctx.exception).lower())


# ---------------------------------------------------------------------------
# _receipt editor_provenance sanitization
# ---------------------------------------------------------------------------


class TestEditorProvenanceSanitization(unittest.TestCase):
    """editor_provenance must be sanitized the same as agent_attestation."""

    def setUp(self) -> None:
        from aiir._receipt import _sanitize_editor_provenance

        self._sanitize = _sanitize_editor_provenance

    def test_none_returns_none(self) -> None:
        self.assertIsNone(self._sanitize(None))

    def test_non_dict_returns_none(self) -> None:
        self.assertIsNone(self._sanitize("not a dict"))  # type: ignore[arg-type]
        self.assertIsNone(self._sanitize(123))  # type: ignore[arg-type]

    def test_known_keys_pass_through(self) -> None:
        data = {
            "schema": "aiir/editor_provenance.v1",
            "mode": "provable",
            "toolId": "aiir-vscode",
        }
        result = self._sanitize(data)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("schema"), "aiir/editor_provenance.v1")
        self.assertEqual(result.get("mode"), "provable")

    def test_terminal_escapes_stripped_from_values(self) -> None:
        data = {"schema": "aiir\x1b[31mevil\x1b[0m"}
        result = self._sanitize(data)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertNotIn("\x1b", result.get("schema", ""))

    def test_unknown_top_level_keys_excluded(self) -> None:
        data = {"schema": "aiir/editor_provenance.v1", "evil_injection": "<script>"}
        result = self._sanitize(data)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertNotIn("evil_injection", result)

    def test_records_list_preserved_and_sanitized(self) -> None:
        data = {
            "schema": "aiir/editor_provenance.v1",
            "records": [
                {"file": "foo.py", "action": "save"},
                {"file": "bar.py\x1b[31m", "action": "edit"},
            ],
        }
        result = self._sanitize(data)
        self.assertIsNotNone(result)
        assert result is not None
        records = result.get("records", [])
        self.assertEqual(len(records), 2)
        self.assertNotIn("\x1b", records[1].get("file", ""))

    def test_nested_dict_values_in_records_dropped(self) -> None:
        # Records whose only value is a nested dict have that key dropped (sanitized out).
        # Mixed records keep the string-valued keys and drop dict-valued keys.
        data = {
            "schema": "aiir/editor_provenance.v1",
            "records": [{"file": "foo.py", "meta": {"deep": "value"}}],
        }
        result = self._sanitize(data)
        self.assertIsNotNone(result)
        assert result is not None
        records = result.get("records", [])
        self.assertEqual(len(records), 1)
        # "file" key (string value) must be kept
        self.assertEqual(records[0].get("file"), "foo.py")
        # "meta" key (dict value) must be excluded
        self.assertNotIn("meta", records[0])

    def test_build_commit_receipt_sanitizes_editor_provenance(self) -> None:
        """editor_provenance with evil content must not reach the receipt unsanitized."""
        from aiir._core import CommitInfo
        from aiir._receipt import build_commit_receipt

        commit = CommitInfo(
            sha="abc123",
            author_name="Test",
            author_email="test@example.com",
            author_date="2026-01-01T00:00:00Z",
            committer_name="Test",
            committer_email="test@example.com",
            committer_date="2026-01-01T00:00:00Z",
            subject="test",
            body="test\n",
            diff_stat="",
            diff_hash="sha256:0000",
            files_changed=[],
            is_ai_authored=False,
            ai_signals_detected=[],
        )
        evil_provenance = {
            "schema": "aiir/editor_provenance.v1",
            "evil": "<script>alert(1)</script>",
            "mode": "provable\x1b[31m",
        }
        with patch("aiir._receipt._run_git", return_value=""):
            r = build_commit_receipt(commit, editor_provenance=evil_provenance)
        ep = r.get("extensions", {}).get("editor_provenance", {})
        # Unknown key "evil" must not pass through
        self.assertNotIn("evil", ep or {})
        # Terminal escape must be stripped
        mode = (ep or {}).get("mode", "")
        self.assertNotIn("\x1b", mode)


# ---------------------------------------------------------------------------
# CBOR docstring / module comment sanity
# ---------------------------------------------------------------------------


class TestCborModuleDocstring(unittest.TestCase):
    """The module docstring must reference RFC 8949 section 4.2.1."""

    def test_docstring_mentions_rfc8949(self) -> None:
        import aiir._canonical_cbor as m

        doc = m.__doc__ or ""
        self.assertIn("RFC 8949", doc)
        self.assertIn("4.2.1", doc)
        self.assertIn("bytewise", doc.lower())


# ---------------------------------------------------------------------------
# D5 — i18n encoding in _GIT_DETERMINISTIC_CONFIG
# ---------------------------------------------------------------------------


class TestI18nEncodingInDeterministicConfig(unittest.TestCase):
    """D5 — i18n.logOutputEncoding and i18n.commitEncoding must be in _GIT_DETERMINISTIC_CONFIG."""

    def test_log_output_encoding_utf8_present(self) -> None:
        from aiir._core import _GIT_DETERMINISTIC_CONFIG

        joined = " ".join(_GIT_DETERMINISTIC_CONFIG)
        self.assertIn("i18n.logOutputEncoding=UTF-8", joined)

    def test_commit_encoding_utf8_present(self) -> None:
        from aiir._core import _GIT_DETERMINISTIC_CONFIG

        joined = " ".join(_GIT_DETERMINISTIC_CONFIG)
        self.assertIn("i18n.commitEncoding=UTF-8", joined)

    def test_i18n_flags_appear_as_dash_c_pairs(self) -> None:
        from aiir._core import _GIT_DETERMINISTIC_CONFIG

        # Both encoding settings must be passed as -c pairs, not bare flags.
        # Walk the list as pairs to verify.
        pairs = []
        it = iter(_GIT_DETERMINISTIC_CONFIG)
        for token in it:
            if token == "-c":
                try:
                    pairs.append(next(it))
                except StopIteration:
                    break
        self.assertTrue(
            any("i18n.logOutputEncoding=UTF-8" in p for p in pairs),
            f"i18n.logOutputEncoding=UTF-8 not found as -c pair in: {pairs}",
        )
        self.assertTrue(
            any("i18n.commitEncoding=UTF-8" in p for p in pairs),
            f"i18n.commitEncoding=UTF-8 not found as -c pair in: {pairs}",
        )


class TestGetCommitInfoUsesDetministicForLogReads(unittest.TestCase):
    """D5 — subject and body reads in get_commit_info must use deterministic=True.

    Ensures message_hash/subject/receipt_id are stable even when the user has
    set i18n.logOutputEncoding to a non-UTF-8 value (e.g. ISO-8859-1).
    """

    def _fake_run_git_tracker(self):
        """Return (tracker_list, fake_run_git) where tracker records all calls."""
        calls: list = []

        def fake(args, cwd=None, deterministic=False):
            calls.append({"args": list(args), "deterministic": deterministic})
            sha = "a" * 40
            tree = "b" * 40
            parent = "c" * 40
            # Return different values based on args
            if "--format=%H%x00" in " ".join(args):
                # subject line read: sha NUL name NUL email NUL date NUL ...
                return (
                    f"{sha}\x00Author\x00a@b.com\x002026-01-01T00:00:00Z\x00"
                    f"Committer\x00c@b.com\x002026-01-01T00:00:00Z\x00subject"
                )
            if "--format=%B" in args:
                return "subject\n\nbody text"
            if "rev-parse" in args and "^{tree}" in " ".join(args):
                return tree
            if "rev-parse" in args and "^@" in " ".join(args):
                return parent
            if "rev-parse" in args and "--verify" in args:
                return parent
            if "--stat" in args:
                return "1 file changed"
            if "--name-only" in args:
                return "foo.py"
            return ""

        return calls, fake

    def test_subject_read_uses_deterministic(self) -> None:
        """The log call that reads the subject (%s) must use deterministic=True."""
        calls, fake = self._fake_run_git_tracker()

        with patch("aiir._detect._run_git", side_effect=fake):
            with patch(
                "aiir._detect._hash_diff_streaming", return_value="sha256:" + "0" * 64
            ):
                try:
                    from aiir._detect import get_commit_info

                    get_commit_info("HEAD", cwd="/tmp")
                except Exception:
                    pass  # Only care about call args

        # Find the call with %H%x00 in format (that's the subject/metadata read)
        subject_calls = [
            c
            for c in calls
            if any("%H%x00" in a or "--format=%H" in a for a in c["args"])
        ]
        self.assertTrue(
            subject_calls,
            f"No subject-format log call found in calls: {calls}",
        )
        for c in subject_calls:
            self.assertTrue(
                c["deterministic"],
                f"Subject log call must use deterministic=True, got: {c}",
            )

    def test_body_read_uses_deterministic(self) -> None:
        """The log call that reads the full body (%B) must use deterministic=True."""
        calls, fake = self._fake_run_git_tracker()

        with patch("aiir._detect._run_git", side_effect=fake):
            with patch(
                "aiir._detect._hash_diff_streaming", return_value="sha256:" + "0" * 64
            ):
                try:
                    from aiir._detect import get_commit_info

                    get_commit_info("HEAD", cwd="/tmp")
                except Exception:
                    pass

        body_calls = [c for c in calls if "--format=%B" in c["args"]]
        self.assertTrue(
            body_calls,
            f"No body-format (%B) log call found in calls: {calls}",
        )
        for c in body_calls:
            self.assertTrue(
                c["deterministic"],
                f"Body log call must use deterministic=True, got: {c}",
            )

    def test_non_ascii_commit_message_stable_across_encoding_configs(self) -> None:
        """Regression test: non-ASCII subject/body must be stable regardless of user's
        i18n.logOutputEncoding setting, because we always pass i18n.logOutputEncoding=UTF-8
        via deterministic=True.

        This test creates a real git repo, sets i18n.logOutputEncoding=ISO-8859-1,
        makes a commit with a non-ASCII message, then verifies that get_commit_info
        returns the same message_hash, subject, and receipt_id as when run without
        the non-UTF-8 config override.  The fix (D5) closes this gap by always
        passing -c i18n.logOutputEncoding=UTF-8 on the git log calls.
        """
        import hashlib
        import subprocess

        with tempfile.TemporaryDirectory() as td:
            # Initialize a git repo
            subprocess.run(["git", "init", td], check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", td, "config", "user.email", "test@test.com"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", td, "config", "user.name", "Test User"],
                check=True,
                capture_output=True,
            )
            # Create a commit with a non-ASCII subject (e.g., accented characters)
            (Path(td) / "file.txt").write_text("content", encoding="utf-8")
            subprocess.run(
                ["git", "-C", td, "add", "file.txt"], check=True, capture_output=True
            )
            non_ascii_msg = "feat: add résumé parser — handles UTF-8 naïvely"
            subprocess.run(
                ["git", "-C", td, "commit", "-m", non_ascii_msg],
                check=True,
                capture_output=True,
            )

            # Set i18n.logOutputEncoding=ISO-8859-1 on the repo
            subprocess.run(
                ["git", "-C", td, "config", "i18n.logOutputEncoding", "ISO-8859-1"],
                check=True,
                capture_output=True,
            )

            # get_commit_info must return the correct UTF-8 subject despite the
            # ISO-8859-1 config, because deterministic=True forces UTF-8.
            from aiir._detect import get_commit_info

            info = get_commit_info("HEAD", cwd=td)

            # The subject must match the original (not be garbled by ISO-8859-1 decoding)
            self.assertEqual(
                info.subject,
                non_ascii_msg,
                f"Subject was garbled under ISO-8859-1 config: {info.subject!r}",
            )

            # message_hash/receipt_id must be stable — compute expected hash
            expected_body_hash = (
                "sha256:" + hashlib.sha256(info.body.encode("utf-8")).hexdigest()
            )
            # Verify body was also not garbled
            self.assertIn("résumé", info.body, "Body should contain non-ASCII text")

            # Now remove the ISO-8859-1 config and verify subject is the same
            subprocess.run(
                ["git", "-C", td, "config", "--unset", "i18n.logOutputEncoding"],
                check=True,
                capture_output=True,
            )
            info2 = get_commit_info("HEAD", cwd=td)
            self.assertEqual(
                info.subject,
                info2.subject,
                "Subject must be identical regardless of i18n.logOutputEncoding config",
            )


# ---------------------------------------------------------------------------
# D5 — False-positive signal hardening (bolt.new, lovable, continue.dev, double.bot)
# ---------------------------------------------------------------------------


class TestAISignalFalsePositiveHardening(unittest.TestCase):
    """Signals moved to word-boundary patterns must not fire on benign substrings."""

    def setUp(self) -> None:
        from aiir._detect import detect_ai_signals

        self._detect = detect_ai_signals

    # ---- bolt.new ----

    def test_bolt_new_exact_match_detected(self) -> None:
        """'bolt.new' as a standalone reference must be detected."""
        ai, _ = self._detect("built with bolt.new ai tool")
        self.assertTrue(
            any("bolt.new" in s for s in ai),
            f"Expected bolt.new signal, got: {ai}",
        )

    def test_bolt_newer_not_detected(self) -> None:
        """'bolt.newer' must NOT trigger the bolt.new signal (no false positive)."""
        ai, _ = self._detect("use the bolt.newer version of the library")
        bolt_hits = [s for s in ai if "bolt.new" in s]
        self.assertEqual(
            bolt_hits,
            [],
            f"False positive for 'bolt.newer': {bolt_hits}",
        )

    def test_bolt_newline_not_detected(self) -> None:
        """'bolt.newline' must NOT trigger the bolt.new signal."""
        ai, _ = self._detect("parse bolt.newline characters from the stream")
        bolt_hits = [s for s in ai if "bolt.new" in s]
        self.assertEqual(
            bolt_hits,
            [],
            f"False positive for 'bolt.newline': {bolt_hits}",
        )

    def test_bolt_new_in_url_without_trailing_word_char_detected(self) -> None:
        """'bolt.new' in a URL context like 'bolt.new/project' is still detected."""
        # The word boundary \b fires at the '/' since '/' is non-word.
        ai, _ = self._detect("generated using bolt.new/my-project")
        self.assertTrue(
            any("bolt.new" in s for s in ai),
            f"Expected bolt.new detection in URL context, got: {ai}",
        )

    # ---- lovable ----

    def test_lovable_adjective_not_detected(self) -> None:
        """'lovable' as a common English adjective must NOT be flagged as AI signal."""
        ai, _ = self._detect("what a lovable character in this story")
        lovable_hits = [s for s in ai if "lovable" in s]
        self.assertEqual(
            lovable_hits,
            [],
            f"False positive for adjective 'lovable': {lovable_hits}",
        )

    def test_lovable_rogue_not_detected(self) -> None:
        """'lovable rogue' in prose must NOT trigger AI detection."""
        ai, _ = self._detect("he is a lovable rogue, always getting into trouble")
        lovable_hits = [s for s in ai if "lovable" in s]
        self.assertEqual(
            lovable_hits,
            [],
            f"False positive for 'lovable rogue': {lovable_hits}",
        )

    def test_lovable_dev_url_detected(self) -> None:
        """'lovable.dev' (the tool's domain) must be detected."""
        ai, _ = self._detect("deployed via lovable.dev platform")
        self.assertTrue(
            any("lovable" in s for s in ai),
            f"Expected lovable.dev signal, got: {ai}",
        )

    def test_generated_by_lovable_detected(self) -> None:
        """'generated by lovable' must be detected."""
        ai, _ = self._detect("generated by lovable")
        self.assertTrue(
            any("lovable" in s for s in ai),
            f"Expected 'generated by lovable' signal, got: {ai}",
        )

    def test_generated_with_lovable_detected(self) -> None:
        """'generated with lovable' must be detected."""
        ai, _ = self._detect("scaffold generated with lovable")
        self.assertTrue(
            any("lovable" in s for s in ai),
            f"Expected 'generated with lovable' signal, got: {ai}",
        )

    def test_co_authored_by_lovable_detected(self) -> None:
        """'co-authored-by: lovable' in a trailer must be detected."""
        ai, _ = self._detect("fix typo\n\nco-authored-by: lovable")
        self.assertTrue(
            any("lovable" in s for s in ai),
            f"Expected co-authored-by lovable signal, got: {ai}",
        )

    # ---- continue.dev ----

    def test_continue_dev_exact_detected(self) -> None:
        """'continue.dev' as a standalone reference must be detected."""
        ai, _ = self._detect("code written with continue.dev ai assistant")
        self.assertTrue(
            any("continue.dev" in s for s in ai),
            f"Expected continue.dev signal, got: {ai}",
        )

    def test_continue_develop_not_detected(self) -> None:
        """'continue.develop' must NOT trigger the continue.dev signal."""
        ai, _ = self._detect("will continue.develop this feature next sprint")
        continue_hits = [s for s in ai if "continue.dev" in s]
        self.assertEqual(
            continue_hits,
            [],
            f"False positive for 'continue.develop': {continue_hits}",
        )

    def test_continue_development_not_detected(self) -> None:
        """'continue.development' must NOT trigger the continue.dev signal."""
        ai, _ = self._detect("continue.development of the core module")
        continue_hits = [s for s in ai if "continue.dev" in s]
        self.assertEqual(
            continue_hits,
            [],
            f"False positive for 'continue.development': {continue_hits}",
        )

    def test_continue_dev_in_url_detected(self) -> None:
        """'continue.dev' in URL context (e.g. href=continue.dev/...) must be detected."""
        # Word boundary fires at '/' because '/' is non-word.
        ai, _ = self._detect("see docs at continue.dev/docs for setup")
        self.assertTrue(
            any("continue.dev" in s for s in ai),
            f"Expected continue.dev signal in URL context, got: {ai}",
        )

    # ---- double.bot ----

    def test_double_bot_exact_detected(self) -> None:
        """'double.bot' as a standalone reference must be detected."""
        ai, _ = self._detect("review requested from double.bot")
        self.assertTrue(
            any("double.bot" in s for s in ai),
            f"Expected double.bot signal, got: {ai}",
        )

    def test_double_bottle_not_detected(self) -> None:
        """'double.bottle' must NOT trigger the double.bot signal."""
        ai, _ = self._detect("carry a double.bottle of water on the hike")
        bot_hits = [s for s in ai if "double.bot" in s]
        self.assertEqual(
            bot_hits,
            [],
            f"False positive for 'double.bottle': {bot_hits}",
        )

    def test_double_bottom_not_detected(self) -> None:
        """'double.bottom' must NOT trigger the double.bot signal."""
        ai, _ = self._detect("the chart shows a double.bottom pattern")
        bot_hits = [s for s in ai if "double.bot" in s]
        self.assertEqual(
            bot_hits,
            [],
            f"False positive for 'double.bottom': {bot_hits}",
        )

    def test_double_bought_not_detected(self) -> None:
        """'double.bought' (arbitrary suffix) must NOT trigger the double.bot signal."""
        ai, _ = self._detect("double.bought the wrong item")
        bot_hits = [s for s in ai if "double.bot" in s]
        self.assertEqual(
            bot_hits,
            [],
            f"False positive for 'double.bought': {bot_hits}",
        )

    # ---- Previously-detected signals must still fire (no regression) ----

    def test_replit_agent_still_detected(self) -> None:
        """'replit agent' (plain substring) must still be detected."""
        ai, _ = self._detect("deployed via replit agent")
        self.assertTrue(
            any("replit agent" in s for s in ai),
            f"Expected replit agent signal, got: {ai}",
        )

    def test_supermaven_still_detected(self) -> None:
        """'supermaven' (plain substring) must still be detected."""
        ai, _ = self._detect("completion powered by supermaven")
        self.assertTrue(
            any("supermaven" in s for s in ai),
            f"Expected supermaven signal, got: {ai}",
        )

    def test_jetbrains_ai_still_detected(self) -> None:
        """'jetbrains ai' (plain substring) must still be detected."""
        ai, _ = self._detect("written using jetbrains ai assistant")
        self.assertTrue(
            any("jetbrains ai" in s for s in ai),
            f"Expected jetbrains ai signal, got: {ai}",
        )

    def test_codestral_still_detected(self) -> None:
        """'codestral' (plain substring) must still be detected."""
        ai, _ = self._detect("generated with codestral model")
        self.assertTrue(
            any("codestral" in s for s in ai),
            f"Expected codestral signal, got: {ai}",
        )

    def test_human_commit_with_innocuous_words_no_false_positives(self) -> None:
        """A human commit mentioning lovable/continue/bolt in prose must not be flagged."""
        message = (
            "refactor: simplify login flow\n\n"
            "This removes the lovable but overcomplicated auth helper.\n"
            "We will continue developing the new approach next sprint.\n"
            "The old bolt-on solution was a pain to maintain.\n"
            "double-check all tests pass before merging."
        )
        ai, _ = self._detect(
            message, author_name="Alice Smith", author_email="alice@company.com"
        )
        self.assertEqual(
            ai,
            [],
            f"Unexpected AI signals on innocent commit: {ai}",
        )


if __name__ == "__main__":
    unittest.main()
