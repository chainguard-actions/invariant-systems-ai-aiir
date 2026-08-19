# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import aiir._ledger as ledger
from aiir._policy import evaluate_ledger_policy


class TestLedgerSigningBackfillCoverage(unittest.TestCase):
    def _receipt(self, sha: str, *, extensions: object) -> dict[str, object]:
        return {
            "commit": {"sha": sha},
            "extensions": extensions,
        }

    def test_load_index_resets_non_dict_commits_before_backfill(self):
        """Updated (D4 fix): sigstore_bundle must be a structurally-valid bundle
        shape; a bare dict like {'bundle': 'present'} is now unsigned."""
        with tempfile.TemporaryDirectory() as td:
            ledger_dir = Path(td)
            index_path = ledger_dir / ledger.INDEX_FILE
            ledger_path = ledger_dir / ledger.LEDGER_FILE

            index_path.write_text(
                json.dumps({"version": 1, "receipt_count": 1, "commits": []}),
                encoding="utf-8",
            )
            # D4: use a structurally-valid Sigstore bundle (not merely truthy).
            ledger_path.write_text(
                json.dumps(
                    self._receipt(
                        "signed-sha",
                        extensions={
                            "sigstore_bundle": {
                                "mediaType": "application/vnd.dev.sigstore.bundle+json;version=0.2",
                                "verificationMaterial": {
                                    "certificate": {"rawBytes": "AAAA"}
                                },
                                "messageSignature": {"signature": "BBBB"},
                            }
                        },
                    )
                )
                + "\n",
                encoding="utf-8",
            )

            loaded = ledger._load_index(index_path)

        self.assertEqual(loaded["commits"], {})
        self.assertEqual(loaded["signed_receipt_count"], 1)
        self.assertEqual(loaded["unsigned_receipt_count"], 0)

    def test_load_index_backfills_legacy_signing_counts_and_flags(self):
        """Updated (D4 fix): extensions.sigstore must be a structurally-valid
        bundle dict; {'bundle': 'present'} is now treated as unsigned."""
        with tempfile.TemporaryDirectory() as td:
            ledger_dir = Path(td)
            index_path = ledger_dir / ledger.INDEX_FILE
            ledger_path = ledger_dir / ledger.LEDGER_FILE

            legacy_index = {
                "version": 1,
                "receipt_count": 2,
                "commits": {
                    "signed-sha": {"ai": False},
                    "unsigned-sha": {"ai": True},
                },
            }
            index_path.write_text(json.dumps(legacy_index), encoding="utf-8")
            # D4: use a structurally-valid bundle for the "signed" receipt.
            ledger_path.write_text(
                "\n".join(
                    [
                        "",
                        "not-json",
                        json.dumps(["not", "a", "receipt"]),
                        json.dumps({"commit": {}}),
                        json.dumps(
                            self._receipt(
                                "signed-sha",
                                extensions={
                                    "sigstore": {
                                        "mediaType": "application/vnd.dev.sigstore.bundle+json;version=0.2",
                                        "verificationMaterial": {
                                            "certificate": {"rawBytes": "AAAA"}
                                        },
                                        "messageSignature": {"signature": "BBBB"},
                                    }
                                },
                            )
                        ),
                        json.dumps(
                            self._receipt("unsigned-sha", extensions=["not-a-dict"])
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            loaded = ledger._load_index(index_path)

        self.assertEqual(loaded["signed_receipt_count"], 1)
        self.assertEqual(loaded["unsigned_receipt_count"], 1)
        self.assertTrue(loaded["commits"]["signed-sha"]["signed"])
        self.assertFalse(loaded["commits"]["unsigned-sha"]["signed"])

    def test_backfill_signing_metadata_replaces_non_dict_commits(self):
        """Updated (D4 fix): sigstore_bundle must be a structurally-valid
        bundle shape to count as signed; bare dicts are now unsigned."""
        with tempfile.TemporaryDirectory() as td:
            ledger_path = Path(td) / ledger.LEDGER_FILE
            # D4: use a structurally-valid Sigstore bundle.
            ledger_path.write_text(
                json.dumps(
                    self._receipt(
                        "signed-sha",
                        extensions={
                            "sigstore_bundle": {
                                "mediaType": "application/vnd.dev.sigstore.bundle+json;version=0.2",
                                "verificationMaterial": {
                                    "certificate": {"rawBytes": "AAAA"}
                                },
                                "messageSignature": {"signature": "BBBB"},
                            }
                        },
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            index = {"receipt_count": 1, "commits": []}

            ledger._backfill_signing_metadata(index, ledger_path)

        self.assertEqual(index["commits"], {})
        self.assertEqual(index["signed_receipt_count"], 1)
        self.assertEqual(index["unsigned_receipt_count"], 0)


class TestPolicyUnsignedCountCoverage(unittest.TestCase):
    def test_signed_count_without_total_clamps_unsigned_to_zero(self):
        index = {
            "signed_receipt_count": 3,
            "ai_commit_count": 0,
            "ai_percentage": 0.0,
        }
        policy = {"max_unsigned_receipts": 0, "enforcement": "hard-fail"}

        passed, _, violations = evaluate_ledger_policy(index, policy)

        self.assertTrue(passed)
        self.assertEqual(violations, [])

    def test_commit_signing_state_derives_unsigned_count(self):
        index = {
            "receipt_count": 4,
            "commits": {
                "a": {"signed": True},
                "b": {"signed": False},
                "c": {"other": 1},
                "d": "not-a-dict",
            },
            "ai_commit_count": 0,
            "ai_percentage": 0.0,
        }
        policy = {"max_unsigned_receipts": 2, "enforcement": "hard-fail"}

        passed, _, violations = evaluate_ledger_policy(index, policy)

        self.assertFalse(passed)
        self.assertEqual([v.rule for v in violations], ["max_unsigned_receipts"])
        self.assertIn("3/4", violations[0].message)

    def test_commits_without_signed_flags_do_not_derive_unsigned_count(self):
        index = {
            "receipt_count": 4,
            "commits": {
                "a": {"other": 1},
                "b": "not-a-dict",
            },
            "ai_commit_count": 0,
            "ai_percentage": 0.0,
        }
        policy = {"max_unsigned_receipts": 0, "enforcement": "hard-fail"}

        passed, _, violations = evaluate_ledger_policy(index, policy)

        self.assertTrue(passed)
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
