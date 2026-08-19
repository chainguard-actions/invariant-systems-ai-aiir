# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
from __future__ import annotations

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "emit_release_attest.py"
PUBLISH_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish.yml"


def _load_module():
    spec = importlib.util.spec_from_file_location("emit_release_attest", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestPublishWorkflowReleaseAttestSurface(unittest.TestCase):
    def test_publish_workflow_emits_release_attestation_surface(self):
        content = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("scripts/emit_release_attest.py", content)
        self.assertIn("release-attest.json", content)
        self.assertIn("release-attest.md", content)
        self.assertIn("--asset-dir", content)
        self.assertIn("--sbom-path", content)
        self.assertIn("aiir-sbom.cdx.json", content)


class TestEmitReleaseAttestCliSurface(unittest.TestCase):
    def test_tag_help_uses_version_agnostic_example(self):
        content = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("Release tag, e.g. vX.Y.Z", content)
        self.assertNotIn("Release tag, e.g. v1.3.0", content)


class TestEmitReleaseAttestHelpers(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    def test_sha256_file_matches_hashlib(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "artifact.whl"
            path.write_bytes(b"artifact-bytes")
            self.assertEqual(
                self.module.sha256_file(path),
                hashlib.sha256(b"artifact-bytes").hexdigest(),
            )

    def test_extract_tlog_entries_reads_log_metadata(self):
        bundle = {
            "verificationMaterial": {
                "tlogEntries": [
                    {
                        "logIndex": "1079928472",
                        "integratedTime": "1773225577",
                        "logId": {"keyId": "abc"},
                        "kindVersion": {"kind": "dsse"},
                    }
                ]
            }
        }
        self.assertEqual(
            self.module.extract_tlog_entries(bundle),
            [
                {
                    "log_index": "1079928472",
                    "integrated_time": "1773225577",
                    "log_id": "abc",
                    "kind": "dsse",
                }
            ],
        )

    def test_upsert_marked_section_inserts_and_replaces(self):
        inserted = self.module.upsert_marked_section(
            "Base body",
            self.module.BEGIN_MARKER + "\nX\n" + self.module.END_MARKER + "\n",
        )
        self.assertIn("Base body", inserted)
        self.assertIn(self.module.BEGIN_MARKER, inserted)

        replaced = self.module.upsert_marked_section(
            inserted,
            self.module.BEGIN_MARKER + "\nY\n" + self.module.END_MARKER + "\n",
        )
        self.assertIn("Y", replaced)
        self.assertNotIn("\nX\n", replaced)

    def test_render_markdown_includes_provenance_links(self):
        markdown = self.module.render_markdown(
            [
                {
                    "kind": "distribution",
                    "artifact": "aiir-1.2.5-py3-none-any.whl",
                    "sha256": "a" * 64,
                    "github_release_asset_url": "https://example.invalid/wheel",
                    "github_provenance_asset_url": "https://example.invalid/bundle",
                    "pypi_attestation_url": "https://pypi.org/integrity/aiir/1.2.5/file/provenance",
                    "pypi_file_url": "https://files.pythonhosted.org/demo.whl",
                    "rekor_entries": [{"log_index": "42"}],
                }
            ],
            project="aiir",
            tag="v1.2.5",
        )
        self.assertIn("## Provenance & Verification", markdown)
        self.assertIn("sha256:" + "a" * 64, markdown)
        self.assertIn("PyPI attestation", markdown)
        self.assertIn("GitHub bundle", markdown)
        self.assertIn("`42`", markdown)

    def test_render_markdown_includes_sbom_release_asset(self):
        markdown = self.module.render_markdown(
            [
                {
                    "kind": "sbom",
                    "artifact": "aiir-sbom.cdx.json",
                    "sha256": "b" * 64,
                    "github_release_asset_url": "https://example.invalid/sbom",
                    "github_provenance_asset_url": "",
                    "pypi_attestation_url": "",
                    "pypi_file_url": "",
                    "rekor_entries": [],
                }
            ],
            project="aiir",
            tag="v1.2.5",
        )
        self.assertIn("GitHub release asset", markdown)
        self.assertIn("verify-release-evidence.py 1.2.5", markdown)

    def test_build_release_attestation_rows_combines_release_and_pypi_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist_dir = Path(tmp) / "dist"
            dist_dir.mkdir()
            wheel = dist_dir / "aiir-1.2.5-py3-none-any.whl"
            wheel.write_bytes(b"wheel-bytes")
            sbom = Path(tmp) / "aiir-sbom.cdx.json"
            sbom.write_text('{"bomFormat":"CycloneDX"}', encoding="utf-8")
            digest = hashlib.sha256(b"wheel-bytes").hexdigest()
            sbom_digest = hashlib.sha256(sbom.read_bytes()).hexdigest()

            original_load_release_assets = self.module.load_release_assets
            original_load_pypi_release_files = self.module.load_pypi_release_files
            original_fetch_attestation_bundle = self.module.fetch_attestation_bundle
            try:
                self.module.load_release_assets = lambda repo, tag, token=None: {
                    wheel.name: "https://example.invalid/release/wheel",
                    f"{wheel.name}.intoto.jsonl": "https://example.invalid/release/bundle",
                    sbom.name: "https://example.invalid/release/sbom",
                }
                self.module.load_pypi_release_files = lambda project, version: [
                    {
                        "filename": wheel.name,
                        "url": "https://files.pythonhosted.org/packages/demo.whl",
                    }
                ]
                self.module.fetch_attestation_bundle = (
                    lambda repo, digest, token=None: {
                        "verificationMaterial": {
                            "tlogEntries": [
                                {
                                    "logIndex": "99",
                                    "integratedTime": "1773225577",
                                    "logId": {"keyId": "abc"},
                                    "kindVersion": {"kind": "dsse"},
                                }
                            ]
                        }
                    }
                )

                rows = self.module.build_release_attestation_rows(
                    repo="invariant-systems-ai/aiir",
                    tag="v1.2.5",
                    project="aiir",
                    dist_dir=dist_dir,
                    sbom_path=sbom,
                )
            finally:
                self.module.load_release_assets = original_load_release_assets
                self.module.load_pypi_release_files = original_load_pypi_release_files
                self.module.fetch_attestation_bundle = original_fetch_attestation_bundle

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["artifact"], wheel.name)
        self.assertEqual(rows[0]["kind"], "distribution")
        self.assertEqual(rows[0]["sha256"], digest)
        self.assertEqual(rows[0]["rekor_entries"][0]["log_index"], "99")
        self.assertEqual(
            rows[0]["github_provenance_asset"], f"{wheel.name}.intoto.jsonl"
        )
        self.assertEqual(rows[1]["artifact"], sbom.name)
        self.assertEqual(rows[1]["kind"], "sbom")
        self.assertEqual(rows[1]["sha256"], sbom_digest)
        self.assertEqual(
            rows[1]["github_release_asset_url"], "https://example.invalid/release/sbom"
        )
        self.assertEqual(rows[1]["rekor_entries"], [])

    def test_main_writes_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dist_dir = root / "dist"
            dist_dir.mkdir()
            artifact = dist_dir / "aiir-1.2.5.tar.gz"
            artifact.write_bytes(b"sdist-bytes")
            sbom = root / "aiir-sbom.cdx.json"
            sbom.write_text('{"bomFormat":"CycloneDX"}', encoding="utf-8")

            original_build_rows = self.module.build_release_attestation_rows
            original_fetch_json = self.module._fetch_json
            try:
                self.module.build_release_attestation_rows = lambda **kwargs: [
                    {
                        "kind": "distribution",
                        "artifact": artifact.name,
                        "sha256": hashlib.sha256(b"sdist-bytes").hexdigest(),
                        "github_release_asset_url": "",
                        "github_provenance_asset_url": "",
                        "pypi_attestation_url": "https://pypi.org/integrity/demo",
                        "pypi_file_url": "",
                        "rekor_entries": [],
                    },
                    {
                        "kind": "sbom",
                        "artifact": sbom.name,
                        "sha256": hashlib.sha256(sbom.read_bytes()).hexdigest(),
                        "github_release_asset_url": "https://example.invalid/sbom",
                        "github_provenance_asset_url": "",
                        "pypi_attestation_url": "",
                        "pypi_file_url": "",
                        "rekor_entries": [],
                    },
                ]
                self.module._fetch_json = lambda url, headers=None: {"body": "Existing"}

                json_out = root / "release-attest.json"
                md_out = root / "release-attest.md"
                body_out = root / "release-body.md"
                asset_dir = root / "release-assets"
                code = self.module.main(
                    [
                        "--repo",
                        "invariant-systems-ai/aiir",
                        "--tag",
                        "v1.2.5",
                        "--dist-dir",
                        str(dist_dir),
                        "--sbom-path",
                        str(sbom),
                        "--json-out",
                        str(json_out),
                        "--md-out",
                        str(md_out),
                        "--asset-dir",
                        str(asset_dir),
                        "--release-body-out",
                        str(body_out),
                    ]
                )
            finally:
                self.module.build_release_attestation_rows = original_build_rows
                self.module._fetch_json = original_fetch_json

            self.assertEqual(code, 0)
            self.assertTrue(json_out.exists())
            self.assertTrue(md_out.exists())
            self.assertTrue(body_out.exists())
            self.assertTrue(asset_dir.exists())
            self.assertTrue(
                (asset_dir / f"{artifact.name}.publish.attestation").exists()
            )
            self.assertTrue((asset_dir / f"rekor-{artifact.name}.json").exists())
            self.assertTrue((asset_dir / "VERIFY-OFFLINE.md").exists())
            self.assertIn(
                "Provenance & Verification", md_out.read_text(encoding="utf-8")
            )
            self.assertIn("aiir-sbom.cdx.json", md_out.read_text(encoding="utf-8"))
            self.assertIn("Existing", body_out.read_text(encoding="utf-8"))
            self.assertIn(
                "https://pypi.org/integrity/demo",
                (asset_dir / f"{artifact.name}.publish.attestation").read_text(
                    encoding="utf-8"
                ),
            )


if __name__ == "__main__":
    unittest.main()
