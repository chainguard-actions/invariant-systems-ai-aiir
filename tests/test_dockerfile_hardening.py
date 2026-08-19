# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = REPO_ROOT / "Dockerfile"


class TestDockerfileHardening(unittest.TestCase):
    def test_runtime_security_packages_are_installed(self):
        content = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("apt-get update", content)
        for package in (
            "git",
            "libc-bin",
            "libc6",
            "openssl",
            "openssl-provider-legacy",
        ):
            self.assertIn(package, content)


if __name__ == "__main__":
    unittest.main()
