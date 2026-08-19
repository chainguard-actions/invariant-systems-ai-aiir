# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
from __future__ import annotations

import base64
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "enforce_pypi_provenance.py"
PUBLISH_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish.yml"


def _load_module():
    spec = importlib.util.spec_from_file_location("enforce_pypi_provenance", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestPublishWorkflowProvenanceGate(unittest.TestCase):
    def test_publish_workflow_uses_pypi_attestations(self):
        content = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("pypi-attestations==0.0.29", content)
        self.assertIn("python3 -m venv", content)
        self.assertIn('venv/bin/pypi-attestations" verify pypi', content)
        self.assertIn("scripts/enforce_pypi_provenance.py", content)


class TestEnforcePyPIProvenanceHelpers(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    def test_decode_statement_round_trip(self):
        statement = {"subject": [{"name": "a.whl", "digest": {"sha256": "abc"}}]}
        encoded = base64.b64encode(json.dumps(statement).encode("utf-8")).decode(
            "ascii"
        )
        self.assertEqual(self.module.decode_statement(encoded), statement)

    def test_expected_predicates_require_publish_attestation(self):
        self.assertIn(
            "https://docs.pypi.org/attestations/publish/v1",
            self.module.EXPECTED_PREDICATE_TYPES,
        )
        self.assertEqual(len(self.module.EXPECTED_PREDICATE_TYPES), 1)

    def test_enforce_file_rejects_missing_publisher_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            artifact = out_dir / "demo.whl"
            artifact.write_bytes(b"demo-wheel")
            digest = self.module.sha256_file(artifact)

            provenance = {
                "attestation_bundles": [
                    {
                        "publisher": {
                            "kind": "GitHub",
                            "repository": "wrong/repo",
                            "workflow": "publish.yml",
                            "environment": "pypi",
                        },
                        "attestations": [
                            {
                                "envelope": {
                                    "statement": base64.b64encode(
                                        json.dumps(
                                            {
                                                "subject": [
                                                    {
                                                        "name": "demo.whl",
                                                        "digest": {"sha256": digest},
                                                    }
                                                ],
                                                "predicateType": "https://docs.pypi.org/attestations/publish/v1",
                                            }
                                        ).encode("utf-8")
                                    ).decode("ascii")
                                }
                            },
                        ],
                    }
                ]
            }

            original_download = self.module.download
            original_fetch = self.module.fetch_json_retry
            try:

                def fake_download(url: str, destination: Path) -> None:
                    destination.write_bytes(artifact.read_bytes())

                def fake_fetch(url: str, *, retries: int, delay_seconds: int):
                    return provenance, 200

                self.module.download = fake_download
                self.module.fetch_json_retry = fake_fetch

                with self.assertRaises(RuntimeError) as ctx:
                    self.module.enforce_file(
                        project="aiir",
                        version="1.2.5",
                        file_info={
                            "filename": "demo.whl",
                            "url": "https://example.invalid/demo.whl",
                            "digests": {"sha256": digest},
                        },
                        out_dir=out_dir,
                        expected_repository="invariant-systems-ai/aiir",
                        expected_workflow="publish.yml",
                        expected_environment="pypi",
                        retries=1,
                        delay_seconds=0,
                    )
                self.assertIn("Publisher policy mismatch", str(ctx.exception))
            finally:
                self.module.download = original_download
                self.module.fetch_json_retry = original_fetch


if __name__ == "__main__":
    unittest.main()
