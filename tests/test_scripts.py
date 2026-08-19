"""Unit tests for scripts/ — check_licenses.py, conformance.py, sync-version.py.

Copyright 2025-2026 Invariant Systems, Inc.
# SPDX-License-Identifier: Apache-2.0

These scripts are part of the CI pipeline but previously had zero test coverage.
This file validates their core logic without requiring external dependencies.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"


def _load_module(name: str, path: Path):
    """Import a script module by path (they don't live in a package)."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ═══════════════════════════════════════════════════════════════════════
# check_licenses.py
# ═══════════════════════════════════════════════════════════════════════


class TestCheckLicenses(unittest.TestCase):
    """Tests for scripts/check_licenses.py logic."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("check_licenses", SCRIPTS_DIR / "check_licenses.py")

    def test_approved_terms_present(self):
        """APPROVED_TERMS list contains core open-source license families."""
        terms = self.mod.APPROVED_TERMS
        self.assertIn("Apache", terms)
        self.assertIn("MIT", terms)
        self.assertIn("BSD", terms)

    def test_skip_packages_includes_aiir(self):
        """aiir itself should be skipped (not on PyPI during dev)."""
        self.assertIn("aiir", self.mod.SKIP_PACKAGES)

    def test_all_approved(self):
        """All packages approved → exit 0."""
        pkgs = [
            {"Name": "pytest", "Version": "8.0.0", "License": "MIT License"},
            {
                "Name": "hypothesis",
                "Version": "6.0",
                "License": "Mozilla Public License 2.0",
            },
        ]
        tf = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tf_name = tf.name
        json.dump(pkgs, tf)
        tf.close()  # close before test reads — required on Windows
        try:
            with mock.patch("sys.argv", ["check_licenses.py", tf_name]):
                result = self.mod.main()
            self.assertEqual(result, 0)
        finally:
            os.unlink(tf_name)

    def test_unapproved_license(self):
        """Package with unapproved license → exit 1."""
        pkgs = [
            {"Name": "evil-lib", "Version": "1.0", "License": "Proprietary"},
        ]
        tf = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tf_name = tf.name
        json.dump(pkgs, tf)
        tf.close()
        try:
            with mock.patch("sys.argv", ["check_licenses.py", tf_name]):
                result = self.mod.main()
            self.assertEqual(result, 1)
        finally:
            os.unlink(tf_name)

    def test_skipped_package_ignored(self):
        """Packages in SKIP_PACKAGES are not checked."""
        pkgs = [
            {"Name": "aiir", "Version": "1.0", "License": "UNKNOWN"},
        ]
        tf = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tf_name = tf.name
        json.dump(pkgs, tf)
        tf.close()
        try:
            with mock.patch("sys.argv", ["check_licenses.py", tf_name]):
                result = self.mod.main()
            self.assertEqual(result, 0)
        finally:
            os.unlink(tf_name)

    def test_no_args(self):
        """Missing CLI argument → exit 2."""
        with mock.patch("sys.argv", ["check_licenses.py"]):
            result = self.mod.main()
        self.assertEqual(result, 2)


# ═══════════════════════════════════════════════════════════════════════
# conformance.py
# ═══════════════════════════════════════════════════════════════════════


class TestConformance(unittest.TestCase):
    """Tests for scripts/conformance.py logic."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("conformance", SCRIPTS_DIR / "conformance.py")

    def test_canonical_json_sorted_keys(self):
        """Canonical JSON sorts keys."""
        result = self.mod.canonical_json({"b": 2, "a": 1})
        self.assertEqual(result, '{"a":1,"b":2}')

    def test_canonical_json_no_whitespace(self):
        """Canonical JSON has no extraneous whitespace."""
        result = self.mod.canonical_json({"key": "value"})
        self.assertNotIn(" ", result.replace('"key"', "").replace('"value"', ""))

    def test_canonical_json_ascii_escape(self):
        """Non-ASCII characters are \\uXXXX-escaped."""
        result = self.mod.canonical_json({"emoji": "🎉"})
        self.assertIn("\\u", result)
        self.assertNotIn("🎉", result)

    def test_canonical_json_depth_limit(self):
        """Exceeding depth 64 raises ValueError."""
        # Build a 65-deep nested dict
        obj = {"a": "leaf"}
        for _ in range(65):
            obj = {"nested": obj}
        with self.assertRaises(ValueError):
            self.mod.canonical_json(obj)

    def test_canonical_json_null(self):
        self.assertEqual(self.mod.canonical_json(None), "null")

    def test_canonical_json_bool(self):
        self.assertEqual(self.mod.canonical_json(True), "true")
        self.assertEqual(self.mod.canonical_json(False), "false")

    def test_canonical_json_list(self):
        self.assertEqual(self.mod.canonical_json([1, 2, 3]), "[1,2,3]")

    def test_canonical_json_nan_rejected(self):
        with self.assertRaises(ValueError):
            self.mod.canonical_json(float("nan"))

    def test_canonical_json_unsupported_type(self):
        with self.assertRaises(TypeError):
            self.mod.canonical_json(set())

    def test_verify_valid_receipt(self):
        """A properly constructed receipt passes verification."""
        import hashlib

        core = {
            "type": "aiir.commit_receipt",
            "schema": "aiir/commit_receipt.v1",
            "version": "1.0.0",
            "commit": {"sha": "a" * 40, "subject": "test"},
            "ai_attestation": {},
            "provenance": {},
        }
        core_json = self.mod.canonical_json(core)
        digest = hashlib.sha256(core_json.encode()).hexdigest()
        receipt = {
            **core,
            "content_hash": f"sha256:{digest}",
            "receipt_id": f"g1-{digest[:32]}",
        }
        valid, errors = self.mod.verify(receipt)
        self.assertTrue(valid, f"Expected valid, got errors: {errors}")

    def test_verify_tampered_receipt(self):
        """A tampered receipt fails verification."""
        receipt = {
            "type": "aiir.commit_receipt",
            "schema": "aiir/commit_receipt.v1",
            "version": "1.0.0",
            "commit": {"sha": "a" * 40, "subject": "test"},
            "ai_attestation": {},
            "provenance": {},
            "content_hash": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
            "receipt_id": "g1-00000000000000000000000000000000",
        }
        valid, errors = self.mod.verify(receipt)
        self.assertFalse(valid)
        self.assertTrue(len(errors) > 0)

    def test_verify_not_dict(self):
        valid, errors = self.mod.verify("not a dict")
        self.assertFalse(valid)

    def test_verify_wrong_type(self):
        valid, errors = self.mod.verify({"type": "wrong"})
        self.assertFalse(valid)

    def test_verify_bad_schema(self):
        valid, errors = self.mod.verify(
            {
                "type": "aiir.commit_receipt",
                "schema": "bad",
            }
        )
        self.assertFalse(valid)

    def test_verify_bad_version(self):
        valid, errors = self.mod.verify(
            {
                "type": "aiir.commit_receipt",
                "schema": "aiir/commit_receipt.v1",
                "version": "not-a-version",
            }
        )
        self.assertFalse(valid)

    def test_run_vectors_with_bundled_vectors(self):
        """run_vectors succeeds on the bundled test_vectors.json."""
        vectors_path = SCHEMAS_DIR / "test_vectors.json"
        if not vectors_path.exists():
            self.skipTest("test_vectors.json not found")
        passed, total, failures = self.mod.run_vectors(vectors_path)
        self.assertEqual(len(failures), 0, f"Failures: {failures}")
        self.assertGreater(total, 0)

    def test_main_with_bundled_vectors(self):
        """main() succeeds when run from repo root."""
        with mock.patch("sys.argv", ["conformance.py"]):
            result = self.mod.main()
        self.assertEqual(result, 0)

    def test_main_missing_vectors(self):
        """main() fails gracefully when vectors file not found."""
        with mock.patch("sys.argv", ["conformance.py", "/nonexistent/vectors.json"]):
            # Should fail to open the file
            with self.assertRaises((FileNotFoundError, SystemExit)):
                self.mod.main()


# ═══════════════════════════════════════════════════════════════════════
# sync-version.py
# ═══════════════════════════════════════════════════════════════════════


class TestSyncVersion(unittest.TestCase):
    """Tests for scripts/sync-version.py logic."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("sync_version", SCRIPTS_DIR / "sync-version.py")

    def test_get_version_reads_init(self):
        """get_version() reads from aiir/__init__.py."""
        version = self.mod.get_version()
        # Should be a valid semver-ish string
        parts = version.split(".")
        self.assertEqual(len(parts), 3)
        for p in parts:
            self.assertTrue(p.isdigit(), f"Non-numeric version part: {p}")

    def test_extension_manifest_uses_independent_version_lane(self):
        """The VS Code extension manifest is not synced to aiir/__init__.py."""
        synced_paths = {rule.path for rule in self.mod.AIIR_RULES}
        self.assertNotIn("extensions/vscode/package.json", synced_paths)

    def test_check_mode_no_drift(self):
        """--check exits 0 when all versions are in sync."""
        with mock.patch("sys.argv", ["sync-version.py", "--check"]):
            result = self.mod.main()
        self.assertEqual(result, 0)

    def test_apply_rules_detects_drift(self):
        """apply_rules detects version drift in a test file."""
        tmpdir = tempfile.mkdtemp()
        try:
            # Create a file with a stale version
            test_file = Path(tmpdir) / "test.md"
            test_file.write_text("rev: v0.0.0\n")

            rules = [
                self.mod.Rule(
                    "test.md",
                    r"rev:\s*v(?P<ver>\d+\.\d+\.\d+)",
                    "rev: v{version}",
                ),
            ]
            drifts = self.mod.apply_rules(rules, Path(tmpdir), "1.2.3", fix=False)
            self.assertEqual(len(drifts), 1)
            self.assertIn("0.0.0", drifts[0])
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_apply_rules_fixes_drift(self):
        """apply_rules with fix=True patches the file."""
        tmpdir = tempfile.mkdtemp()
        try:
            test_file = Path(tmpdir) / "test.md"
            test_file.write_text("rev: v0.0.0\n")

            rules = [
                self.mod.Rule(
                    "test.md",
                    r"rev:\s*v(?P<ver>\d+\.\d+\.\d+)",
                    "rev: v{version}",
                ),
            ]
            drifts = self.mod.apply_rules(rules, Path(tmpdir), "1.2.3", fix=True)
            self.assertEqual(len(drifts), 1)
            content = test_file.read_text()
            self.assertIn("v1.2.3", content)
            self.assertNotIn("v0.0.0", content)
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_apply_rules_missing_file_skipped(self):
        """Missing files are silently skipped."""
        rules = [
            self.mod.Rule("nonexistent.md", r"v(?P<ver>\d+)", "v{version}"),
        ]
        drifts = self.mod.apply_rules(rules, Path("/tmp"), "1.0.0", fix=False)
        self.assertEqual(drifts, [])

    def test_apply_rules_stale_pattern(self):
        """Pattern that doesn't match generates a warning."""
        tmpdir = tempfile.mkdtemp()
        try:
            test_file = Path(tmpdir) / "test.md"
            test_file.write_text("no version here\n")

            rules = [
                self.mod.Rule(
                    "test.md",
                    r"rev:\s*v(?P<ver>\d+\.\d+\.\d+)",
                    "rev: v{version}",
                ),
            ]
            drifts = self.mod.apply_rules(rules, Path(tmpdir), "1.0.0", fix=False)
            self.assertEqual(len(drifts), 1)
            self.assertIn("pattern not found", drifts[0])
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_aiir_rules_not_empty(self):
        """AIIR_RULES covers critical files."""
        paths = [r.path for r in self.mod.AIIR_RULES]
        self.assertIn("mcp-manifest.json", paths)
        self.assertIn("README.md", paths)

    def test_aiir_rules_cover_public_example_version_docs(self):
        """Public example docs with live release strings stay under sync-version."""
        paths = {r.path for r in self.mod.AIIR_RULES}
        self.assertIn("examples/witness-quorum/VERIFY.md", paths)
        self.assertIn("contrib/guac/README.md", paths)

    def test_website_rules_present(self):
        """WEBSITE_RULES exist for cross-repo sync."""
        self.assertGreater(len(self.mod.WEBSITE_RULES), 0)


# ═══════════════════════════════════════════════════════════════════════
# verify-release-evidence.py
# ═══════════════════════════════════════════════════════════════════════


class TestVerifyReleaseEvidence(unittest.TestCase):
    """Tests for scripts/verify-release-evidence.py logic."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module(
            "verify_release_evidence", SCRIPTS_DIR / "verify-release-evidence.py"
        )

    def test_build_parser_accepts_version_verbose_and_repo(self):
        """CLI accepts an optional version, --verbose, and --repo."""
        parser = self.mod.build_parser()
        args = parser.parse_args(["1.2.5", "--verbose", "--repo", "example/repo"])
        self.assertEqual(args.version, "1.2.5")
        self.assertTrue(args.verbose)
        self.assertEqual(args.repo, "example/repo")

    def test_verify_release_attest_manifest_fails_on_mismatched_sbom_hash_with_distributions(
        self,
    ):
        """A bad SBOM hash fails the manifest check even when distribution rows are correct."""
        fake_mod = mock.Mock()
        fake_mod.get_release_files.return_value = [
            {
                "filename": "aiir-1.2.5-py3-none-any.whl",
                "url": "https://files.pythonhosted.org/packages/demo.whl",
                "digests": {"sha256": "a" * 64},
            }
        ]
        fake_mod.PYPI_PROJECT = "aiir"
        fake_mod.PYPI_INTEGRITY_URL = (
            "https://pypi.org/integrity/{project}/{version}/{filename}/provenance"
        )

        with (
            mock.patch.object(
                self.mod,
                "get_release_asset_urls",
                return_value={
                    "release-attest.json": "https://example.invalid/release-attest.json",
                    "release-attest.md": "https://example.invalid/release-attest.md",
                    "aiir-1.2.5-py3-none-any.whl": "https://example.invalid/wheel",
                    "aiir-1.2.5-py3-none-any.whl.intoto.jsonl": "https://example.invalid/bundle",
                    "aiir-sbom.cdx.json": "https://example.invalid/sbom",
                },
            ),
            mock.patch.object(
                self.mod,
                "_fetch_json",
                return_value=[
                    {
                        "kind": "distribution",
                        "artifact": "aiir-1.2.5-py3-none-any.whl",
                        "sha256": "a" * 64,
                        "github_release_asset_url": "https://example.invalid/wheel",
                        "github_provenance_asset": "aiir-1.2.5-py3-none-any.whl.intoto.jsonl",
                        "github_provenance_asset_url": "https://example.invalid/bundle",
                        "pypi_attestation_url": "https://pypi.org/integrity/aiir/1.2.5/aiir-1.2.5-py3-none-any.whl/provenance",
                        "pypi_file_url": "https://files.pythonhosted.org/packages/demo.whl",
                        "rekor_entries": [{"log_index": "42"}],
                    },
                    {
                        "kind": "sbom",
                        "artifact": "aiir-sbom.cdx.json",
                        "sha256": "b" * 64,
                        "github_release_asset_url": "https://example.invalid/sbom",
                        "github_provenance_asset": "",
                        "github_provenance_asset_url": "",
                        "pypi_attestation_url": "",
                        "pypi_file_url": "",
                        "rekor_entries": [],
                    },
                ],
            ),
            mock.patch.object(self.mod, "_fetch_bytes", return_value=b"sbom-bytes"),
        ):
            result = self.mod.verify_release_attest_manifest("1.2.5", fake_mod)

        self.assertFalse(result)

    def test_verify_release_attest_manifest_happy_path_with_sbom_hash(self):
        """The verifier accepts a manifest when the SBOM hash matches the downloaded asset."""
        fake_mod = mock.Mock()
        fake_mod.get_release_files.return_value = [
            {
                "filename": "aiir-1.2.5-py3-none-any.whl",
                "url": "https://files.pythonhosted.org/packages/demo.whl",
                "digests": {"sha256": "a" * 64},
            }
        ]
        fake_mod.PYPI_PROJECT = "aiir"
        fake_mod.PYPI_INTEGRITY_URL = (
            "https://pypi.org/integrity/{project}/{version}/{filename}/provenance"
        )
        sbom_hash = hashlib.sha256(b"sbom-bytes").hexdigest()

        with (
            mock.patch.object(
                self.mod,
                "get_release_asset_urls",
                return_value={
                    "release-attest.json": "https://example.invalid/release-attest.json",
                    "release-attest.md": "https://example.invalid/release-attest.md",
                    "aiir-1.2.5-py3-none-any.whl": "https://example.invalid/wheel",
                    "aiir-1.2.5-py3-none-any.whl.intoto.jsonl": "https://example.invalid/bundle",
                    "aiir-sbom.cdx.json": "https://example.invalid/sbom",
                },
            ),
            mock.patch.object(
                self.mod,
                "_fetch_json",
                return_value=[
                    {
                        "kind": "distribution",
                        "artifact": "aiir-1.2.5-py3-none-any.whl",
                        "sha256": "a" * 64,
                        "github_release_asset_url": "https://example.invalid/wheel",
                        "github_provenance_asset": "aiir-1.2.5-py3-none-any.whl.intoto.jsonl",
                        "github_provenance_asset_url": "https://example.invalid/bundle",
                        "pypi_attestation_url": "https://pypi.org/integrity/aiir/1.2.5/aiir-1.2.5-py3-none-any.whl/provenance",
                        "pypi_file_url": "https://files.pythonhosted.org/packages/demo.whl",
                        "rekor_entries": [{"log_index": "42"}],
                    },
                    {
                        "kind": "sbom",
                        "artifact": "aiir-sbom.cdx.json",
                        "sha256": sbom_hash,
                        "github_release_asset_url": "https://example.invalid/sbom",
                        "github_provenance_asset": "",
                        "github_provenance_asset_url": "",
                        "pypi_attestation_url": "",
                        "pypi_file_url": "",
                        "rekor_entries": [],
                    },
                ],
            ),
            mock.patch.object(self.mod, "_fetch_bytes", return_value=b"sbom-bytes"),
        ):
            result = self.mod.verify_release_attest_manifest("1.2.5", fake_mod)

        self.assertTrue(result)

    def test_verify_release_attest_manifest_fails_on_missing_assets(self):
        """Missing release-attest assets fail the public release-evidence gate."""
        fake_mod = mock.Mock()

        with mock.patch.object(
            self.mod,
            "get_release_asset_urls",
            return_value={
                "release-attest.json": "https://example.invalid/release-attest.json"
            },
        ):
            result = self.mod.verify_release_attest_manifest("1.2.5", fake_mod)

        self.assertFalse(result)

    def test_verify_release_attest_manifest_fails_on_missing_sbom_asset(self):
        """Missing SBOM release assets fail the public release-evidence gate."""
        fake_mod = mock.Mock()
        fake_mod.get_release_files.return_value = []

        with (
            mock.patch.object(
                self.mod,
                "get_release_asset_urls",
                return_value={
                    "release-attest.json": "https://example.invalid/release-attest.json",
                    "release-attest.md": "https://example.invalid/release-attest.md",
                },
            ),
            mock.patch.object(self.mod, "_fetch_json", return_value=[]),
        ):
            result = self.mod.verify_release_attest_manifest("1.2.5", fake_mod)

        self.assertFalse(result)

    def test_verify_release_attest_manifest_fails_on_mismatched_sha(self):
        """Digest mismatches in release-attest.json fail closed."""
        fake_mod = mock.Mock()
        fake_mod.get_release_files.return_value = [
            {
                "filename": "aiir-1.2.5.tar.gz",
                "url": "https://files.pythonhosted.org/packages/demo.tar.gz",
                "digests": {"sha256": "b" * 64},
            }
        ]
        fake_mod.PYPI_PROJECT = "aiir"
        fake_mod.PYPI_INTEGRITY_URL = (
            "https://pypi.org/integrity/{project}/{version}/{filename}/provenance"
        )

        with (
            mock.patch.object(
                self.mod,
                "get_release_asset_urls",
                return_value={
                    "release-attest.json": "https://example.invalid/release-attest.json",
                    "release-attest.md": "https://example.invalid/release-attest.md",
                    "aiir-1.2.5.tar.gz": "https://example.invalid/sdist",
                    "aiir-1.2.5.tar.gz.intoto.jsonl": "https://example.invalid/bundle",
                },
            ),
            mock.patch.object(
                self.mod,
                "_fetch_json",
                return_value=[
                    {
                        "kind": "distribution",
                        "artifact": "aiir-1.2.5.tar.gz",
                        "sha256": "c" * 64,
                        "github_release_asset_url": "https://example.invalid/sdist",
                        "github_provenance_asset": "aiir-1.2.5.tar.gz.intoto.jsonl",
                        "github_provenance_asset_url": "https://example.invalid/bundle",
                        "pypi_attestation_url": "https://pypi.org/integrity/aiir/1.2.5/aiir-1.2.5.tar.gz/provenance",
                        "pypi_file_url": "https://files.pythonhosted.org/packages/demo.tar.gz",
                        "rekor_entries": [{"log_index": "42"}],
                    },
                    {
                        "kind": "sbom",
                        "artifact": "aiir-sbom.cdx.json",
                        "sha256": hashlib.sha256(b"sbom-bytes").hexdigest(),
                        "github_release_asset_url": "https://example.invalid/sbom",
                        "github_provenance_asset": "",
                        "github_provenance_asset_url": "",
                        "pypi_attestation_url": "",
                        "pypi_file_url": "",
                        "rekor_entries": [],
                    },
                ],
            ),
            mock.patch.object(self.mod, "_fetch_bytes", return_value=b"sbom-bytes"),
        ):
            result = self.mod.verify_release_attest_manifest("1.2.5", fake_mod)

        self.assertFalse(result)

    def test_verify_release_attest_manifest_fails_on_mismatched_sbom_sha(self):
        """SBOM digest mismatches in release-attest.json fail closed."""
        fake_mod = mock.Mock()
        fake_mod.get_release_files.return_value = []
        fake_mod.PYPI_PROJECT = "aiir"
        fake_mod.PYPI_INTEGRITY_URL = (
            "https://pypi.org/integrity/{project}/{version}/{filename}/provenance"
        )

        with (
            mock.patch.object(
                self.mod,
                "get_release_asset_urls",
                return_value={
                    "release-attest.json": "https://example.invalid/release-attest.json",
                    "release-attest.md": "https://example.invalid/release-attest.md",
                    "aiir-sbom.cdx.json": "https://example.invalid/sbom",
                },
            ),
            mock.patch.object(
                self.mod,
                "_fetch_json",
                return_value=[
                    {
                        "kind": "sbom",
                        "artifact": "aiir-sbom.cdx.json",
                        "sha256": "f" * 64,
                        "github_release_asset_url": "https://example.invalid/sbom",
                        "github_provenance_asset": "",
                        "github_provenance_asset_url": "",
                        "pypi_attestation_url": "",
                        "pypi_file_url": "",
                        "rekor_entries": [],
                    }
                ],
            ),
            mock.patch.object(self.mod, "_fetch_bytes", return_value=b"sbom-bytes"),
        ):
            result = self.mod.verify_release_attest_manifest("1.2.5", fake_mod)

        self.assertFalse(result)

    def test_main_uses_latest_version_when_unspecified(self):
        """Wrapper defaults to the latest published version."""
        fake_mod = mock.Mock()
        fake_mod.get_latest_version.return_value = "1.2.5"
        fake_mod.verify_release.return_value = True

        with (
            mock.patch.object(self.mod, "_load_verify_module", return_value=fake_mod),
            mock.patch.object(
                self.mod, "verify_release_attest_manifest", return_value=True
            ) as verify_manifest,
        ):
            result = self.mod.main([])

        self.assertEqual(result, 0)
        fake_mod.get_latest_version.assert_called_once_with()
        fake_mod.verify_release.assert_called_once_with(
            "1.2.5", strict=True, verbose=False
        )
        verify_manifest.assert_called_once_with(
            "1.2.5", fake_mod, repo=self.mod.DEFAULT_REPO, verbose=False
        )

    def test_main_passes_explicit_version_and_verbose(self):
        """Wrapper forwards version and verbosity to the underlying verifier."""
        fake_mod = mock.Mock()
        fake_mod.verify_release.return_value = True

        with (
            mock.patch.object(self.mod, "_load_verify_module", return_value=fake_mod),
            mock.patch.object(
                self.mod, "verify_release_attest_manifest", return_value=True
            ) as verify_manifest,
        ):
            result = self.mod.main(["1.2.4", "--verbose", "--repo", "example/repo"])

        self.assertEqual(result, 0)
        fake_mod.get_latest_version.assert_not_called()
        fake_mod.verify_release.assert_called_once_with(
            "1.2.4", strict=True, verbose=True
        )
        verify_manifest.assert_called_once_with(
            "1.2.4", fake_mod, repo="example/repo", verbose=True
        )

    def test_main_returns_one_when_verifier_fails(self):
        """Wrapper fails closed when provenance coverage is incomplete."""
        fake_mod = mock.Mock()
        fake_mod.verify_release.return_value = False

        with (
            mock.patch.object(self.mod, "_load_verify_module", return_value=fake_mod),
            mock.patch.object(
                self.mod, "verify_release_attest_manifest", return_value=True
            ),
        ):
            result = self.mod.main(["1.2.4"])

        self.assertEqual(result, 1)

    def test_main_returns_one_when_release_manifest_fails(self):
        """Wrapper fails closed when the GitHub release attestation surface is inconsistent."""
        fake_mod = mock.Mock()
        fake_mod.verify_release.return_value = True

        with (
            mock.patch.object(self.mod, "_load_verify_module", return_value=fake_mod),
            mock.patch.object(
                self.mod, "verify_release_attest_manifest", return_value=False
            ),
        ):
            result = self.mod.main(["1.2.4"])

        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()


# =============================================================================
# verify-pypi-provenance.py  (security-fix tests)
# =============================================================================


class TestVerifyPyPIProvenance(unittest.TestCase):
    """Tests for scripts/verify-pypi-provenance.py after the report-verified-
    for-unverified security fix.

    Each test describes the exploit it closes (failing-before / passing-after).
    """

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module(
            "verify_pypi_provenance",
            SCRIPTS_DIR / "verify-pypi-provenance.py",
        )

    # ---- constants ----------------------------------------------------------

    def test_expected_repository_constant(self):
        """EXPECTED_REPOSITORY must name the canonical AIIR repo."""
        self.assertEqual(self.mod.EXPECTED_REPOSITORY, "invariant-systems-ai/aiir")

    def test_expected_workflow_constant(self):
        """EXPECTED_WORKFLOW must be the publish workflow."""
        self.assertEqual(self.mod.EXPECTED_WORKFLOW, "publish.yml")

    def test_expected_environment_constant(self):
        """EXPECTED_ENVIRONMENT must be the PyPI environment."""
        self.assertEqual(self.mod.EXPECTED_ENVIRONMENT, "pypi")

    def test_expected_predicate_type_constant(self):
        """EXPECTED_PREDICATE_TYPE must be the PyPI publish predicate."""
        self.assertEqual(
            self.mod.EXPECTED_PREDICATE_TYPE,
            "https://docs.pypi.org/attestations/publish/v1",
        )

    # ---- _check_bundle_structural -------------------------------------------

    def test_structural_check_rejects_wrong_repository(self):
        """Exploit: attacker bundle with wrong repo must fail structural check."""
        bundle = {
            "publisher": {
                "kind": "GitHub",
                "repository": "attacker/malicious",
                "workflow": "publish.yml",
                "environment": "pypi",
            },
            "attestations": [
                {"predicate_type": "https://docs.pypi.org/attestations/publish/v1"}
            ],
        }
        ok, issues = self.mod._check_bundle_structural(bundle)
        self.assertFalse(ok, "fabricated repo should fail structural check")
        self.assertTrue(
            any("repository" in i for i in issues),
            "issues should mention repository mismatch",
        )

    def test_structural_check_rejects_wrong_workflow(self):
        """Bundle with wrong workflow name must fail structural check."""
        bundle = {
            "publisher": {
                "kind": "GitHub",
                "repository": "invariant-systems-ai/aiir",
                "workflow": "evil.yml",
                "environment": "pypi",
            },
            "attestations": [
                {"predicate_type": "https://docs.pypi.org/attestations/publish/v1"}
            ],
        }
        ok, issues = self.mod._check_bundle_structural(bundle)
        self.assertFalse(ok)
        self.assertTrue(any("workflow" in i for i in issues))

    def test_structural_check_rejects_wrong_environment(self):
        """Bundle with wrong environment must fail structural check."""
        bundle = {
            "publisher": {
                "kind": "GitHub",
                "repository": "invariant-systems-ai/aiir",
                "workflow": "publish.yml",
                "environment": "testpypi",
            },
            "attestations": [
                {"predicate_type": "https://docs.pypi.org/attestations/publish/v1"}
            ],
        }
        ok, issues = self.mod._check_bundle_structural(bundle)
        self.assertFalse(ok)
        self.assertTrue(any("environment" in i for i in issues))

    def test_structural_check_rejects_wrong_predicate(self):
        """Bundle with wrong predicate type must fail structural check."""
        bundle = {
            "publisher": {
                "kind": "GitHub",
                "repository": "invariant-systems-ai/aiir",
                "workflow": "publish.yml",
                "environment": "pypi",
            },
            "attestations": [
                {"predicate_type": "https://evil.example.com/bad/predicate"}
            ],
        }
        ok, issues = self.mod._check_bundle_structural(bundle)
        self.assertFalse(ok)
        self.assertTrue(any("predicate" in i for i in issues))

    def test_structural_check_rejects_missing_publisher(self):
        """Bundle without a publisher object must fail structural check."""
        bundle = {
            "attestations": [
                {"predicate_type": "https://docs.pypi.org/attestations/publish/v1"}
            ]
        }
        ok, issues = self.mod._check_bundle_structural(bundle)
        self.assertFalse(ok)
        self.assertTrue(any("publisher" in i for i in issues))

    def test_structural_check_passes_correct_bundle(self):
        """A correctly formed bundle passes structural identity check."""
        bundle = {
            "publisher": {
                "kind": "GitHub",
                "repository": "invariant-systems-ai/aiir",
                "workflow": "publish.yml",
                "environment": "pypi",
            },
            "attestations": [
                {"predicate_type": "https://docs.pypi.org/attestations/publish/v1"}
            ],
        }
        ok, issues = self.mod._check_bundle_structural(bundle)
        self.assertTrue(ok, "correct bundle should pass: %s" % issues)
        self.assertEqual(issues, [])

    # ---- check_attestation (integration) ------------------------------------

    def _good_bundle_response(self):
        return {
            "attestation_bundles": [
                {
                    "publisher": {
                        "kind": "GitHub",
                        "repository": "invariant-systems-ai/aiir",
                        "workflow": "publish.yml",
                        "environment": "pypi",
                    },
                    "attestations": [
                        {
                            "predicate_type": (
                                "https://docs.pypi.org/attestations/publish/v1"
                            )
                        }
                    ],
                }
            ]
        }

    def _fabricated_bundle_response(self):
        """Exploit payload: looks like an attestation but from wrong repo."""
        return {
            "attestation_bundles": [
                {
                    "publisher": {
                        "kind": "GitHub",
                        "repository": "attacker/malicious",
                        "workflow": "evil.yml",
                        "environment": "nowhere",
                    },
                    "attestations": [
                        {
                            "predicate_type": (
                                "https://docs.pypi.org/attestations/publish/v1"
                            )
                        }
                    ],
                }
            ]
        }

    def test_check_attestation_fabricated_bundle_not_reported_verified(self):
        """EXPLOIT CLOSED: fabricated attestation bundle must NOT be has_attestations=True.

        Before fix: len(bundles)>0 was enough -> has_attestations=True for any bundle.
        After fix: structural identity check must pass too.
        """
        with mock.patch.object(
            self.mod,
            "_fetch_json_safe",
            return_value=(self._fabricated_bundle_response(), 200),
        ):
            result = self.mod.check_attestation("1.0.0", "aiir-1.0.0-py3-none-any.whl")

        self.assertFalse(
            result["has_attestations"],
            "fabricated bundle from wrong repo must NOT be reported as attested",
        )
        self.assertGreater(
            len(result["structural_issues"]),
            0,
            "structural_issues must report the identity mismatch",
        )

    def test_check_attestation_good_bundle_passes_structural(self):
        """Correctly formed bundle from the right identity passes structural check."""
        with mock.patch.object(
            self.mod,
            "_fetch_json_safe",
            return_value=(self._good_bundle_response(), 200),
        ):
            result = self.mod.check_attestation("1.0.0", "aiir-1.0.0-py3-none-any.whl")

        self.assertTrue(result["has_attestations"])
        self.assertEqual(result["verification_level"], self.mod.LEVEL_STRUCTURAL)
        self.assertFalse(result["crypto_verified"])  # no sigstore installed
        self.assertEqual(result["structural_issues"], [])

    def test_check_attestation_empty_bundles_not_attested(self):
        """Empty bundle list must result in has_attestations=False."""
        with mock.patch.object(
            self.mod,
            "_fetch_json_safe",
            return_value=({"attestation_bundles": []}, 200),
        ):
            result = self.mod.check_attestation("1.0.0", "aiir-1.0.0-py3-none-any.whl")

        self.assertFalse(result["has_attestations"])
        self.assertEqual(result["attestation_count"], 0)

    def test_check_attestation_404_not_attested(self):
        """404 from Integrity API must return has_attestations=False."""
        with mock.patch.object(self.mod, "_fetch_json_safe", return_value=(None, 404)):
            result = self.mod.check_attestation("1.0.0", "aiir-1.0.0-py3-none-any.whl")

        self.assertFalse(result["has_attestations"])
        self.assertEqual(result["http_code"], 404)

    # ---- verify_release output wording (structural level) -------------------

    def test_verify_release_structural_does_not_claim_cryptographic_guarantee(self):
        """When no crypto libs available, output must NOT claim 'All release
        artifacts are attested.' (the old misleading claim) for structural only.
        """
        files = [
            {
                "filename": "aiir-1.0.0-py3-none-any.whl",
                "packagetype": "bdist_wheel",
                "size": 100,
                "digests": {"sha256": "a" * 64},
            }
        ]
        with (
            mock.patch.object(self.mod, "get_release_files", return_value=files),
            mock.patch.object(
                self.mod,
                "_fetch_json_safe",
                return_value=(self._good_bundle_response(), 200),
            ),
            mock.patch.object(self.mod, "_crypto_libs_available", return_value=False),
        ):
            import io

            buf = io.StringIO()
            old_stdout = __import__("sys").stdout
            __import__("sys").stdout = buf
            result = self.mod.verify_release("1.0.0")
            __import__("sys").stdout = old_stdout

        output = buf.getvalue()
        # Must not contain the old unqualified "All release artifacts are attested."
        self.assertNotIn(
            "All release artifacts are attested.",
            output,
            "structural check must not claim cryptographic attestation",
        )
        # Must mention structural nature
        self.assertIn(
            "structural",
            output.lower(),
            "output must explain that only a structural check was performed",
        )
        # Must return True (coverage is complete at structural level)
        self.assertTrue(result)

    def test_verify_release_fabricated_bundle_fails_strict(self):
        """EXPLOIT CLOSED: fabricated attestation must fail strict verify_release."""
        files = [
            {
                "filename": "aiir-1.0.0-py3-none-any.whl",
                "packagetype": "bdist_wheel",
                "size": 100,
                "digests": {"sha256": "a" * 64},
            }
        ]
        with (
            mock.patch.object(self.mod, "get_release_files", return_value=files),
            mock.patch.object(
                self.mod,
                "_fetch_json_safe",
                return_value=(self._fabricated_bundle_response(), 200),
            ),
            mock.patch.object(self.mod, "_crypto_libs_available", return_value=False),
        ):
            result = self.mod.verify_release("1.0.0", strict=True)

        self.assertFalse(
            result,
            "fabricated attestation from wrong repo must fail strict verify_release",
        )

    def test_verify_release_cryptographic_banner_only_when_crypto_available(self):
        """When crypto libs ARE available and check passes, output must mention
        cryptographic verification (not just structural)."""
        files = [
            {
                "filename": "aiir-1.0.0-py3-none-any.whl",
                "packagetype": "bdist_wheel",
                "size": 100,
                "digests": {"sha256": "a" * 64},
            }
        ]
        good_result = {
            "filename": "aiir-1.0.0-py3-none-any.whl",
            "has_attestations": True,
            "http_code": 200,
            "attestation_count": 1,
            "predicates": ["https://docs.pypi.org/attestations/publish/v1"],
            "verification_level": self.mod.LEVEL_CRYPTOGRAPHIC,
            "structural_issues": [],
            "crypto_verified": True,
            "raw": None,
        }
        with (
            mock.patch.object(self.mod, "get_release_files", return_value=files),
            mock.patch.object(self.mod, "check_attestation", return_value=good_result),
            mock.patch.object(self.mod, "_crypto_libs_available", return_value=True),
        ):
            import io

            buf = io.StringIO()
            old_stdout = __import__("sys").stdout
            __import__("sys").stdout = buf
            result = self.mod.verify_release("1.0.0")
            __import__("sys").stdout = old_stdout

        output = buf.getvalue()
        self.assertTrue(result)
        self.assertIn(
            "cryptographic",
            output.lower(),
            "crypto-level verification output must mention cryptographic",
        )

    # ---- _crypto_libs_available ---------------------------------------------

    def test_crypto_libs_available_returns_false_when_missing(self):
        """Without pypi_attestations installed, must return False."""
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name in ("pypi_attestations", "sigstore"):
                raise ImportError("not installed")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=fake_import):
            result = self.mod._crypto_libs_available()
        self.assertFalse(result)

    # ---- verification_level field -------------------------------------------

    def test_check_attestation_result_has_verification_level(self):
        """Result dict must include verification_level key."""
        with mock.patch.object(self.mod, "_fetch_json_safe", return_value=(None, 404)):
            result = self.mod.check_attestation("1.0.0", "demo.whl")
        self.assertIn("verification_level", result)
        self.assertEqual(result["verification_level"], self.mod.LEVEL_STRUCTURAL)

    def test_check_attestation_result_has_structural_issues(self):
        """Result dict must include structural_issues key (list)."""
        with mock.patch.object(self.mod, "_fetch_json_safe", return_value=(None, 404)):
            result = self.mod.check_attestation("1.0.0", "demo.whl")
        self.assertIn("structural_issues", result)
        self.assertIsInstance(result["structural_issues"], list)

    def test_check_attestation_result_has_crypto_verified(self):
        """Result dict must include crypto_verified key (bool)."""
        with mock.patch.object(self.mod, "_fetch_json_safe", return_value=(None, 404)):
            result = self.mod.check_attestation("1.0.0", "demo.whl")
        self.assertIn("crypto_verified", result)
        self.assertIsInstance(result["crypto_verified"], bool)
