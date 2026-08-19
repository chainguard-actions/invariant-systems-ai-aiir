# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""
Regression tests for the second audit hardening pass (audit-remediation-2).

Each test exercises a SECURITY-remediation branch added during the hardening
pass and asserts the real fail-closed / accept behaviour (the exploit path is
rejected, the canonical/valid case passes).  They do not merely call code for
coverage — every test asserts the security-relevant outcome.

Covered branches:
  * aiir/_agent_receipt.py D2 canonical-form field rejection
    (_field_is_canonical / _receipt_fields_are_canonical) — per-field paths.
  * aiir/_github.py        HTTPS-scheme / repo-shape guard re-raise in
    _find_existing_comment.
  * aiir/_ledger.py        alternative-shape branches in
    _is_structurally_valid_sigstore_bundle_dict.
  * aiir/_verify_release.py D3 bundle-binding branches
    (_is_structurally_valid_sigstore_bundle / _has_structural_sigstore_sidecar).
  * aiir/cli.py            --gl-sast-report symlink-after-mkdir TOCTOU re-check.
"""

from __future__ import annotations

import base64
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import aiir._github as gh
import aiir._ledger as ledger
import aiir._verify_release as vr
import aiir.cli as cli
from aiir._agent_receipt import build_agent_receipt, verify_agent_receipt

# Reuse integrity-valid receipt/ledger fixtures from the verify_release suite
# (importing helpers — not editing that test file).
from tests.test_verify_release import (  # noqa: E402
    _make_receipt as _vr_make_receipt,
    _pad_sha,
    _write_ledger as _vr_write_ledger,
)

# A value that is NOT in canonical form: it embeds an ANSI CSI escape sequence
# that _strip_terminal_escapes removes, so stripped(value) != value.
_NON_CANONICAL = "ok\x1b[31mEVIL"
# A value with an embedded C0 control byte (NUL) — also non-canonical.
_NON_CANONICAL_CTRL = "ok\x00EVIL"


# ===========================================================================
# aiir/_agent_receipt.py — D2 canonical-form field rejection (330-367)
# ===========================================================================


def _valid_full_receipt() -> Dict[str, Any]:
    """Build a fully-populated, valid agent receipt.

    All optional string fields (tool.surface, actor.session_ref, action.intent,
    artifact role, policy.reasons, policy.contract_ref) are present so each can
    be individually tampered to exercise its canonical-form branch.
    """
    return build_agent_receipt(
        actor_kind="ai_agent",
        actor_tool_name="claude-code",
        actor_tool_surface="cli",
        actor_session_ref="session-abc",
        action_kind="code_edit",
        action_intent="apply patch",
        action_summary="edited a file",
        artifact_inputs=[{"type": "file", "ref": "a.py", "role": "source"}],
        artifact_outputs=[{"type": "file", "ref": "b.py", "role": "result"}],
        policy_decision="allow",
        policy_reasons=["within scope", "signed"],
        policy_contract_ref="contract://v1",
        timestamp="2026-06-01T00:00:00Z",
    )


class TestAgentReceiptCanonicalFieldRejection(unittest.TestCase):
    """D2: a stored field that is not in normalized canonical form is rejected
    *before* the content hash is recomputed, defeating escape/control-byte
    collision forgery."""

    def test_fully_populated_receipt_is_valid_baseline(self):
        """The untampered, fully-populated receipt verifies valid."""
        receipt = _valid_full_receipt()
        result = verify_agent_receipt(receipt)
        self.assertTrue(result["valid"], result.get("errors"))

    def _assert_rejected_non_canonical(self, receipt: Dict[str, Any]) -> None:
        result = verify_agent_receipt(receipt)
        self.assertFalse(result["valid"])
        self.assertIn("canonical form", " ".join(result["errors"]))

    def test_actor_tool_surface_non_canonical_rejected(self):
        """330: actor.tool.surface with an embedded escape is rejected."""
        receipt = _valid_full_receipt()
        receipt["actor"]["tool"]["surface"] = _NON_CANONICAL
        self._assert_rejected_non_canonical(receipt)

    def test_actor_session_ref_non_canonical_rejected(self):
        """332: actor.session_ref with an embedded control byte is rejected."""
        receipt = _valid_full_receipt()
        receipt["actor"]["session_ref"] = _NON_CANONICAL_CTRL
        self._assert_rejected_non_canonical(receipt)

    def test_artifact_type_non_canonical_rejected(self):
        """351: artifacts.inputs[].type with an embedded escape is rejected."""
        receipt = _valid_full_receipt()
        receipt["artifacts"]["inputs"][0]["type"] = _NON_CANONICAL
        self._assert_rejected_non_canonical(receipt)

    def test_artifact_ref_non_canonical_rejected(self):
        """353: artifacts.outputs[].ref with an embedded escape is rejected."""
        receipt = _valid_full_receipt()
        receipt["artifacts"]["outputs"][0]["ref"] = _NON_CANONICAL
        self._assert_rejected_non_canonical(receipt)

    def test_artifact_role_non_canonical_rejected(self):
        """355: artifacts.inputs[].role with an embedded escape is rejected."""
        receipt = _valid_full_receipt()
        receipt["artifacts"]["inputs"][0]["role"] = _NON_CANONICAL
        self._assert_rejected_non_canonical(receipt)

    def test_policy_reason_non_canonical_rejected(self):
        """364: a policy.reasons[] entry with an embedded escape is rejected."""
        receipt = _valid_full_receipt()
        receipt["policy"]["reasons"][1] = _NON_CANONICAL
        self._assert_rejected_non_canonical(receipt)

    def test_policy_contract_ref_non_canonical_rejected(self):
        """367: policy.contract_ref with an embedded escape is rejected."""
        receipt = _valid_full_receipt()
        receipt["policy"]["contract_ref"] = _NON_CANONICAL
        self._assert_rejected_non_canonical(receipt)

    def test_value_exceeding_cap_with_trailing_bytes_rejected(self):
        """A stored value longer than its field cap (truncation collision) is
        rejected — the stored bytes carry payload past the cap that would be
        dropped before hashing."""
        receipt = _valid_full_receipt()
        # action.intent cap is 200; append payload beyond the cap.
        receipt["action"]["intent"] = "x" * 200 + "TRAILING-PAYLOAD"
        self._assert_rejected_non_canonical(receipt)

    def test_non_dict_artifact_entry_is_rejected(self):
        """349->348: a non-dict entry in an artifacts list is skipped by the
        canonical scan (loop-continue arc), then rejected downstream by
        normalization — the receipt is invalid either way."""
        receipt = _valid_full_receipt()
        # Insert a bare string where an artifact object is expected.
        receipt["artifacts"]["inputs"] = ["not-an-object"]
        result = verify_agent_receipt(receipt)
        self.assertFalse(result["valid"])


# ===========================================================================
# aiir/_github.py — HTTPS/scheme guard re-raise in _find_existing_comment (494)
# ===========================================================================


class TestFindExistingCommentSchemeGuard(unittest.TestCase):
    """The GET in _find_existing_comment must propagate RuntimeError (HTTPS /
    redirect / scheme guard) rather than swallowing it like a transient error."""

    def test_runtime_error_from_opener_is_propagated(self):
        """494: a RuntimeError raised inside the request (e.g. the no-redirect
        opener refusing a credentialed redirect) is re-raised, not swallowed."""

        def _boom(*_args, **_kwargs):
            raise RuntimeError("GitHub API request was redirected — refusing")

        with patch.dict(os.environ, {"GITHUB_TOKEN": "tok"}, clear=False):
            with patch.object(gh, "urlopen", _boom):
                with self.assertRaises(RuntimeError):
                    gh._find_existing_comment("owner/repo", "1", token="tok")

    def test_non_https_api_url_is_rejected(self):
        """The pre-request HTTPS guard rejects an http:// GITHUB_API_URL so the
        Authorization token is never sent in cleartext."""
        with patch.dict(
            os.environ,
            {"GITHUB_TOKEN": "tok", "GITHUB_API_URL": "http://insecure.example"},
            clear=False,
        ):
            with self.assertRaises(RuntimeError) as ctx:
                gh._find_existing_comment("owner/repo", "1", token="tok")
        self.assertIn("HTTPS", str(ctx.exception))

    def test_malformed_repo_shape_is_rejected(self):
        """A malformed repo (path traversal) is rejected before the URL is built."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "tok"}, clear=False):
            with self.assertRaises(RuntimeError) as ctx:
                gh._find_existing_comment("../../evil", "1", token="tok")
        self.assertIn("repo shape", str(ctx.exception))

    def test_non_runtime_error_is_swallowed(self):
        """A transient network error (non-RuntimeError) is swallowed and the
        function returns None so the caller creates a fresh comment."""

        def _net_fail(*_args, **_kwargs):
            raise OSError("connection reset")

        with patch.dict(os.environ, {"GITHUB_TOKEN": "tok"}, clear=False):
            with patch.object(gh, "urlopen", _net_fail):
                self.assertIsNone(
                    gh._find_existing_comment("owner/repo", "1", token="tok")
                )


# ===========================================================================
# aiir/_ledger.py — _is_structurally_valid_sigstore_bundle_dict (230, 236)
# ===========================================================================


def _ledger_bundle_base() -> Dict[str, Any]:
    return {
        "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
        "verificationMaterial": {"certificate": {"rawBytes": "dGVzdA=="}},
        "messageSignature": {"signature": "c2ln"},
    }


class TestLedgerSigstoreBundleShape(unittest.TestCase):
    """_is_structurally_valid_sigstore_bundle_dict must accept the documented
    alternative shapes and reject malformed material."""

    def test_valid_bundle_dict_accepted(self):
        self.assertTrue(
            ledger._is_structurally_valid_sigstore_bundle_dict(_ledger_bundle_base())
        )

    def test_verification_material_not_a_dict_rejected(self):
        """230: verificationMaterial that is not an object is rejected."""
        bundle = _ledger_bundle_base()
        bundle["verificationMaterial"] = "not-a-dict"
        self.assertFalse(ledger._is_structurally_valid_sigstore_bundle_dict(bundle))

    def test_no_certificate_and_no_chain_rejected(self):
        """236: material with neither certificate.rawBytes nor
        x509CertificateChain.certificates is rejected."""
        bundle = _ledger_bundle_base()
        bundle["verificationMaterial"] = {"somethingElse": True}
        self.assertFalse(ledger._is_structurally_valid_sigstore_bundle_dict(bundle))

    def test_x509_certificate_chain_shape_accepted(self):
        """The x509CertificateChain.certificates alternative shape is accepted."""
        bundle = _ledger_bundle_base()
        bundle["verificationMaterial"] = {
            "x509CertificateChain": {"certificates": [{"rawBytes": "dGVzdA=="}]}
        }
        self.assertTrue(ledger._is_structurally_valid_sigstore_bundle_dict(bundle))

    def test_dsse_envelope_shape_accepted(self):
        """The dsseEnvelope.signatures alternative shape is accepted (no
        messageSignature)."""
        bundle = _ledger_bundle_base()
        del bundle["messageSignature"]
        bundle["dsseEnvelope"] = {"signatures": [{"sig": "c2ln"}]}
        self.assertTrue(ledger._is_structurally_valid_sigstore_bundle_dict(bundle))

    def test_receipt_is_signed_via_structural_bundle(self):
        """_receipt_is_signed accepts a commit receipt carrying a structurally
        valid inline bundle, and rejects a trivially-forgeable truthy value."""
        signed = {
            "type": "aiir.commit_receipt",
            "extensions": {"sigstore_bundle": _ledger_bundle_base()},
        }
        self.assertTrue(ledger._receipt_is_signed(signed))
        forged = {
            "type": "aiir.commit_receipt",
            "extensions": {"sigstore_bundle": True},
        }
        self.assertFalse(ledger._receipt_is_signed(forged))


# ===========================================================================
# aiir/_verify_release.py — D3 bundle-binding branches (271-276, 332-333)
# ===========================================================================


def _write_bundle(path: Path, digest_b64: str) -> None:
    bundle = {
        "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
        "verificationMaterial": {"certificate": {"rawBytes": "dGVzdGNlcnQ="}},
        "messageSignature": {
            "messageDigest": {"algorithm": "SHA2_256", "digest": digest_b64},
            "signature": "dGVzdHNpZw==",
        },
    }
    path.write_text(json.dumps(bundle), encoding="utf-8")


class TestVerifyReleaseDigestBinding(unittest.TestCase):
    """D3: the messageSignature digest binding must reject undecodable digests
    and non-hex file hashes fail-closed."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aiir_d3_")

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_valid_digest_binding_accepted(self):
        """A bundle whose messageDigest matches the file SHA-256 is accepted."""
        sidecar = Path(self._tmp, "r.json.sigstore")
        file_sha = "ab" * 32  # 64-hex
        digest_b64 = base64.b64encode(bytes.fromhex(file_sha)).decode()
        _write_bundle(sidecar, digest_b64)
        self.assertTrue(
            vr._is_structurally_valid_sigstore_bundle(
                str(sidecar), receipt_file_sha256=file_sha
            )
        )

    def test_mismatching_digest_rejected(self):
        """A bundle digest that does not match the receipt file hash is rejected
        (recycled/forged-bundle replay defence)."""
        sidecar = Path(self._tmp, "r.json.sigstore")
        digest_b64 = base64.b64encode(bytes.fromhex("cd" * 32)).decode()
        _write_bundle(sidecar, digest_b64)
        self.assertFalse(
            vr._is_structurally_valid_sigstore_bundle(
                str(sidecar), receipt_file_sha256="ab" * 32
            )
        )

    def test_undecodable_base64_digest_rejected(self):
        """271-272: a messageDigest.digest that is not valid base64 is rejected
        (the decode raises and we fail closed)."""
        sidecar = Path(self._tmp, "r.json.sigstore")
        _write_bundle(sidecar, "a")  # length-1 string -> base64 padding error
        self.assertFalse(
            vr._is_structurally_valid_sigstore_bundle(
                str(sidecar), receipt_file_sha256="ab" * 32
            )
        )

    def test_non_hex_receipt_file_sha_rejected(self):
        """275-276: a non-hex receipt_file_sha256 makes bytes.fromhex raise and
        the binding fails closed."""
        sidecar = Path(self._tmp, "r.json.sigstore")
        digest_b64 = base64.b64encode(bytes.fromhex("ab" * 32)).decode()
        _write_bundle(sidecar, digest_b64)
        self.assertFalse(
            vr._is_structurally_valid_sigstore_bundle(
                str(sidecar), receipt_file_sha256="zz-not-hex"
            )
        )

    def test_no_digest_path_accepted(self):
        """When the bundle carries no messageDigest.digest, the binding check is
        skipped and structural validity alone decides (accepted)."""
        sidecar = Path(self._tmp, "r.json.sigstore")
        _write_bundle(sidecar, "")  # empty digest -> binding skipped
        self.assertTrue(
            vr._is_structurally_valid_sigstore_bundle(
                str(sidecar), receipt_file_sha256="ab" * 32
            )
        )


class TestHasStructuralSidecarOSError(unittest.TestCase):
    """332-333: when the receipt JSON file cannot be read, the file hash falls
    back to None (binding skipped) but a structurally valid sidecar still
    gates."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aiir_sidecar_")

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_unreadable_receipt_file_falls_back_to_none(self):
        """332-333: open(json_path, 'rb') raising OSError sets the file hash to
        None; with no digest the sidecar still gates True."""
        json_path = Path(self._tmp, "missing.json")  # deliberately not created
        sidecar = Path(str(json_path) + ".sigstore")
        _write_bundle(sidecar, "")  # no digest -> binding skipped

        receipt: Dict[str, Any] = {"content_hash": "sha256:" + "a" * 64}
        artifact_index = {
            "sha256:" + "a" * 64: {"json_path": str(json_path)},
        }

        with patch(
            "aiir._evidence._artifact_key_candidates",
            return_value=["sha256:" + "a" * 64],
        ):
            self.assertTrue(
                vr._has_structural_sigstore_sidecar(receipt, artifact_index)
            )


# ===========================================================================
# aiir/_verify_release.py — commit-sha scope filter (743)
# ===========================================================================


class TestVerifyReleaseScopeFilter(unittest.TestCase):
    """743: when a commit range supplies an explicit scope, a commit receipt
    whose SHA is not in scope is excluded from the ledger-aggregate policy
    counts (so an out-of-scope AI receipt cannot trip max_ai_percent, and an
    out-of-scope receipt cannot dilute the AI percentage)."""

    @patch("aiir._verify_release.list_commits_in_range")
    @patch("aiir._verify_release._validate_ref")
    def test_out_of_scope_commit_receipt_excluded(self, _mock_validate, mock_list):
        in_scope_sha = "aa11"
        out_scope_sha = "bb22"
        # The range contains ONLY the in-scope sha.
        mock_list.return_value = [_pad_sha(in_scope_sha)]
        with tempfile.TemporaryDirectory() as td:
            # In-scope receipt is human-authored; the out-of-scope receipt is
            # AI-authored.  If the scope filter (line 743) works, the AI receipt
            # is excluded → ai% == 0 → max_ai_percent=0 PASSES.  If it leaked
            # in, ai% would be 50 and the hard-fail policy would FAIL.
            receipts = [
                _vr_make_receipt(sha=in_scope_sha, ai=False),
                _vr_make_receipt(sha=out_scope_sha, ai=True),
            ]
            ledger_path = _vr_write_ledger(Path(td), receipts)
            result = vr.verify_release(
                commit_range="origin/main..HEAD",
                receipts_path=ledger_path,
                policy_overrides={
                    "max_ai_percent": 0,
                    "enforcement": "hard-fail",
                    "require_signing": False,
                },
                policy_preset="permissive",
            )
        # The out-of-scope AI receipt was filtered out of the aggregate, so the
        # max_ai_percent=0 gate is satisfied and verification PASSES.
        self.assertEqual(result["verificationResult"], "PASSED", result.get("reason"))


# ===========================================================================
# aiir/cli.py — --gl-sast-report symlink-after-mkdir TOCTOU (3383-3387)
# ===========================================================================


class TestSastReportSymlinkTOCTOU(unittest.TestCase):
    """3383-3387: after the target's parent directory is created, the target
    path is re-checked for being a symlink (narrow TOCTOU window).  If a
    symlink appeared, the write is refused."""

    def test_symlink_appearing_after_mkdir_is_rejected(self):
        """The path passes all pre-checks (in-cwd, no traversal, not a symlink),
        but becomes a symlink right after mkdir — the re-check rejects it."""
        import subprocess

        original_cwd = os.getcwd()
        tmpdir = tempfile.mkdtemp(prefix="aiir_sast_toctou_")
        try:
            # The CLI requires a git repo cwd before it reaches the SAST logic.
            subprocess.run(["git", "init", tmpdir], capture_output=True, check=True)
            subprocess.run(
                ["git", "-C", tmpdir, "config", "user.email", "t@t.com"],
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "-C", tmpdir, "config", "user.name", "T"],
                capture_output=True,
                check=True,
            )
            Path(tmpdir, "README.md").write_text("hi\n")
            subprocess.run(
                ["git", "-C", tmpdir, "add", "."], capture_output=True, check=True
            )
            subprocess.run(
                ["git", "-C", tmpdir, "commit", "-m", "init"],
                capture_output=True,
                check=True,
            )
            os.chdir(tmpdir)
            sast_path = "report.json"
            receipt = {
                "type": "aiir.commit_receipt",
                "commit": {"sha": "a" * 40},
                "ai_attestation": {"is_ai_authored": True},
            }
            captured_err = io.StringIO()

            real_is_symlink = Path.is_symlink
            state = {"after_mkdir": False}

            def _fake_is_symlink(self: Path) -> bool:
                # Only the resolved target reports as a symlink, and only after
                # the directory-creation step has run.
                if state["after_mkdir"] and self.name == "report.json":
                    return True
                return False

            real_mkdir = Path.mkdir

            def _fake_mkdir(self: Path, *a: Any, **k: Any):
                state["after_mkdir"] = True
                return real_mkdir(self, *a, **k)

            with (
                patch("aiir.cli.generate_receipt", return_value=receipt),
                patch(
                    "aiir.cli.append_to_ledger",
                    return_value=(1, 0, "/tmp/r.jsonl"),
                ),
                patch("aiir.cli.write_receipt", return_value="stdout:json"),
                patch("aiir.cli.set_gitlab_ci_output"),
                patch(
                    "aiir.cli.format_gl_sast_report",
                    return_value={"version": "15.0.0", "vulnerabilities": []},
                ),
                patch.object(Path, "is_symlink", _fake_is_symlink),
                patch.object(Path, "mkdir", _fake_mkdir),
                patch("sys.stderr", captured_err),
                patch("sys.stdout", io.StringIO()),
                patch.dict(os.environ, {"CI_COMMIT_SHA": "a" * 40}, clear=False),
            ):
                code = cli.main(["--gitlab-ci", "--gl-sast-report", sast_path])

            self.assertEqual(code, 1)
            self.assertIn("symlink", captured_err.getvalue().lower())
            # The report must NOT have been written.
            self.assertFalse(Path(tmpdir, "report.json").exists())
            _ = real_is_symlink  # silence unused in some interpreters
        finally:
            os.chdir(original_cwd)
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
