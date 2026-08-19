"""Unit tests for scripts/sync_ci_secrets.py.

Copyright 2025-2026 Invariant Systems, Inc.
# SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "sync_ci_secrets.py"
SPEC = importlib.util.spec_from_file_location("sync_ci_secrets", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class TestSyncCiSecrets(unittest.TestCase):
    def test_parse_env_stream_handles_null_delimited_payload(self) -> None:
        payload = b"GITLAB_TOKEN=abc\0VSCE_PAT=xyz\0EMPTY=\0"
        parsed = MODULE.parse_env_stream(payload)
        self.assertEqual(parsed["GITLAB_TOKEN"], "abc")
        self.assertEqual(parsed["VSCE_PAT"], "xyz")
        self.assertEqual(parsed["EMPTY"], "")

    def test_resolve_secret_source_uses_first_available_alias(self) -> None:
        entry = MODULE.SecretEntry(
            name="VSCE_PAT",
            sources=("VSCE_PAT", "AZURE_DEV_PAT"),
            required=True,
            description="Marketplace token",
        )
        resolved = MODULE.resolve_secret_source(entry, {"AZURE_DEV_PAT": "token-value"})
        self.assertEqual(resolved, "AZURE_DEV_PAT")

    def test_filter_entries_returns_named_subset(self) -> None:
        entries = [
            MODULE.SecretEntry("GITLAB_TOKEN", ("GITLAB_TOKEN",), True, ""),
            MODULE.SecretEntry("NPM_TOKEN", ("NPM_TOKEN",), True, ""),
        ]
        filtered = MODULE.filter_entries(entries, {"NPM_TOKEN"})
        self.assertEqual([entry.name for entry in filtered], ["NPM_TOKEN"])

    @patch.dict("os.environ", {"VSCE_PAT": "from-env"}, clear=True)
    def test_combine_env_overrides_vault_values_with_process_env(self) -> None:
        combined = MODULE.combine_env(
            {"VSCE_PAT": "from-vault", "GITLAB_TOKEN": "gitlab"}
        )
        self.assertEqual(combined["VSCE_PAT"], "from-env")
        self.assertEqual(combined["GITLAB_TOKEN"], "gitlab")


if __name__ == "__main__":
    unittest.main()
