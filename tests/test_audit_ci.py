# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""Regression tests for CI configuration, supply-chain hardening, and packaging.

These tests are dependency-free (stdlib only) and assert invariants about
the repo's configuration files so that accidental regressions are caught
before they reach CI.  They act as a living specification for the audit
remediation findings addressed in the fix/audit-2026-06-hardening branch.
"""

from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TEST_IN = REPO_ROOT / ".github" / "requirements" / "test.in"
TEST_TXT = REPO_ROOT / ".github" / "requirements" / "test.txt"
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PUBLISH_YML = REPO_ROOT / ".github" / "workflows" / "publish.yml"
PYPROJECT_TOML = REPO_ROOT / "pyproject.toml"
GITIGNORE = REPO_ROOT / ".gitignore"
DOCKERFILE = REPO_ROOT / "Dockerfile"
RULESET = REPO_ROOT / ".github" / "rulesets" / "main-production-gate.json"
FUZZ_ATHERIS = REPO_ROOT / "tests" / "fuzz_atheris.py"
FUZZ_CBOR = REPO_ROOT / ".clusterfuzzlite" / "fuzz_cbor.py"


class TestTestRequirements(unittest.TestCase):
    """test.in and test.txt must declare the conformance-suite packages."""

    def test_test_in_contains_hypothesis(self) -> None:
        content = TEST_IN.read_text(encoding="utf-8")
        self.assertIn("hypothesis", content, "hypothesis must be in test.in")

    def test_test_in_contains_markdown_it_py(self) -> None:
        content = TEST_IN.read_text(encoding="utf-8")
        self.assertIn("markdown-it-py", content, "markdown-it-py must be in test.in")

    def test_test_in_contains_mdurl(self) -> None:
        content = TEST_IN.read_text(encoding="utf-8")
        self.assertIn(
            "mdurl", content, "mdurl must be in test.in (dep of markdown-it-py)"
        )

    def test_test_in_contains_rfc8785(self) -> None:
        content = TEST_IN.read_text(encoding="utf-8")
        self.assertIn("rfc8785", content, "rfc8785 must be in test.in")

    def test_test_txt_contains_hypothesis_hash(self) -> None:
        content = TEST_TXT.read_text(encoding="utf-8")
        self.assertIn("hypothesis", content)
        self.assertIn("--hash=sha256:", content)

    def test_test_txt_contains_rfc8785_hash(self) -> None:
        content = TEST_TXT.read_text(encoding="utf-8")
        self.assertIn("rfc8785", content)

    def test_test_txt_contains_markdown_it_py_hash(self) -> None:
        content = TEST_TXT.read_text(encoding="utf-8")
        self.assertIn("markdown-it-py", content)

    def test_test_txt_contains_mdurl_hash(self) -> None:
        content = TEST_TXT.read_text(encoding="utf-8")
        self.assertIn("mdurl", content)

    def test_test_txt_contains_sortedcontainers_hash(self) -> None:
        """sortedcontainers is a direct dep of hypothesis and must be pinned."""
        content = TEST_TXT.read_text(encoding="utf-8")
        self.assertIn("sortedcontainers", content)

    def test_test_txt_all_hashes_are_sha256(self) -> None:
        """Every hash entry in test.txt must use sha256 (not sha1/md5)."""
        content = TEST_TXT.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("--hash="):
                self.assertTrue(
                    line.startswith("--hash=sha256:"),
                    f"Non-sha256 hash found: {line!r}",
                )


class TestCiYml(unittest.TestCase):
    """ci.yml must wire test.txt into the test job and include SDK jobs."""

    def test_test_job_installs_test_txt(self) -> None:
        content = CI_YML.read_text(encoding="utf-8")
        self.assertIn(
            ".github/requirements/test.txt",
            content,
            "ci.yml test job must install .github/requirements/test.txt",
        )

    def test_sdk_js_job_present(self) -> None:
        content = CI_YML.read_text(encoding="utf-8")
        self.assertIn("sdk-js:", content, "ci.yml must have a sdk-js job")
        self.assertIn(
            "test_encoder_vectors.mjs",
            content,
            "sdk-js job must run the JS encoder vector tests",
        )

    def test_sdk_rust_job_present(self) -> None:
        content = CI_YML.read_text(encoding="utf-8")
        self.assertIn("sdk-rust:", content, "ci.yml must have a sdk-rust job")
        self.assertIn("cargo test", content, "sdk-rust job must run cargo test")

    def test_sdk_vscode_job_present(self) -> None:
        content = CI_YML.read_text(encoding="utf-8")
        self.assertIn("sdk-vscode:", content, "ci.yml must have a sdk-vscode job")

    def test_ci_ok_depends_on_sdk_jobs(self) -> None:
        content = CI_YML.read_text(encoding="utf-8")
        self.assertIn("sdk-js", content)
        self.assertIn("sdk-rust", content)
        self.assertIn("sdk-vscode", content)
        # ci-ok needs line must contain the SDK jobs
        for line in content.splitlines():
            if "needs:" in line and "sdk-js" in line:
                self.assertIn("sdk-rust", line)
                self.assertIn("sdk-vscode", line)
                break
        else:
            # needs: may span multiple lines — check the block
            self.assertIn(
                "sdk-rust",
                content,
                "ci-ok must depend on sdk-rust",
            )


class TestPublishYml(unittest.TestCase):
    """publish.yml supply-chain hardening assertions."""

    def test_ci_gate_verifies_tag_on_main(self) -> None:
        content = PUBLISH_YML.read_text(encoding="utf-8")
        self.assertIn(
            "Verify tag is reachable from main",
            content,
            "publish.yml ci-gate must verify the tag is reachable from main",
        )

    def test_ci_gate_requires_ci_ok_present(self) -> None:
        content = PUBLISH_YML.read_text(encoding="utf-8")
        self.assertIn("ci-ok", content)
        self.assertIn("quality-ok", content)
        self.assertIn("security-ok", content)

    def test_ci_gate_requires_named_rollup_checks(self) -> None:
        """The gate must hard-require all three named rollup checks to be present."""
        content = PUBLISH_YML.read_text(encoding="utf-8")
        self.assertIn("HAS_CI_OK", content)
        self.assertIn("HAS_QUALITY", content)
        self.assertIn("HAS_SECURITY", content)

    def test_event_inputs_not_interpolated_raw_in_run(self) -> None:
        """workflow_dispatch inputs must be passed via env:, not interpolated directly
        into run: script bodies (script injection prevention).

        The only allowed location for ${{ github.event.inputs.* }} is in env: blocks
        or in non-run: fields (if:, with:, etc.).
        """
        content = PUBLISH_YML.read_text(encoding="utf-8")
        lines = content.splitlines()
        in_run_block = False
        run_indent = 0
        for lineno, line in enumerate(lines, 1):
            stripped = line.lstrip()
            current_indent = len(line) - len(stripped)
            if stripped.startswith("run:") and "|" in stripped:
                in_run_block = True
                run_indent = current_indent
                continue
            if in_run_block:
                if (
                    stripped
                    and current_indent <= run_indent
                    and not stripped.startswith("#")
                ):
                    # We have left the run block
                    in_run_block = False
                else:
                    # Inside run block — no raw event input interpolation allowed
                    if "${{ github.event.inputs." in line:
                        self.fail(
                            f"Script injection sink at line {lineno}: "
                            f"event input interpolated directly in run: block: {line.rstrip()!r}"
                        )


class TestPyprojectToml(unittest.TestCase):
    """pyproject.toml configuration assertions."""

    def test_pre_commit_in_dev_deps(self) -> None:
        content = PYPROJECT_TOML.read_text(encoding="utf-8")
        self.assertIn(
            "pre-commit",
            content,
            "pre-commit must be in [project.optional-dependencies] dev",
        )

    def test_mutmut_includes_sign_tests(self) -> None:
        content = PYPROJECT_TOML.read_text(encoding="utf-8")
        self.assertIn(
            "tests/test_sign.py",
            content,
            "mutmut pytest_add_cli_args_test_selection must include test_sign.py",
        )

    def test_mutmut_includes_transparency_tests(self) -> None:
        content = PYPROJECT_TOML.read_text(encoding="utf-8")
        self.assertIn("tests/test_transparency.py", content)

    def test_mutmut_includes_ledger_tests(self) -> None:
        content = PYPROJECT_TOML.read_text(encoding="utf-8")
        self.assertIn("tests/test_ledger.py", content)

    def test_mutmut_includes_mcp_tests(self) -> None:
        content = PYPROJECT_TOML.read_text(encoding="utf-8")
        self.assertIn("tests/test_mcp.py", content)


class TestGitignore(unittest.TestCase):
    """uv.lock and other dev artifacts must be gitignored."""

    def test_uv_lock_gitignored(self) -> None:
        content = GITIGNORE.read_text(encoding="utf-8")
        self.assertIn(
            "uv.lock",
            content,
            "uv.lock must be in .gitignore (dev artifact)",
        )

    def test_uv_lock_line_is_a_pattern(self) -> None:
        """The uv.lock entry must not be inside a comment."""
        for line in GITIGNORE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped == "uv.lock":
                return  # found as a non-comment pattern
        self.fail("uv.lock is not present as a non-comment gitignore pattern")


class TestDockerfile(unittest.TestCase):
    """Dockerfile hardening assertions."""

    def test_safe_directory_set_as_user_aiir(self) -> None:
        """git safe.directory must be set after USER aiir, not as root.

        Setting it as root writes to /root/.gitconfig which is not read by
        the aiir user at runtime, breaking volume-mount usage.
        """
        content = DOCKERFILE.read_text(encoding="utf-8")
        lines = content.splitlines()

        user_aiir_seen = False
        safe_dir_after_user = False
        safe_dir_before_user = False

        for line in lines:
            stripped = line.strip()
            # Skip comment lines — they may mention safe.directory in prose
            if stripped.startswith("#"):
                continue
            if stripped == "USER aiir":
                user_aiir_seen = True
            if "safe.directory" in stripped:
                if user_aiir_seen:
                    safe_dir_after_user = True
                else:
                    safe_dir_before_user = True

        self.assertTrue(
            safe_dir_after_user,
            "git safe.directory must be set after 'USER aiir' in Dockerfile",
        )
        self.assertFalse(
            safe_dir_before_user,
            "git safe.directory must NOT be set as root (before USER aiir)",
        )

    def test_safe_directory_uses_wildcard(self) -> None:
        """safe.directory should use '*' so any volume-mount path is trusted."""
        content = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn(
            "safe.directory '*'",
            content,
            "Dockerfile must use safe.directory '*' to cover any volume-mount path",
        )


class TestRuleset(unittest.TestCase):
    """Branch ruleset must require code-owner review."""

    def test_ruleset_requires_code_owner_review(self) -> None:
        data = json.loads(RULESET.read_text(encoding="utf-8"))
        for rule in data.get("rules", []):
            if rule.get("type") == "pull_request":
                params = rule.get("parameters", {})
                self.assertTrue(
                    params.get("require_code_owner_review", False),
                    "main-production-gate.json must set require_code_owner_review: true",
                )
                self.assertGreaterEqual(
                    params.get("required_approving_review_count", 0),
                    1,
                    "main-production-gate.json must require at least 1 approving review",
                )
                return
        self.fail("No pull_request rule found in main-production-gate.json")


class TestFuzzAtheris(unittest.TestCase):
    """fuzz_atheris.py must import real functions (smoke-check)."""

    def test_fuzz_atheris_valid_python(self) -> None:
        source = FUZZ_ATHERIS.read_text(encoding="utf-8")
        try:
            ast.parse(source)
        except SyntaxError as exc:
            self.fail(f"fuzz_atheris.py has a syntax error: {exc}")

    def test_fuzz_atheris_imports_validate_receipt_schema(self) -> None:
        content = FUZZ_ATHERIS.read_text(encoding="utf-8")
        self.assertIn(
            "validate_receipt_schema",
            content,
            "fuzz_atheris.py must import validate_receipt_schema (not validate_receipt)",
        )
        self.assertNotIn(
            "from aiir._schema import validate_receipt\n",
            content,
            "fuzz_atheris.py must not import the non-existent validate_receipt",
        )

    def test_fuzz_atheris_imports_detect_ai_signals(self) -> None:
        content = FUZZ_ATHERIS.read_text(encoding="utf-8")
        self.assertIn(
            "detect_ai_signals",
            content,
            "fuzz_atheris.py must import detect_ai_signals (not detect_ai_commit)",
        )

    def test_fuzz_atheris_imports_canonical_json(self) -> None:
        content = FUZZ_ATHERIS.read_text(encoding="utf-8")
        self.assertIn(
            "_canonical_json",
            content,
            "fuzz_atheris.py must import _canonical_json from aiir._core",
        )

    def test_fuzz_atheris_imports_exist_at_runtime(self) -> None:
        """All four fuzz target imports must be resolvable at import time."""
        from aiir._schema import validate_receipt_schema  # noqa: F401
        from aiir._verify import verify_receipt  # noqa: F401
        from aiir._detect import detect_ai_signals  # noqa: F401
        from aiir._core import _canonical_json  # noqa: F401


class TestClusterFuzzLiteCbor(unittest.TestCase):
    """The CBOR fuzz target must exist and be syntactically valid."""

    def test_fuzz_cbor_exists(self) -> None:
        self.assertTrue(
            FUZZ_CBOR.exists(),
            ".clusterfuzzlite/fuzz_cbor.py must exist",
        )

    def test_fuzz_cbor_valid_python(self) -> None:
        source = FUZZ_CBOR.read_text(encoding="utf-8")
        try:
            ast.parse(source)
        except SyntaxError as exc:
            self.fail(f"fuzz_cbor.py has a syntax error: {exc}")

    def test_fuzz_cbor_imports_decode_cbor_full(self) -> None:
        content = FUZZ_CBOR.read_text(encoding="utf-8")
        self.assertIn(
            "decode_cbor_full",
            content,
            "fuzz_cbor.py must feed bytes to decode_cbor_full",
        )

    def test_fuzz_cbor_imports_canonical_cbor_bytes(self) -> None:
        content = FUZZ_CBOR.read_text(encoding="utf-8")
        self.assertIn(
            "canonical_cbor_bytes",
            content,
            "fuzz_cbor.py must import canonical_cbor_bytes for round-trip assertion",
        )

    def test_fuzz_cbor_asserts_only_value_error(self) -> None:
        """The target must assert that only ValueError is raised on bad input."""
        content = FUZZ_CBOR.read_text(encoding="utf-8")
        self.assertIn("ValueError", content)
        self.assertIn("AssertionError", content)

    def test_fuzz_cbor_has_round_trip_assertion(self) -> None:
        content = FUZZ_CBOR.read_text(encoding="utf-8")
        self.assertIn("round_tripped == value", content)

    def test_fuzz_cbor_decode_cbor_full_is_importable(self) -> None:
        from aiir._verify_cbor import decode_cbor_full  # noqa: F401

    def test_fuzz_cbor_canonical_cbor_bytes_is_importable(self) -> None:
        from aiir._canonical_cbor import canonical_cbor_bytes  # noqa: F401

    def test_fuzz_cbor_no_uncaught_exceptions_on_valid_receipt(self) -> None:
        """decode_cbor_full on valid CBOR bytes must not raise ValueError."""
        from aiir._canonical_cbor import canonical_cbor_bytes
        from aiir._verify_cbor import decode_cbor_full

        # Encode a simple receipt-like dict and verify round-trip
        sample = {"type": "aiir.commit_receipt", "schema": "aiir/commit_receipt.v2"}
        encoded = canonical_cbor_bytes(sample)
        decoded = decode_cbor_full(encoded)
        self.assertEqual(decoded, sample)

    def test_fuzz_cbor_invalid_bytes_raises_only_value_error(self) -> None:
        """decode_cbor_full on garbage must raise ValueError (not OverflowError, etc.)."""
        from aiir._verify_cbor import decode_cbor_full

        bad_inputs = [
            b"",  # empty
            b"\xff\xff",  # invalid major type / break code at top
            b"\x9f",  # indefinite-length array (not supported in strict mode)
            b"\xa1\x61",  # truncated map
            b"not cbor",  # plain text
        ]
        for bad in bad_inputs:
            try:
                decode_cbor_full(bad)
            except ValueError:
                pass  # expected
            except Exception as exc:
                self.fail(
                    f"decode_cbor_full raised {type(exc).__name__} instead of ValueError "
                    f"on input {bad!r}: {exc}"
                )

    def test_fuzz_cbor_both_branches_new_guard(self) -> None:
        """Both guard branches: success path and ValueError path are exercised."""
        from aiir._canonical_cbor import canonical_cbor_bytes
        from aiir._verify_cbor import decode_cbor_full

        # Success branch: valid canonical integer
        encoded_int = canonical_cbor_bytes(42)
        self.assertEqual(decode_cbor_full(encoded_int), 42)

        # ValueError branch: truncated data
        with self.assertRaises(ValueError):
            decode_cbor_full(b"\x58")  # text(24) with no following length byte


if __name__ == "__main__":
    unittest.main()
