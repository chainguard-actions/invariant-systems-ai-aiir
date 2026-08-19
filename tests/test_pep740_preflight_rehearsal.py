# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "verify-attestations.yml"
SCRIPT = REPO_ROOT / "scripts" / "pep740_preflight_rehearsal.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("pep740_preflight_rehearsal", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestPep740RehearsalWorkflow(unittest.TestCase):
    def test_workflow_is_manual_rehearsal(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", content)
        self.assertIn("event: [push, pull_request]", content)
        self.assertIn("source: [pypi, gh-release]", content)

    def test_workflow_uploads_logs(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Upload machine-readable logs", content)
        self.assertIn(
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a", content
        )
        self.assertIn(
            "pep740-preflight/${{ matrix.event }}-${{ matrix.source }}/", content
        )


class TestPep740RehearsalHelpers(unittest.TestCase):
    def setUp(self):
        self.module = _load_module()

    def test_failure_code_mapping(self):
        self.assertEqual(self.module.failure_code_for("pypi", "push"), 11)
        self.assertEqual(self.module.failure_code_for("pypi", "pull_request"), 12)
        self.assertEqual(self.module.failure_code_for("gh-release", "push"), 13)
        self.assertEqual(self.module.failure_code_for("gh-release", "pull_request"), 14)

    def test_mutate_digest_changes_value(self):
        digest = "a" * 64
        mutated = self.module.mutate_digest(digest)
        self.assertEqual(len(mutated), 64)
        self.assertNotEqual(mutated, digest)

    def test_mutate_digest_handles_empty_input(self):
        self.assertEqual(self.module.mutate_digest(""), "0" * 64)


if __name__ == "__main__":
    unittest.main()
