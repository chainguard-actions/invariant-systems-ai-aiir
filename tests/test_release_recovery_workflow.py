# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release-recovery.yml"
RELEASE_SMOKE = REPO_ROOT / ".github" / "workflows" / "release-smoke.yml"


class TestReleaseRecoveryWorkflow(unittest.TestCase):
    def test_docker_lane_can_use_override_ref(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("source_ref:", content)
        self.assertIn('echo "source_ref=$SOURCE" >> "$GITHUB_OUTPUT"', content)
        self.assertIn("ref: ${{ needs.resolve.outputs.source_ref }}", content)
        self.assertGreaterEqual(
            content.count("ref: ${{ needs.resolve.outputs.source_ref }}"),
            2,
        )

    def test_release_prompts_use_version_agnostic_examples(self):
        recovery = WORKFLOW.read_text(encoding="utf-8")
        smoke = RELEASE_SMOKE.read_text(encoding="utf-8")
        self.assertIn("e.g. vX.Y.Z", recovery)
        self.assertIn("semver like vX.Y.Z", recovery)
        self.assertNotIn("v1.3.0", recovery)
        self.assertIn("e.g. X.Y.Z", smoke)
        self.assertNotIn("1.3.0", smoke)


if __name__ == "__main__":
    unittest.main()
